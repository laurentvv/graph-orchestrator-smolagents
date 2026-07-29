import os
import subprocess
from smolagents import tool

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
        return output
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"
