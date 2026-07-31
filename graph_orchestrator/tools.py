import asyncio
import os
import subprocess
from smolagents import tool

from .search_replace_utils import find_similar_lines, replace_most_similar_chunk

# --- Mutex par fichier (anti race-condition) ---------------------------------
# Sérialise les écritures concurrentes sur un MÊME fichier. Inspiré d'openfox
# (src/server/tools/edit.ts : fileLocks Map). Le workflow coding est déjà
# séquentiel, mais bash_command peut écrire hors contrôle Python : ce verrou est
# une défense ceinture+bretelles. Les @tool smolagents sont synchrones et tournent
# dans des threads (asyncio.to_thread) ; on utilise un verrou asynchrone qu'on
# acquiert via asyncio.run / nesté, ou un simple threading.Lock synchrone robuste.
import threading

_FILE_LOCKS: dict[str, threading.Lock] = {}
_FILE_LOCKS_GUARD = threading.Lock()


def _file_lock(path: str) -> threading.Lock:
    """Renvoie (et crée si besoin) le verrou associé à un chemin de fichier normalisé."""
    norm = os.path.normpath(os.path.abspath(path))
    with _FILE_LOCKS_GUARD:
        if norm not in _FILE_LOCKS:
            _FILE_LOCKS[norm] = threading.Lock()
        return _FILE_LOCKS[norm]


@tool
def read_file(path: str, offset: int = 0, limit: int = -1) -> str:
    """Reads a file and returns its content with line numbers.
    Useful for inspecting the codebase before editing.
    
    Args:
        path: The absolute or relative path to the file.
        offset: The starting line number (0-indexed). Defaults to 0.
        limit: The number of lines to read. Set to -1 to read all remaining lines. Defaults to -1.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if limit == -1:
            limit = len(lines)
            
        selected = lines[offset : offset + limit]
        return "".join(f"{offset + i + 1:4}| {line}" for i, line in enumerate(selected))
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"

@tool
def list_directory(path: str = ".") -> str:
    """Lists the contents of a directory.
    Useful for exploring the codebase structure.
    
    Args:
        path: The directory path to list. Defaults to current directory.
    """
    try:
        files = os.listdir(path)
        return f"Contents of {path}:\n" + "\n".join(files)
    except Exception as e:
        return f"Error listing directory {path}: {str(e)}"

@tool
def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file with new content.

    The FULL, real file content MUST go in the `content` argument — never empty,
    never a placeholder. If you describe the content in your reasoning instead of
    passing it here, the file will be created empty and the task will fail.

    Args:
        path: The absolute or relative path to the file. Parent directories are created automatically.
        content: The COMPLETE content to write into the file. Must NOT be empty.
    """
    try:
        # Garde anti-contenu-vide (bug critique des petits modèles : le contenu
        # réel finit dans le raisonnement/prose, pas dans l'argument content).
        # On rejette explicitement et on renvoie un message pédagogique au modèle
        # pour qu'il re-appelle write_file avec le vrai contenu. (gap non couvert
        # par crush/openfox/nanocode, inspiré du pattern openfox FORMAT_CORRECTION.)
        if content is None or not str(content).strip():
            return (
                "ERROR: write_file was called with an EMPTY 'content' argument. "
                "You put the file content in your reasoning/prose instead of in the "
                "'content' argument. Re-call write_file with the COMPLETE, real file "
                "content in the 'content' argument. The file was NOT created."
            )
        # Garde anti-placeholder : un content quasi vide de type "TODO" / "..." est refusé.
        stripped = str(content).strip()
        if len(stripped) < 5 or stripped.lower() in {"...", "todo", "placeholder", "// code here"}:
            return (
                "ERROR: write_file 'content' looks like a placeholder, not real code. "
                "Provide the COMPLETE implementation. The file was NOT created."
            )
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing to file {path}: {str(e)}"


@tool
def append_file(path: str, content: str) -> str:
    """Appends `content` to the END of a file, without rewriting what's already there.

    Use this to BUILD A LARGE FILE INCREMENTALLY: call `write_file` once with the
    skeleton (structure + section markers), then call `append_file` once per
    section. This avoids the truncation/corruption that happens when a single
    `write_file` holds thousands of lines.

    Args:
        path: The file to append to. Created if it does not exist; parent
              directories are created automatically.
        content: The chunk to append. Must NOT be empty or a placeholder.
    """
    try:
        # Garde anti-contenu-vide / anti-placeholder (même logique que write_file).
        if content is None or not str(content).strip():
            return (
                "ERROR: append_file was called with an EMPTY 'content' argument. "
                "Re-call append_file with the real chunk of content to add. "
                "The file was NOT modified."
            )
        if _is_placeholder(str(content)):
            return (
                "ERROR: append_file 'content' looks like a placeholder, not real "
                "code. Provide the COMPLETE section to append. The file was NOT modified."
            )

        # Mutex par fichier (sérialise les appends concurrents, comme write_file/openfox).
        with _file_lock(path):
            # Lecture de l'existant (pour feedback + garde anti-doublon).
            existing = ""
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    existing = f.read()

            # Garde anti-doublon léger (deer-flow read-before-write, version simple) :
            # si le chunk est déjà la fin exacte du fichier, on le signale sans
            # réécrire — évite le bug "section appendée N fois" sans middleware lourd.
            stripped = str(content)
            if existing.endswith(stripped):
                line_count = existing.count("\n") + (0 if existing.endswith("\n") else 1)
                return (
                    f"NOTICE: this content is already at the end of {path} — not "
                    f"re-appended (duplicate guard). File unchanged ({len(existing)} "
                    f"chars, {line_count} lines). Move on to the next section."
                )

            # Append effectif (mode 'a', UTF-8). Le dossier parent doit exister
            # (le mode 'a' crée le fichier, mais pas les dossiers parents).
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                f.write(content)

            # Feedback riche (inspiration SWE-agent ACI : état visible pour le modèle).
            new_total = existing + content
            line_count = new_total.count("\n") + (0 if new_total.endswith("\n") else 1)
            return (
                f"Appended {len(content)} chars to {path}. "
                f"File now {len(new_total)} chars, {line_count} lines."
            )
    except Exception as e:
        return f"Error appending to file {path}: {str(e)}"


@tool
def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Surgically replaces a specific string in a file with a new string.
    The old_string must match exactly, including whitespace and indentation.
    
    Args:
        path: The absolute or relative path to the file.
        old_string: The exact string to find and replace.
        new_string: The replacement string.
        replace_all: If true, replaces all occurrences. If false and multiple occurrences exist, it fails.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if old_string not in content:
            return "Error: old_string not found exactly as written. Ensure indentation and line endings match."
        
        occurrences = content.count(old_string)
        if occurrences > 1 and not replace_all:
            return f"Error: old_string appears {occurrences} times. Must be unique or set replace_all=True."
        
        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return f"Successfully updated {path} ({'all ' + str(occurrences) if replace_all else '1'} occurrences replaced)."
    except Exception as e:
        return f"Error editing file {path}: {str(e)}"

@tool
def bash_command(cmd: str) -> str:
    """Executes a bash shell command. Useful for creating directories, running tests, or checking environment.

    Args:
        cmd: The shell command to execute.
    """
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout
        if result.stderr:
            output += "\nSTDERR:\n" + result.stderr
        if not output.strip():
            output = f"Command executed successfully (exit code {result.returncode}), no output."
        # Troncature anti "Context Overflow" : une commande (ex: tests) peut cracher
        # des centaines de lignes de stderr. On garde tête + queue avant de renvoyer
        # au LLM, sinon le contexte explose (Priorité 2 du plan usine logicielle).
        from .feedback_utils import truncate_output
        return truncate_output(output, head_lines=20, tail_lines=20, max_chars=2000)
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"


# ===========================================================================
# Outil SEARCH/REPLACE tolérant (Priorité 1 du plan usine logicielle)
# ===========================================================================
# Solution au bug de corruption des gros contenus JSON inline : au lieu de faire
# générer au LLM un fichier ENTIER dans un argument JSON (ce que les petits
# modèles corrompent), on lui demande juste le fragment à remplacer (search) et
# son substitut (replace). La logique tolérante (portée d'Aider) accepte les
# imprécisions classiques : indentation différente, lignes vides, ellipses.
# ===========================================================================

# Placeholders interdits dans un bloc replace (garde anti-paresse, Priorité 1).
_PLACEHOLDER_TOKENS = {"...", "todo", "todoreplace", "// code here", "# code here",
                       "placeholder", "<your code>", "<!-- code -->"}


def _is_placeholder(text: str) -> bool:
    """Vrai si le texte de remplacement est un placeholder (placeholder uniquement)."""
    stripped = (text or "").strip().lower()
    if not stripped:
        return True
    # Un replace constitué d'un seul token placeholder, ou d'un commentaire
    # `// ...` / `# ...` / `/* ... */` sans réel contenu.
    return stripped in _PLACEHOLDER_TOKENS


@tool
def search_replace(path: str, search: str, replace: str) -> str:
    """Surgically edits a file by replacing the 'search' block with the 'replace' block.

    PREFER this tool over write_file when modifying an EXISTING file: you only need to
    provide the exact code to find and its replacement, NOT the whole file. This avoids
    truncation/corruption on long files.

    The matching is TOLERANT: minor leading-whitespace differences and `...` ellipses
    in the 'search' block are accepted. If 'search' appears multiple times, the edit fails
    (provide more surrounding lines to make it unique). If it cannot be found, the tool
    returns the closest lines found so you can correct your 'search' block.

    Args:
        path: The file path to edit. Must exist.
        search: The exact block of text to find in the file (copy it verbatim from the file,
            including indentation). Use `...` on its own line to elide unchanged code in the
            middle of the block.
        replace: The new block of text that replaces 'search'. Must be real code, never a
            placeholder like 'TODO' or '// code here'.
    """
    try:
        # Garde anti-placeholder : un replace qui vide/placeholderise le code est refusé.
        if _is_placeholder(replace):
            return ("ERROR: 'replace' looks like a placeholder (TODO, '...', '// code here', "
                    "empty). Provide the COMPLETE real replacement code. File NOT modified.")

        lock = _file_lock(path)
        with lock:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

            # 'search' vide = ajout en fin de fichier (utile pour compléter un fichier).
            if not search.strip():
                new_content = original
                if new_content and not new_content.endswith("\n"):
                    new_content += "\n"
                new_content += replace
            else:
                new_content = replace_most_similar_chunk(original, search, replace)

            if new_content is None:
                # Échec : feedback pédagogique avec les lignes les plus proches.
                hint = find_similar_lines(search, original)
                msg = (
                    "ERROR: the 'search' block was NOT found in the file (even with tolerant "
                    "matching). The file was NOT modified. Copy the exact text FROM the file "
                    "(use read_file first), including indentation."
                )
                if hint:
                    msg += (
                        "\n\nClosest lines found in the file (use these verbatim as your "
                        "'search' block):\n" + hint
                    )
                return msg

            # Refus d'écrire si le résultat est vide (sécurité anti-effacement).
            if not new_content.strip():
                return ("ERROR: the edit would empty the file. Aborting. File NOT modified.")

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

        return f"Successfully edited {path} via SEARCH/REPLACE."
    except FileNotFoundError:
        return (f"ERROR: file '{path}' does not exist. Use write_file to CREATE a new file, "
                "or check the path.")
    except Exception as e:
        return f"Error editing file {path}: {str(e)}"

