"""Normalisation des chemins passés aux outils (MA-5 / F-97).

Contexte : sur win32 + Git Bash (MSYS), un petit LLM mélange deux formats incompatibles :
- `file:///D:/GIT/...` est CORRECT pour `navigate_page` (Chrome l'accepte comme URL),
  mais FATAL pour `read_file` / `list_directory` (Python ``open()`` / ``os.listdir()``
  → ``[Errno 22] Invalid argument``).
- `/d/GIT/...` (préfixe MSYS) → ``[WinError 123]`` côté Python.

Le modèle copie souvent le même token (fourni dans le prompt sous forme de ``file:///``)
dans les deux outils. Plutôt que de compter uniquement sur le prompt (doctrine F-33 :
« un prompt seul ne suffit jamais »), on normalise en tête des outils fichier.

Principes :
- **Pur chaîne, SANS ``os.path.abspath``** : on préserve les chemins relatifs
  (``index.html``) — sinon on casserait la résolution CWD du run dir ET le hashing
  du Read-Before-Write Gate (F-67, ``read_gate._normalize_path`` absorbe lui-même).
- **Fail-open** : tout ce qui ne matche pas un schéma connu est laissé tel quel.
  La validation smolagents reste l'arbitre final ; aucune corruption silencieuse.
- **Aucune règle ``^([a-zA-Z])/`` sans slash initial** : on ne touche jamais un chemin
  qui ne commence pas par ``/`` ou ``file:`` (sinon ``src/a.js`` deviendrait ``S:/rc/a.js``).
"""

from __future__ import annotations

import re

# file:///, file://, file:/  (insensible à la casse)
_FILE_SCHEME = re.compile(r"^file:/+", re.IGNORECASE)
# /D:/...  ou  /D:\...  (slash initial + lettre + deux-points + séparateur)
_LEADING_SLASH_DRIVE = re.compile(r"^/([a-zA-Z]:[\\/].*)$")
# /d/GIT/...  (forme MSYS : slash initial + 1 lettre + slash)
_MSYS_DRIVE = re.compile(r"^/([a-zA-Z])/(.*)$")


def normalize_tool_path(path: str) -> str:
    """Normalise un chemin d'outil : strip ``file://`` et résout les préfixes MSYS.

    Transformations (dans l'ordre, fail-open) :
      1. ``file:///D:/a.html`` / ``file://D:/a.html`` / ``file:/D:/a.html`` → ``D:/a.html``
      2. ``/D:/a.html`` (slash initial devant une lettre+``:``) → ``D:/a.html``
      3. ``/d/GIT/a.html`` (MSYS) → ``D:/GIT/a.html``

    Laissé inchangé (volontairement) :
      - chemins relatifs (``index.html``, ``src/a.js``) — préserve la résolution CWD ;
      - backslash ``D:\\GIT\\a.html`` — déjà valide sous Windows ;
      - chemins déjà corrects ``D:/GIT/a.html`` ;
      - valeurs non-chaîne / vides (renvoyées telles quelles).

    Args:
        path: argument ``path`` brut reçu par l'outil (peut venir d'un LLM).

    Returns:
        Chemin normalisé (ou inchangé si non reconnu). Jamais d'exception.
    """
    if not isinstance(path, str) or not path:
        return path

    p = path.strip()

    # 1. Strip du schéma file:// (variantes 1/2/3 slashes)
    m = _FILE_SCHEME.match(p)
    if m:
        p = p[m.end():]

    # 2. /D:/...  → D:/...  (slash initial parasite devant une lettre + deux-points)
    m = _LEADING_SLASH_DRIVE.match(p)
    if m:
        return m.group(1)

    # 3. /d/...  → D:/...  (préfixe MSYS Git Bash)
    m = _MSYS_DRIVE.match(p)
    if m:
        return m.group(1).upper() + ":/" + m.group(2)

    # Rien reconnu → on renvoie la chaîne éventuellement déséquivée (fail-open).
    return p
