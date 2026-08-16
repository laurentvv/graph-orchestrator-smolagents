"""Garde-fous anti-boucle de compaction (F-101, P9+P3).

Deux invariants complémentaires, 0 LLM, Python pur :

1. ``OverflowGuard`` (fiche 24-pi → ``packages/agent/docs/harness.md`` §3.9,
   ``overflowRecoveryUsed``) : UN SEUL essai de récupération d'overflow par
   input utilisateur. La première erreur de dépassement de contexte déclenche
   la récupération (compaction/purge) et arme le drapeau ; si la requête
   recompactée déborde ENCORE, on ne recompacte pas — on passe en
   ``failure_drain`` (échec propre, plus aucune inférence brûlée). Sans ce
   garde, un prompt système incompressible (tools schemas + skills + tâche)
   fait purger-rejouer-purger tous les retries du nœud pour rien.

2. ``CompactionBudget`` (fiche 25-hermes-agent →
   ``agent/conversation_compression.py`` + ``context_compressor.py``) :
   budget de tentatives de compaction remboursé UNIQUEMENT après progrès
   réel vérifié — le verdict d'efficacité est rendu par l'usage provider
   rapporté par la requête suivante (prompt_tokens réel), jamais par une
   estimation ou par « la liste de messages a rétréci ». Évite de payer N
   compactages inutiles sur un transcript incompressible.

   Écarts consciencieux vs hermes (documentés) : pas de persistance DB des
   compteurs (notre agent vit en RAM, mono-process séquentiel — un restart
   repart de toute façon d'un nœud neuf) ni de fenêtre de probation 300 s
   (le breaker simplifié bloque ; la probation sera ajoutée si un run réel
   montre le besoin). Le cœur — remboursement sur usage vérifié, verdict
   unique par compaction — est porté fidèlement.

Branchement prod : ``OverflowGuard`` est utilisé dans
``nodes.run_with_retry`` (détection d'overflow dans le bloc except).
``CompactionBudget`` est prêt pour le compact LLM opt-in (F-86) — module
testé, dormant tant que la compaction déterministe 0-LLM reste la défaut.
"""

import re
from dataclasses import dataclass
from typing import Optional, Union

__all__ = [
    "is_context_overflow_error",
    "OverflowGuard",
    "CompactionBudget",
]


# Détection d'un dépassement de contexte dans un message d'erreur provider.
# s08 détecte « prompt_too_long » / « too many tokens » ; F-104
# (llm_retry._FATAL_RES) classe déjà « context length|maximum context|too
# long » en fatal transport — l'exception remonte donc au nœud ; ce filtre
# décide si c'est un OVERFLOW (récupérable par compaction) ou une autre
# erreur fatale. Frontières de mots sur les codes nu (leçon F-104 : un code
# ne doit pas matcher un port).
_OVERFLOW_RES = (
    re.compile(r"contex(t|t window|t size)\b.*(exceed|larger|longer|too)|"
               r"(exceed|larger|longer|too).*(contex(t|t window)|tokens)", re.I),
    re.compile(r"context length|maximum context|context window", re.I),
    re.compile(r"prompt[_ ]?too[_ ]?long|too many tokens|too long", re.I),
    re.compile(r"input tokens? .{0,40} (exceeds?|larger than)", re.I),
    re.compile(r"requested .{0,30}tokens?,? .{0,30}(resulted|maximum|limit)", re.I),
)


def is_context_overflow_error(exc_or_msg: Union[BaseException, str]) -> bool:
    """True si l'erreur signale un dépassement de la fenêtre de contexte.

    Tolérant par construction : accepte une exception ou une chaîne, ne
    lève jamais.
    """
    try:
        msg = str(exc_or_msg)
    except Exception:
        return False
    return any(rx.search(msg) for rx in _OVERFLOW_RES)


@dataclass
class OverflowGuard:
    """Un seul essai de récupération d'overflow par input utilisateur (pi §3.9).

    ``on_overflow()`` arme le drapeau DANS LA MÊME décision atomique que
    « on récupère » (un crash entre les deux ne permet pas deux récupérations).
    Un second overflow sans nouvel input utilisateur → ``failure_drain`` :
    la boucle doit rendre un échec propre SANS réessayer (chez nous :
    ``return None`` au niveau nœud — le graphe continue, le Judge arbitre).
    """

    recovery_used: bool = False
    failure: Optional[str] = None

    def on_overflow(self) -> bool:
        """À appeler sur erreur d'overflow. True = récupérer, False = drainer."""
        if self.failure is not None:
            return False
        if self.recovery_used:
            self.failure = (
                "context overflow persists after recovery — incompressible request"
            )
            return False
        self.recovery_used = True
        return True

    def on_new_user_input(self) -> None:
        """Réarme le drapeau (pi : « consuming new user input resets the flag »).

        Un tool-result seul ne réarme PAS (le contexte a la même forme) ;
        seul un input utilisateur projeteur efface l'échec et réarme.
        """
        self.recovery_used = False
        self.failure = None

    def is_drained(self) -> bool:
        return self.failure is not None


@dataclass
class CompactionBudget:
    """Budget de compaction remboursé après progrès réel vérifié (hermes).

    Règle d'or : le verdict d'efficacité est « le prompt provider réel est-il
    repassé sous le seuil ? », rendu UNE SEULE fois par compaction (le latch
    ``verify_cleared`` est consommé à la première lecture d'usage, même sans
    usage rapporté). Une estimation grossière ne rembourse jamais.
    """

    threshold_tokens: int = 0  # 0 = seuil inconnu → verdict impossible
    max_attempts: int = 3
    attempts: int = 0
    ineffective_strikes: int = 0
    fallback_streak: int = 0
    verify_cleared: bool = False
    awaiting_real_usage: bool = False

    def exhausted(self) -> bool:
        return self.attempts >= self.max_attempts

    def blocked(self) -> bool:
        """Breaker anti-thrash : 2 compactions inefficaces OU 2 fallbacks de suite."""
        return self.ineffective_strikes >= 2 or self.fallback_streak >= 2

    def charge(self) -> None:
        """La tentative démarre réellement (consomme le budget)."""
        self.attempts += 1

    def refund_noop(self) -> None:
        """No-op par verrou = DEFER temporaire, pas une preuve
        d'incompressibilité → remboursement immédiat (hermes)."""
        self.attempts = max(0, self.attempts - 1)

    def on_compaction_committed(
        self, made_progress: bool, used_fallback: bool = False
    ) -> None:
        """Compaction réellement commise. N'arme le verdict QUE sur progrès.

        hermes : « Arm the effectiveness verdict only after a completed
        rewrite crosses the full compaction boundary. Exceptions, aborts,
        and no-op attempts leave this false. »
        """
        if not made_progress:
            return
        self.verify_cleared = True
        self.awaiting_real_usage = True
        if used_fallback:
            self.fallback_streak += 1
        else:
            self.fallback_streak = 0

    def on_real_usage(self, prompt_tokens: Optional[int]) -> None:
        """Verdict : la réponse provider suivante rapporte l'usage réel.

        Consomme le latch quoi qu'il arrive (un seul verdict par compaction).
        Sous le seuil → remboursement du budget + reset des strikes.
        Au-dessus du seuil avec verdict pending → strike (n'a pas dégagé).
        Pas d'usage rapporté → pas de verdict différé.
        """
        verdict_pending = self.verify_cleared
        self.verify_cleared = False
        self.awaiting_real_usage = False
        if prompt_tokens is None or prompt_tokens <= 0:
            return
        if self.threshold_tokens <= 0:
            return  # seuil inconnu : aucune conclusion tirable
        if prompt_tokens < self.threshold_tokens:
            self.ineffective_strikes = 0
            if verdict_pending and self.attempts > 0:
                self.attempts = 0  # budget REMBOURSÉ sur usage vérifié
        elif verdict_pending:
            self.ineffective_strikes += 1
