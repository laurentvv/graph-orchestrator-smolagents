"""Read-Before-Write Gate — Priorité 1 (F-66) du plan usine logicielle.

L'invariant n°1 « read-before-write » (cf. UNIVERSAL_INVARIANTS dans prompts.py)
était jusqu'ici UNIQUEMENT en prompt (nodes.py) — aucun garde logiciel ne
l'appliquait. Le Coder (CodeAgent) pouvait donc éditer/écraser un fichier
existant sans l'avoir lu, ou enchaîner write→edit sans relire, ce qui est la
cause n°1 de corruption aveugle (cf. Deer Flow issue #3857 : « append sans jamais
relire », le modèle édite à l'aveugle une représentation mentale stale).

Ce module est le middleware-gate qui ferme ce gap. Inspiré fidèlement de
`references/deer-flow/backend/packages/harness/deerflow/agents/middlewares/
read_before_write_middleware.py` (plan + spec design lus), adapté à notre
CodeAgent unique séquentiel (pas un graphe LangGraph multi-threads).

**Règle ALLOW vs BLOCK** : un outil d'écriture sur un fichier EXISTANT est
bloqué si, parmi les lectures enregistrées pour ce chemin normalisé, la plus
récente a un hash ≠ du contenu actuel du fichier (sha256 du contenu COMPLET
UTF-8). Fail-open sur toute erreur d'inspection (fichier absent = création OK ;
read impossible = on laisse passer pour ne jamais briquer l'agent).
« Newest mark wins ».

**Mode Strict** (décision utilisateur, fidèle à Deer Flow) : un write RÉUSSI
n'auto-stamp PAS la mark → toute édition suivante sur le même fichier est
bloquée jusqu'à un nouveau `read_file`. Force l'invariant read-before-every-edit.

**Écart consciencieux vs Deer Flow** : Deer Flow stocke la mark sur
`ToolMessage.additional_kwargs["deerflow_read_mark"]` (mark liée à la survie du
contexte, car LangGraph peut summarizer/drop les messages). Notre Coder est un
CodeAgent unique séquentiel → la mark est tenue en RAM dans un dict partagé
`{norm_path: hash}` (pattern `screenshot_capture` éprouvé dans
vision_callback.py). Plus simple, adapté à notre archi.

Le branchement se fait via `wrap_tools_with_read_gate` qui enveloppe `read_file`
dans `_ReadTrackingTool` et chaque outil d'écriture dans `_GatedWriteTool`
(template copié de `SanitizedTool` dans sanitizer.py). 100 % Python natif, 0 LLM.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Any, List, Tuple

from smolagents import BaseTool

# Outil qui « stamp » une mark de lecture après appel.
_READ_TOOLS = frozenset({"read_file"})

# Outils d'écriture soumis au gate. Deer Flow gate write_file + str_replace ;
# on ajoute nos outils d'édition équivalents (edit_file, search_replace,
# multi_replace) qui ÉCRASENT/MODIFIENT un fragment existant — ce sont eux qui
# peuvent corrompre aveuglément un fichier non lu.
#
# EXCEPTION : `append_file` est VOLONTAIREMENT EXEMPTÉ du gate. Raisons :
# (1) un append n'écrase pas — il ajoute à la fin — l'anti-doublon F-28 (garde
#     textuelle « content == fin du fichier ») + l'idempotence F-43 (backing
#     DuckDB) suffisent à le protéger.
# (2) `append_file` est le MÉCANISME CENTRAL de la stratégie incremental (F-28) :
#     write_file(squelette) puis N append_file(sections). Forcer un read_file
#     avant CHAQUE append (mode Strict) double le nombre de steps et fait
#     exploser le contexte (test live 2026-08-04 : 425k tokens, crash overflow).
# (3) Deer Flow n'a pas d'équivalent d'append incremental — son `write_file`
#     avec append=True gère la création, pas la construction section-par-section.
_GATED_WRITE_TOOLS = frozenset(
    {"write_file", "search_replace", "edit_file", "multi_replace"}
)


# ==========================================
# Helpers purs (0 dépendance smolagents)
# ==========================================
def compute_content_hash(content: str) -> str:
    """Hash SHA256 du contenu (UTF-8). Stable, déterministe.

    Fidèle à Deer Flow `_content_hash` : toujours le contenu COMPLET, jamais
    path+mtime ni taille. Le hash est le témoin de « version du fichier vue ».
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_path(path: str) -> str:
    """Normalise un chemin de fichier (équivalent posixpath.normpath Deer Flow).

    Windows-safe (win32) : `os.path.normpath(os.path.abspath(...))` résout les
    `..`, séparateWindows mixed (`/` et `\\`), et rend absolu. Deux écritures
    du même fichier (`./a/b.txt`, `a//b.txt`, `a/c/../b.txt`) → même clé.
    """
    return os.path.normpath(os.path.abspath(path))


# ==========================================
# État partagé (le « store des marks »)
# ==========================================
class ReadGate:
    """Tient en RAM le dict {norm_path: hash} des dernières lectures du Coder.

    Thread-safe (threading.Lock) — les @tool smolagents tournent dans des
    threads (asyncio.to_thread), et le workflow coding est séquentiel mais on
    garde le verrou par sécurité (défense ceinture+bretelles, comme _file_lock).

    Toutes les méthodes ne lèvent jamais — un gate doit être fail-open par
    construction (jamais briquer l'agent).
    """

    def __init__(self) -> None:
        self._marks: dict[str, str] = {}
        self._lock = threading.Lock()

    def record_read(self, path: str, content: str) -> None:
        """Stamp le hash du contenu lu pour ce chemin.

        Deer Flow : même sur un read partiel (offset/limit), on hashe TOUJOURS
        le contenu complet passé en argument — l'appelant (_ReadTrackingTool)
        est responsable de re-lire le fichier entier pour hasher la vérité
        disque, peu importe le slice demandé par l'agent.
        """
        if not path or not isinstance(path, str):
            return
        try:
            norm = _normalize_path(path)
            h = compute_content_hash(content)
            with self._lock:
                self._marks[norm] = h
        except Exception:
            # Fail-open : ne jamais planter sur un read bizarre.
            return

    def record_write(self, path: str) -> None:
        """Mode Strict (Deer Flow) : un write RÉUSSI invalide la mark.

        La prochaine édition sur ce même fichier sera BLOQUÉE jusqu'à un
        nouveau read_file. C'est l'invariant read-before-every-edit : l'auteur
        doit relire son propre output avant de l'éditer (prévient le bug
        « append/édition à partir d'une représentation mentale stale »).
        """
        if not path or not isinstance(path, str):
            return
        try:
            norm = _normalize_path(path)
            with self._lock:
                # pop avec défaut : idempotent si pas de mark (création).
                self._marks.pop(norm, None)
        except Exception:
            return

    def check_write(self, path: str) -> Tuple[bool, str]:
        """Décide ALLOW vs BLOCK pour une écriture sur `path`.

        Renvoie `(allowed, reason)` — `reason` vide si allowed, message
        pédagogique si bloqué. Ne lève JAMAIS (fail-open `(True, "")`).

        Règle (fidèle Deer Flow `_check_write_gate`) :
        1. path absent/None → ALLOW (outil sans path, on laisse passer).
        2. Fichier absent du disque → ALLOW (CRÉATION, premier write OK).
        3. Read impossible (permissions, binaire, IO) → ALLOW (fail-open).
        4. hash de la dernière lecture connue == hash disque → ALLOW.
        5. Sinon (pas de lecture, ou lecture stale) → BLOCK.
        """
        if not path or not isinstance(path, str):
            return (True, "")
        try:
            norm = _normalize_path(path)
            # (2) Fichier absent = création autorisée.
            if not os.path.exists(norm):
                return (True, "")
            # (3) Lecture du contenu disque : si ça lève, fail-open.
            try:
                with open(norm, "r", encoding="utf-8") as f:
                    current = f.read()
            except (OSError, UnicodeDecodeError):
                return (True, "")
            current_hash = compute_content_hash(current)
            # (4) Dernière lecture connue pour ce path.
            with self._lock:
                last_read_hash = self._marks.get(norm)
            if last_read_hash is not None and last_read_hash == current_hash:
                return (True, "")
            # (5) Pas de lecture, ou lecture stale (hash ≠) → BLOCK.
            return (
                False,
                _BLOCK_MESSAGE.format(tool_name="write/edit", path=path),
            )
        except Exception:
            # Fail-open absolu : aucune inspection ne doit briquer l'agent.
            return (True, "")


_BLOCK_MESSAGE = (
    "ERROR (Read-Before-Write Gate): {path} already exists and you have not read "
    "its CURRENT version. Any write invalidates earlier reads, so you MUST re-read "
    "before every modification. Call read_file on {path} first (a ranged read of "
    "the relevant section is enough, e.g. the last ~30 lines before an append), "
    "check what is already there, then retry your edit. The file was NOT modified."
)


# ==========================================
# Proxies d'outils (template copié de SanitizedTool, sanitizer.py:170-219)
# ==========================================
class _GatedWriteTool(BaseTool):
    """Proxy autour d'un outil d'écriture qui applique le read-before-write gate.

    Copie name/description/inputs/output_type de l'outil sous-jacent (pour que
    le CodeAgent smolagents l'expose correctement dans son interpréteur Jinja).
    Intercepte `__call__` ET `forward` : si `check_write(path)` bloque, renvoie
    le message d'erreur SANS déléguer ; sinon délèue puis appelle `record_write`.
    `__getattr__` délèue tout le reste (préserve `to_code_prompt` etc.).
    """

    def __init__(self, tool: BaseTool, gate: "ReadGate") -> None:
        self._wrapped = tool
        self._gate = gate
        self.name = getattr(tool, "name", "")
        self.description = getattr(tool, "description", "")
        self.inputs = getattr(tool, "inputs", {})
        self.output_type = getattr(tool, "output_type", "string")
        super().__init__()

    def __getattr__(self, item: str) -> Any:
        # Délégue tout attribut non défini ici (to_code_prompt, etc.) à l'outil
        # sous-jacent — critique pour ne pas casser le rendu du prompt CodeAgent.
        return getattr(self._wrapped, item)

    def _check_and_record(self, kwargs: dict, result: Any) -> Any:
        """Hook appelé après un write RÉUSSI pour invalider la mark (Strict)."""
        path = kwargs.get("path")
        if path is not None:
            self._gate.record_write(path)
        return result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # Le CodeAgent appelle les outils via __call__ (chemin confirmé dans
        # sanitizer.py docstring). On coerce rien ici (le sanitizer le fait en
        # amont ou en aval selon l'ordre de la chaîne) — on ne fait que gate.
        allowed, reason = self._gate.check_write(kwargs.get("path"))
        if not allowed:
            return reason
        result = self._wrapped(*args, **kwargs)
        return self._check_and_record(kwargs, result)

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        # Chemin TCA / fallback. Même logique que __call__.
        allowed, reason = self._gate.check_write(kwargs.get("path"))
        if not allowed:
            return reason
        result = self._wrapped.forward(*args, **kwargs)
        return self._check_and_record(kwargs, result)


class _ReadTrackingTool(BaseTool):
    """Proxy miroir autour de read_file qui stamp la mark de lecture.

    Après délégation à read_file, on RE-LIT le fichier disque en interne pour
    hasher le contenu COMPLET (vision Deer Flow) — peu importe l'offset/limit
    demandé par l'agent, la mark reflète la version complète du fichier.
    """

    def __init__(self, tool: BaseTool, gate: "ReadGate") -> None:
        self._wrapped = tool
        self._gate = gate
        self.name = getattr(tool, "name", "")
        self.description = getattr(tool, "description", "")
        self.inputs = getattr(tool, "inputs", {})
        self.output_type = getattr(tool, "output_type", "string")
        super().__init__()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._wrapped, item)

    def _stamp_after_read(self, kwargs: dict) -> None:
        """Stamp le hash du contenu COMPLET du fichier (re-lecture disque)."""
        path = kwargs.get("path")
        if not path or not isinstance(path, str):
            return
        try:
            norm = _normalize_path(path)
            if not os.path.exists(norm):
                return
            with open(norm, "r", encoding="utf-8") as f:
                full_content = f.read()
            self._gate.record_read(path, full_content)
        except Exception:
            # Fail-open : ne jamais planter sur un stamp de mark.
            return

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self._wrapped(*args, **kwargs)
        self._stamp_after_read(kwargs)
        return result

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        result = self._wrapped.forward(*args, **kwargs)
        self._stamp_after_read(kwargs)
        return result


# ==========================================
# Branchement (miror de sanitize_tools / wrap_screenshot_tools)
# ==========================================
def wrap_tools_with_read_gate(
    tools: List[BaseTool], gate: ReadGate, enabled: bool = True
) -> List[BaseTool]:
    """Enveloppe read_file et les outils d'écriture avec le gate.

    No-op (liste inchangée) quand `enabled=False` (opt-out
    READ_BEFORE_WRITE_ENABLED=false). Préserve l'ordre de la liste. Les outils
    non ciblés (list_directory, bash_command, MCP, DuckDuckGo, ...) restent
    intacts.
    """
    if not enabled:
        return tools
    wrapped: List[BaseTool] = []
    for t in tools:
        name = getattr(t, "name", "")
        if name in _READ_TOOLS and isinstance(t, BaseTool):
            wrapped.append(_ReadTrackingTool(t, gate))
        elif name in _GATED_WRITE_TOOLS and isinstance(t, BaseTool):
            wrapped.append(_GatedWriteTool(t, gate))
        else:
            wrapped.append(t)
    return wrapped
