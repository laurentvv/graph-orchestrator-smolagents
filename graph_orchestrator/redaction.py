"""Redaction de secrets avant injection au LLM / affichage (F-105, P8-bis).

Directive « Redact » portée de references/mattpocock-skills/skills/engineering/
diagnosing-bugs/SKILL.md : tout secret montré (commande, output, artefact
capturé) est remplacé par ``<REDACTED>`` — les captures HAR portent des auth
headers, les dumps d'env portent des tokens. Dans ce projet, les traces
(sorties bash_command, feedback Tester→Judge→Coder) transitent par
``feedback_utils.truncate_output`` : c'est le point de branchement unique, la
redaction s'applique à la LECTURE (injection au LLM / logs), DuckDB conserve
le contenu intégral pour l'audit post-mortem — même doctrine que la troncature
F-21.

 POLITIQUE ANTI-CORRUPTION (fail-open documenté) : mieux vaut laisser passer un
 secret exotique que casser la lisibilité du CODE montré au Judge. Les valeurs
 qui ressemblent à du code (accès attribut ``a.b``, appel ``f()``, référence
 env ``$VAR`` / ``%VAR%``, placeholder ``<...>``) ne sont PAS redactées. Les
 secrets exotiques restent visibles localement (LLM local, DuckDB local) — le
 risque résiduel est borné à la machine.
"""

from __future__ import annotations

import re
from typing import Optional

REDACTED = "<REDACTED>"

# Blocs de clés privées PEM (RSA/EC/OPENSSH/...) — tout le bloc est remplacé.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)

# Identifiants dans une URL (https://user:password@host) — l'utilisateur est
# conservé (utile au diagnostic), le mot de passe est redacté.
_URL_CREDENTIALS_RE = re.compile(r"(?i)(https?://[^\s/:@\"']+):([^\s/@\"']+)(@)")

# Tokens avec préfixe réservé connus (OpenAI, GitHub, Slack, AWS, Google).
_TOKEN_PREFIXES_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{20,}"  # OpenAI-style
    r"|ghp_[A-Za-z0-9]{30,}"  # GitHub PAT (classic)
    r"|github_pat_[A-Za-z0-9_]{20,}"  # GitHub PAT (fine-grained)
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"  # Slack
    r"|AKIA[0-9A-Z]{16}"  # AWS access key id
    r"|AIza[0-9A-Za-z_\-]{35}"  # Google API key
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"  # JWT
    r")\b"
)

# En-têtes d'autorisation : "Bearer <token>", "token: <token>".
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(bearer|authorization)\s*[:=]?\s+[A-Za-z0-9._~+/=-]{16,}"
)

# Affectations nommées : password=..., api_key: ..., client_secret= ...
# Le NOM est conservé (le LLM doit savoir qu'un secret existait à cet endroit),
# seule la VALEUR est remplacée. Quotes optionnelles appariées. Le nom peut être
# le SUFFIXE d'un identifiant plus long (PGPASSWORD, OS_PASSWORD, DB_TOKEN...)
# d'où le préfixe [A-Za-z0-9_]* capturé AVEC le nom (conservé dans la sortie).
_SECRET_NAMES = (
    r"password|passwd|pwd|secret(?:[_-]?key)?|api[_-]?key|apikey|"
    r"access[_-]?token|auth[_-]?token|client[_-]?secret|token"
)
_ASSIGNMENT_RE = re.compile(
    rf"""(?xi)\b(?P<name>[A-Za-z0-9_]*(?:{_SECRET_NAMES}))\s*(?P<sep>[:=])\s*
    (?P<q>["']?)(?P<val>[^\s"'<>]{{8,}})(?P=q)"""
)

# Valeurs qui ressemblent à du CODE ou à une référence, pas à un secret littéral.
_CODE_LOOK_CHARS = set(".()[]{}@$%")  # accès/membre, appel, index, env var
_CODE_LOOK_PREFIXES = ("<", "${", "%", "$")


def _looks_like_code(value: str) -> bool:
    """True si la valeur ressemble à du code / une référence plutôt qu'un secret."""
    if value.upper() == REDACTED:
        return True  # déjà redacté (idempotence)
    if value[:1] in _CODE_LOOK_PREFIXES:
        return True
    return any(ch in _CODE_LOOK_CHARS for ch in value)


def redact_secrets(text: Optional[str]) -> str:
    """Remplace les secrets reconnaissables d'un texte par ``<REDACTED>``.

    Deterministe, 0 LLM, jamais d'exception. Fail-open : un secret non reconnu
    passe tel quel (priorité à la lisibilité du code, cf. docstring module).
    """
    if not text:
        return ""

    out = _PRIVATE_KEY_RE.sub(REDACTED, text)
    out = _URL_CREDENTIALS_RE.sub(rf"\1:{REDACTED}\3", out)
    out = _TOKEN_PREFIXES_RE.sub(REDACTED, out)
    out = _AUTH_HEADER_RE.sub(rf"\1 {REDACTED}", out)

    def _sub_assign(m: re.Match) -> str:
        value = m.group("val")
        if _looks_like_code(value):
            return m.group(0)
        q = m.group("q")
        return f"{m.group('name')}{m.group('sep')}{q}{REDACTED}{q}"

    out = _ASSIGNMENT_RE.sub(_sub_assign, out)
    return out
