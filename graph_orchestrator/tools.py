import os
import re
import subprocess
from smolagents import tool

from .idempotency import get_current_store, make_op_key
from .io_guard import ensure_read_allowed, ensure_write_allowed
from .path_utils import normalize_tool_path
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

# --- Suivi d'état pour introspection (Coder) ---------------------------------
# Trace les erreurs internes rencontrées par l'agent lors de la tentative précédente
_RUN_ERRORS: list[str] = []

def record_run_error(error_msg: str) -> None:
    """Enregistre une erreur interne pour introspection future par l'agent."""
    _RUN_ERRORS.append(error_msg)


@tool
def check_run_state() -> str:
    """Checks the internal state of the current node execution.
    If you previously crashed (e.g., due to a JSON parsing error, timeout, or Python syntax error),
    this tool will return the exact errors you encountered in the previous attempts.
    Always call this BEFORE creating files if you suspect you are in a retry loop.
    
    Returns:
        A string describing the errors encountered in previous attempts, or a message saying no errors occurred.
    """
    if not _RUN_ERRORS:
        return "Aucune erreur enregistrée. C'est votre première tentative ou tout s'est bien passé jusqu'ici."
    
    report = "ERREURS LORS DES TENTATIVES PRÉCÉDENTES :\n"
    for i, err in enumerate(_RUN_ERRORS, 1):
        report += f"[{i}] {err}\n"
    report += "\nSi l'erreur précédente était liée à final_answer ou au formatage (ex: parsing JSON), les fichiers que tu as créés juste avant le crash SONT PROBABLEMENT DÉJÀ SUR LE DISQUE. Ne les recrée pas !\n"
    report += "Passe directement à la suite en appelant SIMPLEMENT en Python :\n"
    report += "final_answer({'task_id': 'ton_task_id', 'status': 'success', 'details': 'Fichiers récupérés intacts après crash du LLM.'})"
    return report


# F-109 : audit visuel MATÉRIALISÉ — le Coder doit appeler visual_check pour
# CHAQUE critère de validation visuelle après le screenshot. Sans appel,
# final_answer est bloqué logiciellement (nodes.py) : fini le « all criteria
# verified » déclaratif du 4B (run #5 : il déclarait 6/6 puis le Tester
# trouvait un crash). Pattern « evidence exigée » (fiche 46, tool-ralph).
_VISUAL_AUDIT: list[dict] = []


def reset_visual_audit() -> None:
    """Réinitialise l'audit visuel (une exécution de nœud Coder = un audit)."""
    _VISUAL_AUDIT.clear()


def get_visual_audit() -> list[dict]:
    """Copie de l'audit visuel courant (consommé par l'enforcement nodes.py)."""
    return list(_VISUAL_AUDIT)


@tool
def visual_check(criterion_number: int, verdict: bool, observation: str) -> str:
    """À appeler pour CHAQUE critère de validation visuelle, APRÈS le screenshot.

    Matérialise ton audit critère par critère : sans ces appels, final_answer
    sera REFUSÉ (checklist incomplète). Chaque observation doit dire ce que tu
    VOIS concrètement sur la capture — pas une généralité.

    Args:
        criterion_number: le numéro du critère dans la liste (1, 2, 3...).
        verdict: True si le critère est VÉRIFIÉ sur ta capture, False sinon.
        observation: ce que tu vois concrètement (1 phrase factuelle).
    """
    entry = {
        "criterion_number": int(criterion_number),
        "verdict": bool(verdict),
        "observation": str(observation or "").strip(),
    }
    _VISUAL_AUDIT.append(entry)
    etat = "VÉRIFIÉ ✓" if entry["verdict"] else "ÉCHEC ✗ — corrige le code puis ré-audite ce critère"
    return f"[visual_check {entry['criterion_number']}/{len(_VISUAL_AUDIT)}] {etat} : {entry['observation'][:120]}"


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
    # F-97 / MA-5 : un petit LLM passe parfois un `file:///` URL (correct pour
    # navigate_page mais fatal à open()) ou un préfixe MSYS `/d/...`. On normalise.
    path = normalize_tool_path(path)
    # F-95 : cloisonnement IO — hors des racines autorisées (run dir en prod),
    # refus pédagogique. Fail-open si aucune racine enregistrée.
    _denied = ensure_read_allowed(path)
    if _denied:
        return _denied
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
def read_python_skeleton(path: str) -> str:
    """Reads a Python file and returns its skeleton (classes, functions signatures, constants) 
    while hiding the implementation bodies.
    Useful for quickly understanding the structure of a large Python module without using too much context window.
    
    Args:
        path: The absolute or relative path to the Python file.
    """
    # F-97 / F-95 : normalisation du chemin + cloisonnement IO (fail-open).
    path = normalize_tool_path(path)
    _denied = ensure_read_allowed(path)
    if _denied:
        return _denied
    try:
        from .skeleton import get_skeleton
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()
        return get_skeleton(code)
    except Exception as e:
        return f"Error generating skeleton for {path}: {str(e)}"


@tool
def check_js_syntax(path: str) -> str:
    """Vérifie instantanément la syntaxe d'un fichier JavaScript via `node --check`.
    Retourne un message ✅ si la syntaxe est valide, ou ❌ avec l'erreur du parseur
    (ligne/colonne) s'il y a une SyntaxError. À appeler AVANT final_answer sur tout
    fichier .js généré ou modifié : c'est 1 step et ça évite un rejet du Linter.
    Dégradation gracieuse : si `node` est absent du PATH, retourne un message
    informatif (ne bloque pas l'agent — le Linter/Static Tester prend le relais).

    Args:
        path: Chemin du fichier JavaScript à valider (relatif ou absolu).
    """
    import shutil

    # F-97 / F-95 : normalisation + cloisonnement IO (fail-open).
    path = normalize_tool_path(path)
    _denied = ensure_read_allowed(path)
    if _denied:
        return _denied
    if shutil.which("node") is None:
        return f"ℹ️ `node` non disponible — vérification de syntaxe ignorée pour {path}."
    try:
        from .js_utils import run_node_check, MAX_JS_CHARS

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            js = f.read()
    except OSError as e:
        return f"Erreur de lecture de {path} : {str(e)}"
    if len(js) > MAX_JS_CHARS:
        js = js[:MAX_JS_CHARS]  # sécurité : éviter une ligne de commande trop longue.
    code, stderr = run_node_check(js)
    if code == 0:
        return f"✅ Syntaxe JS valide : {path}"
    return f"❌ Erreur de syntaxe dans {path} :\n{stderr.strip()[:2000]}"

@tool
def list_directory(path: str = ".") -> str:
    """Lists the contents of a directory.
    Useful for exploring the codebase structure.
    
    Args:
        path: The directory path to list. Defaults to current directory.
    """
    path = normalize_tool_path(path)
    # F-95 : cloisonnement IO (fail-open).
    _denied = ensure_read_allowed(path)
    if _denied:
        return _denied
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
        # F-97 / F-95 : normalisation + cloisonnement IO — le Coder ne peut pas
        # écrire hors du dossier du run (échec par défaut = périmètre, avant
        # toute autre garde). Fail-open si aucune racine enregistrée.
        path = normalize_tool_path(path)
        _denied = ensure_write_allowed(path)
        if _denied:
            return _denied
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
        
        # Garde anti-squelette HTML (bug "incremental" des petits modèles distants).
        if bool(re.search(r"<body[^>]*>\s*(?:<!--.*?-->\s*)*</body>", stripped, re.IGNORECASE | re.DOTALL)) or (
            path.endswith(".html") and len(stripped) < 200 and "<html" in stripped.lower()
        ):
            return (
                "ERROR: write_file 'content' is an empty HTML skeleton. "
                "The incremental strategy (skeleton + appends) is forbidden here. "
                "You MUST generate and provide the COMPLETE file content (HTML + CSS + JS) "
                "in this single write_file call. The file was NOT created."
            )
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # Garde anti-imbrication du dossier de run (bug observé run 2026-08-05_1546) :
        # le Coder s'exécute DANS le dossier de run (après _scoped_chdir), mais il
        # écrit parfois avec le chemin relatif au repo root (ex:
        # "runs/2026-..._bubble_sort/index.html") → créant un sous-dossier imbriqué
        # "runs/.../runs/.../index.html". La validation visuelle navigate_page pointe
        # alors vers runs/.../index.html (inexistant) → ERR_FILE_NOT_FOUND → run KO.
        # Détection déterministe sur l'ABSPATH (pas le path brut) : depuis le run dir,
        # path="runs/<run>/index.html" → abspath "repo/runs/<run>/runs/<run>/index.html"
        # qui contient "runs/<X>/runs/". On refuse et on oriente vers le chemin court.
        abs_path = os.path.abspath(path).replace("\\", "/")
        if re.search(r"(^|/)runs/[^/]+/runs/", abs_path):
            short = os.path.basename(path)
            return (
                f"ERROR: chemin imbriqué détecté — '{path}' créerait un sous-dossier "
                f"runs/.../runs/... (bug d'imbrication du dossier de run). Ton dossier "
                f"de travail EST déjà le dossier de run. Utilise le chemin COURT : "
                f"'{short}'. Le fichier N'A PAS été créé."
            )
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
        # F-97 / F-95 : normalisation + cloisonnement IO (fail-open).
        path = normalize_tool_path(path)
        _denied = ensure_write_allowed(path)
        if _denied:
            return _denied
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
            # Réparation HTML : si le fichier existant finit par </body></html>, le
            # contenu à appendu arriverait APRÈS la fermeture → texte brut dans le
            # navigateur. On déplace la fermeture après le nouveau contenu (déterministe).
            def _do_append() -> None:
                parent = os.path.dirname(os.path.abspath(path))
                if parent:
                    os.makedirs(parent, exist_ok=True)
                new_existing, new_content = _html_repair_on_append(existing, content)
                if new_existing != existing:
                    # Cas HTML : on réécrit tout le fichier (existing amputé + content + fermeture).
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_existing)
                        f.write(new_content)
                else:
                    # Cas nominal : simple append à la fin.
                    with open(path, 'a', encoding='utf-8') as f:
                        f.write(content)

            # Idempotence des effets de bord (Priorité 8-bis) : au replay de
            # checkpoint, le Coder rejoue ses appends. La garde anti-doublon
            # ci-dessus (content == fin du fichier) ne couvre que le cas où
            # RIEN n'a été appendé depuis. Si un append ULTÉRIEUR a déplacé la
            # fin du fichier, l'anti-doublon ne voit plus le dup → double-append
            # réel. Le store d'idempotence (backing DuckDB, indexé par
            # run_id+hash(path+content)) garantit qu'un append déjà appliqué
            # CE RUN n'est jamais ré-appliqué, même après crash/replay. Si pas
            # de store (scripts standalone / opt-out) → comportement historique.
            _idem_store = get_current_store()
            if _idem_store is not None and _idem_store.run_id:
                _idem_key = make_op_key(
                    _idem_store.run_id, "append", os.path.abspath(path), content
                )
                _ran = _idem_store.once(_idem_key, _do_append)
                if not _ran:
                    line_count = existing.count("\n") + (
                        0 if existing.endswith("\n") else 1
                    )
                    return (
                        f"NOTICE: this append to {path} was already applied "
                        f"earlier in this run (idempotent replay guard) — not "
                        f"re-appended. File unchanged ({len(existing)} chars, "
                        f"{line_count} lines)."
                    )
            else:
                _do_append()

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
    # F-97 / F-95 : normalisation + cloisonnement IO (fail-open).
    path = normalize_tool_path(path)
    _denied = ensure_write_allowed(path)
    if _denied:
        return _denied
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
        # P8-bis (Guard denylist) : avant tout shell=True, on bloque les commandes
        # manifestement destructrices (rm -rf /, format, mkfs, dd vers un disque,
        # shutdown, git push --force...). Le LLM peut halluciner ou se montrer
        # "zélé" ; un CodeAgent exécute du Python arbitraire, donc bash_command
        # est exposé. Le guard renvoie un message pédagogique au lieu d'exécuter.
        # Opt-out via BASH_GUARD_ENABLED=false pour les environnements de confiance.
        # La lecture du settings se fait à l'appel (pas à l'import) pour rester
        # réactif à un changement d'env en cours de session (ex: tests).
        from .config import settings
        from .bash_guard import check_bash_command
        if getattr(settings, "bash_guard_enabled", True):
            allowed, reason = check_bash_command(cmd)
            if not allowed:
                return reason

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

# --- Réparation auto HTML sur append_file (anti "contenu après </html>") --------
# Failure mode observé en réel (run Bubble Sort) : le Coder fait write_file(squelette
# COMPLET avec </body></html>) puis append_file(css) puis append_file(js). Le contenu
# appendu arrive APRÈS </html> → le navigateur l'affiche en texte brut. Le Linter le
# détecte ("contenu après </html>") mais le petit modèle (gemma) ne sait pas le corriger
# proprement → boucle de frustration.
# Réparation déterministe (0 LLM) : si le fichier se termine par </html> (avec </body>
# optionnel + whitespace), on SUPPRIME cette fermeture de l'existant et on la REPOSE à
# la fin du nouveau contenu. Le document reste bien formé, le contenu est à sa place.
# Transparent : si le fichier ne finit pas par </html>, comportement inchangé.
_HTML_CLOSE_RE = re.compile(
    r"[ \t\r\n]*(?:</body>[ \t\r\n]*)?</html>[ \t\r\n]*$",
    re.IGNORECASE | re.DOTALL,
)


def _html_repair_on_append(existing: str, content: str) -> tuple[str, str]:
    """Si 'existing' finit par </body></html>, déplace la fermeture après 'content'.

    Renvoie (new_existing, new_content) :
    - Si pas de fermeture HTML en fin de fichier → (existing, content) inchangés.
    - Sinon → existing amputé de la fermeture + content enrichi de la fermeture à la fin.
    Le format de fermeture détecté (</body></html> ou </html> seul, casse/whitespace)
    est préservé tel quel dans le content de sortie.
    """
    match = _HTML_CLOSE_RE.search(existing)
    if not match:
        return existing, content
    closing = match.group(0)  # la fermeture exacte (avec son whitespace interne)
    new_existing = existing[: match.start()].rstrip() + "\n"
    new_content = content.rstrip() + "\n" + closing.lstrip() + "\n"
    return new_existing, new_content


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
def search_replace(path: str, old_string: str, new_string: str) -> str:
    """Surgically edits a file by replacing the 'old_string' block with the 'new_string' block.

    PREFER this tool over write_file when modifying an EXISTING file: you only need to
    provide the exact code to find and its replacement, NOT the whole file. This avoids
    truncation/corruption on long files.

    The matching is TOLERANT: minor leading-whitespace differences and `...` ellipses
    in the 'old_string' block are accepted. If 'old_string' appears multiple times, the edit
    fails (provide more surrounding lines to make it unique). If it cannot be found, the tool
    returns the closest lines found so you can correct your 'old_string' block.

    Args:
        path: The file path to edit. Must exist.
        old_string: The exact block of text to find in the file (copy it verbatim from the file,
            including indentation). Use `...` on its own line to elide unchanged code in the
            middle of the block.
        new_string: The new block of text that replaces 'old_string'. Must be real code, never a
            placeholder like 'TODO' or '// code here'.
    """
    # F-97 / F-95 : normalisation + cloisonnement IO (fail-open).
    path = normalize_tool_path(path)
    _denied = ensure_write_allowed(path)
    if _denied:
        return _denied
    try:
        # Garde anti-placeholder : un new_string qui vide/placeholderise le code est refusé.
        if _is_placeholder(new_string):
            return ("ERROR: 'new_string' looks like a placeholder (TODO, '...', '// code here', "
                    "empty). Provide the COMPLETE real replacement code. File NOT modified.")

        lock = _file_lock(path)
        with lock:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

            # 'old_string' vide = ajout en fin de fichier (utile pour compléter un fichier).
            if not old_string.strip():
                new_content = original
                if new_content and not new_content.endswith("\n"):
                    new_content += "\n"
                new_content += new_string
            else:
                new_content = replace_most_similar_chunk(original, old_string, new_string)

            if new_content is None:
                # Échec : feedback pédagogique avec les lignes les plus proches.
                hint = find_similar_lines(old_string, original)
                msg = (
                    "ERROR: the 'old_string' block was NOT found in the file (even with tolerant "
                    "matching). The file was NOT modified. Copy the exact text FROM the file "
                    "(use read_file first), including indentation."
                )
                if hint:
                    msg += (
                        "\n\nClosest lines found in the file (use these verbatim as your "
                        "'old_string' block):\n" + hint
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


@tool
def multi_replace(path: str, replacements: list) -> str:
    """Applies multiple search/replace operations to a file safely without rewriting it entirely.
    
    PREFER this tool over write_file when modifying an EXISTING file with multiple edits: 
    you provide the exact code to find and its replacement for several blocks at once.

    Args:
        path: The file path to edit. Must exist.
        replacements: A list of dictionaries, each containing 'old_string' and 'new_string'.
            Example: [{"old_string": "foo()", "new_string": "bar()"}, ...]
            The 'old_string' is matched tolerantly.
    """
    # F-97 / F-95 : normalisation + cloisonnement IO (fail-open).
    path = normalize_tool_path(path)
    _denied = ensure_write_allowed(path)
    if _denied:
        return _denied
    try:
        if not replacements or not isinstance(replacements, list):
            return "ERROR: 'replacements' must be a non-empty list of dictionaries."
            
        lock = _file_lock(path)
        with lock:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                
            success_count = 0
            errors = []
            
            for i, rep in enumerate(replacements):
                old_str = rep.get("old_string", "")
                new_str = rep.get("new_string", "")
                
                if _is_placeholder(new_str):
                    errors.append(f"Block {i}: 'new_string' is a placeholder. Skipping.")
                    continue
                    
                if not old_str.strip():
                    # Append if old_string is empty
                    if content and not content.endswith("\n"):
                        content += "\n"
                    content += new_str
                    success_count += 1
                else:
                    new_content = replace_most_similar_chunk(content, old_str, new_str)
                    if new_content is None:
                        hint = find_similar_lines(old_str, content)
                        err_msg = f"Block {i}: 'old_string' not found."
                        if hint:
                            err_msg += f" Closest match:\n{hint}"
                        errors.append(err_msg)
                    else:
                        content = new_content
                        success_count += 1
                        
            if success_count == 0:
                return "ERROR: No replacements were successful.\n" + "\n".join(errors)
                
            if not content.strip():
                return "ERROR: The edits would empty the file. Aborting. File NOT modified."
                
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
                
        msg = f"Successfully applied {success_count}/{len(replacements)} replacements to {path}."
        if errors:
            msg += "\nSome errors occurred:\n" + "\n".join(errors)
        return msg
        
    except FileNotFoundError:
        return (f"ERROR: file '{path}' does not exist. Use write_file to CREATE a new file.")
    except Exception as e:
        return f"Error editing file {path}: {str(e)}"

@tool
def log_event(event_type: str, details: str) -> str:
    """Logs a major event in the execution history.
    Use this to keep a trace of the execution instead of writing to a text file.
    
    Args:
        event_type: The type of event (e.g., 'init', 'gen', 'eval', 'fix', 'error').
        details: A description of the event.
    """
    try:
        from .idempotency import get_current_store
        from .event_stream import get_event_db
        store = get_current_store()
        run_id = store.run_id if (store and store.run_id) else "unknown_run"
        
        db = get_event_db()
        db.log_event(run_id, "agent", event_type, details)
        return "Event logged successfully."
    except Exception as e:
        return f"Error logging event: {str(e)}"

@tool
def search_and_install_skill(query: str, author: str = None, triggers: str = None) -> str:
    """Recherche et installe un skill depuis le registre skills.sh (skills.sh by Vercel Labs).

    Usage typique : quand le cahier des charges nécessite une compétence spécialisée
    absente du catalogue local (ex: 'react', 'tailwind', 'seo', 'gsap'), cherche un
    skill pertinent, vérifie qu'il vient d'un auteur de confiance + présente un
    signal de sécurité skills.sh (safe/verified), l'installe dans skills/, puis
    enregistre une ligne regex dédiée (mots-clés déclencheurs) pour que le Coder le
    reconnaisse comme les autres skills. Fail-open : ne lève jamais.

    Args:
        query: Le mot-clé de recherche (ex: 'react', 'tailwind', 'seo').
        author: Optionnel. Auteur/owner à filtrer (ex: 'vercel-labs'). Doit être dans
            l'allowlist de confiance (SKILL_FINDER_TRUSTED_AUTHORS).
        triggers: Optionnel. Mots-clés déclencheurs séparés par virgule (ex:
            'react,jsx,hooks') proposés pour la ligne regex. Complété automatiquement
            par extraction depuis la description du skill si non fourni.
    """
    from .skill_finder import search_and_install

    hints = [t.strip() for t in triggers.split(",")] if triggers else None
    # Settings récupéré au plus tard (import différé pour éviter cycle au chargement).
    try:
        from .config import settings
    except Exception:
        settings = None
    return search_and_install(query, author=author, triggers=hints, settings=settings)
