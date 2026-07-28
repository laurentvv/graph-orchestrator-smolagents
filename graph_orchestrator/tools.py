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
    
    Args:
        path: The absolute or relative path to the file.
        content: The complete content to write into the file.
    """
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote to {path}"
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
