"""Guard denylist pour bash_command (Priorité 8-bis du plan usine logicielle).

`bash_command` (tools.py) exécute des commandes issues du LLM via
`subprocess.run(cmd, shell=True)` — sans aucune garde. Un CodeAgent génère et
exécute du Python arbitraire, donc `bash_command` est exposé à des appels
destructeurs (que le LLM produise par hallucination ou par "zèle"). Ce guard
bloque les commandes manifestement dangereuses AVANT l'exécution.

PORTÉE : DENYLIST (pas sandbox Docker — trop lourde pour ce cycle). C'est le
premier pas concret vers la robustesse runtime (P8-bis) ; la sandbox complète
(Docker exec / process cloisonné) reste un chantier séparé.

Approche : regex sur la commande normalisée (case-insensitive). On couvre les
deux familles destructrices car l'environnement cible est Windows (cmd.exe via
shell=True) mais le projet peut aussi tourner sous Git Bash / WSL :
  - Windows : format, del /f /s /q, rmdir /s /q, shutdown, diskpart, reg delete,
    rd /s, écrasement de C:\\ / disques système.
  - Unix    : rm -rf /, rm -rf ~, mkfs, dd of=/dev/sd*, shutdown, fork bomb,
    chmod -R 777 /, > /dev/sda.

Comportement : le guard NE lève jamais d'exception. Il renvoie un verdict
(allowed, reason). Si bloqué, `bash_command` renvoie un message pédagogique au
LLM (pas une exception) pour qu'il ajuste sa commande vers un usage légitime.
"""

from __future__ import annotations

import re
from typing import Tuple

# ===========================================================================
# Patterns destructeurs — Unix + Windows (matchés sur la commande normalisée)
# ===========================================================================
# Chaque entrée : (regex compilée case-insensitive, label humain du danger).
# On commence par `(^|[\s;&|]+)` pour ne PAS matcher un mot noyau dans un chemin
# anodin (ex: "/format/mon rapport.txt" ne doit pas déclencher le `format` Windows).
# On accepte un séparateur explicite (espace, ;, &, |, début) avant le mot-clé.
_SEP = r"(?:^|[\s;&|]+)"  # début ou séparateur de commande

_DENY_PATTERNS: list[Tuple[re.Pattern, str]] = [
    # --- Unix : suppressions racines / force ---
    # rm -rf / (ou rm -fr /) : efface tout depuis la racine. On cible le "/" racine
    # ou un chemin système absolu (/usr, /etc...), PAS un "./..." local légitime.
    # NOTE sur les flags : pas de \b autour de `-rf` (\b ne matche pas entre `-` et
    # `r`, deux non-mots). On utilise `-[rRfF]{1,3}` (1 à 3 de ces lettres, couvre
    # -r, -f, -rf, -fr, -rfv...) suivi d'un séparateur.
    (re.compile(rf"{_SEP}rm\s+[^\n]*-[rRfF]{{1,3}}(?=\s)[^\n]*\s+(?:/(?:\s|$|/)|/(?:usr|etc|var|bin|boot|home|root|opt|lib|proc|sys|dev|tmp)(?:\s|$|/))", re.IGNORECASE),
     "rm -rf sur la racine du système de fichiers (Unix)"),
    # rm -rf ~ / rm -rf $HOME : efface le home de l'utilisateur.
    (re.compile(rf"{_SEP}rm\s+[^\n]*-[rRfF]{{1,3}}(?=\s)[^\n]*\s+(?:~(?:\s|$|/)|\$HOME(?:\s|$|/))", re.IGNORECASE),
     "rm -rf sur le répertoire home (Unix)"),
    # rm -rf * à la racine : trop risqué sans chemin borné.
    (re.compile(rf"{_SEP}rm\s+[^\n]*-[rRfF]{{1,3}}(?=\s)[^\n]*\s+\*\s*$", re.IGNORECASE),
     "rm -rf * sans chemin borné (Unix)"),
    # mkfs : formate une partition entière.
    (re.compile(rf"{_SEP}mkfs(?:\.\w+)?\s", re.IGNORECASE),
     "mkfs : formatage de partition (Unix)"),
    # dd if=... of=/dev/sd* : écriture brute sur un disque (efface tout).
    (re.compile(rf"{_SEP}dd\s+[^\n]*of=/dev/(?:sd|nvme|hd|vd|disk)", re.IGNORECASE),
     "dd vers un périphérique bloc (efface un disque, Unix)"),
    # Fork bomb :(){ :|:& };:  (on détecte le motif caractéristique)
    (re.compile(r":\(\)\s*\{.*:.*:.*&.*\}.*;", re.IGNORECASE | re.DOTALL),
     "fork bomb (Unix)"),
    # chmod -R 777 / : ouvre toutes les permissions depuis la racine (casse le système).
    (re.compile(rf"{_SEP}chmod\s+[^\n]*(?<=\s)-R(?=\s)[^\n]*\s+(?:/(?:\s|$|/)|/(?:usr|etc|var|bin|boot|home|root|lib)(?:\s|$|/))", re.IGNORECASE),
     "chmod -R 777 depuis la racine (Unix)"),
    # > /dev/sda (redirection vers un disque) — écrasement brute.
    (re.compile(r">\s*/dev/(?:sd|nvme|hd|vd|disk)", re.IGNORECASE),
     "redirection vers un périphérique bloc (Unix)"),

    # --- Windows : suppressions / formatage système ---
    # format C: (ou D:, etc.) : formate un disque entier.
    (re.compile(rf"{_SEP}format\s+[a-z]:", re.IGNORECASE),
     "format : formatage de disque (Windows)"),
    # del /f /s /q sur C:\ ou système, rmdir /s /q, rd /s /q sur racine.
    # On cible les destructeurs récursifs (/f /s /q) sur des chemins racines/système.
    # Lookbehind (?<=\s) + lookahead (?=\s) autour des flags /s /q /f : un flag est
    # un séparateur + lettre + séparateur, PAS un sous-chemin comme "/src".
    (re.compile(rf"{_SEP}(?:rmdir|rd)\s+[^\n]*(?<=\s)/s(?=\s)[^\n]*(?<=\s)/q(?=\s)[^\n]*\s+(?:[a-z]:\\|\$Recycle|%SystemRoot%|%Windir%|%ProgramFiles%)", re.IGNORECASE),
     "rmdir/rd /s /q sur chemin racine/système (Windows)"),
    (re.compile(rf"{_SEP}del\s+[^\n]*(?<=\s)/f(?=\s)[^\n]*(?<=\s)/s(?=\s)[^\n]*(?<=\s)/q(?=\s)[^\n]*\s+(?:[a-z]:\\|\$Recycle|%SystemRoot%|%Windir%|%ProgramFiles%)", re.IGNORECASE),
     "del /f /s /q sur chemin racine/système (Windows)"),
    # diskpart (bas niveau, formate/partitionne).
    (re.compile(rf"{_SEP}diskpart(?:\s|$)", re.IGNORECASE),
     "diskpart : outil disque bas niveau (Windows)"),
    # reg delete sans clé bornée sur HKLM/HKCR (corruption registre système).
    (re.compile(rf"{_SEP}reg\s+delete\s+[^\n]*(?:HKLM|HKEY_LOCAL_MACHINE|HKCR|HKEY_CLASSES_ROOT)\\", re.IGNORECASE),
     "reg delete sur ruche système (Windows)"),

    # --- Cross-plateforme : extinction / réseau dangereux ---
    # shutdown / halt / poweroff / reboot (n'importe quelle plateforme).
    (re.compile(rf"{_SEP}(?:shutdown|halt|poweroff|reboot)(?:\s|$)", re.IGNORECASE),
     "shutdown/halt/reboot : extinction ou redémarrage système"),
    # git push --force / -f vers un remote (peut détruire l'historique partagé).
    # On cible le push force, pas un `git commit` normal. `(?<=\s)-f(?=\s)` évite de
    # matcher `-f` dans un nom de branche ou une option d'une autre commande.
    (re.compile(rf"{_SEP}git\s+push\s+[^\n]*(?:--force|(?<=\s)-f(?=\s))", re.IGNORECASE),
     "git push --force : écrasement potentiel de l'historique distant"),

    # --- Réseau exfiltration / télescopage ---
    # curl/wget pipé dans sh/bash (exécution de code distant sans inspection).
    (re.compile(rf"{_SEP}(?:curl|wget)\s[^\n|]*\|\s*(?:sh|bash|zsh|python3?|perl)(?:\s|$)", re.IGNORECASE),
     "curl/wget | sh : exécution de code distant non inspecté"),
]


def _normalize(cmd: str) -> str:
    r"""Normalise la commande pour le matching : collapse whitespace, strip.

    On ne fait PAS de lowercasing ici (les regex sont IGNORECASE) — on garde
    juste un whitespace stable pour que les patterns `\s+` matchent fiable.
    """
    if not cmd:
        return ""
    # Collapse séries d'espaces/tabs en un seul espace (sans toucher aux newlines,
    # qui sont des séparateurs de commande significatifs pour le guard).
    return re.sub(r"[ \t]+", " ", cmd).strip()


def check_bash_command(cmd: str) -> Tuple[bool, str]:
    """Vérifie une commande bash contre la denylist destructrice.

    Args:
        cmd: La commande telle que générée par le LLM (passée à shell=True).

    Returns:
        (allowed, reason) :
          - allowed=True, reason="" : commande autorisée (passe au subprocess).
          - allowed=False, reason="..." : commande bloquée ; `reason` est un
            message pédagogique à renvoyer au LLM pour qu'il ajuste (pas une
            exception à lever).

    Le guard est volontairement CONSERVATIF : mieux vaut bloquer un cas limite
    et forcer le LLM à reformuler que laisser passer une commande destructrice.
    Les usages légitimes (ex: `rm -rf ./build`) restent autorisés car la
    denylist cible des chemins racines/système, pas les chemins relatifs.
    """
    normalized = _normalize(cmd or "")
    if not normalized:
        return True, ""  # commande vide = laissons subprocess gérer (no-op)

    for pattern, label in _DENY_PATTERNS:
        if pattern.search(normalized):
            return (
                False,
                f"BLOCAGE SÉCURITÉ : cette commande est interdite ({label}). "
                f"L'exécution de commandes destructrices système est bloquée par le guard. "
                f"Si ton intention est légitime, REFORMULE en ciblant un chemin BORNÉ et "
                f"relatif (ex: './build', './dist', 'tests/') plutôt qu'un chemin racine "
                f"ou système. N'utilise JAMAIS rm -rf /, format, mkfs, dd vers un disque, "
                f"shutdown, ou git push --force."
            )
    return True, ""
