#!/usr/bin/env python3
"""
Python Health Audit - Script for running Ruff, Vulture, and Radon
Usage:
    python run_audit.py <target_directory>
"""
import sys
import subprocess
from pathlib import Path

def run_command(cmd, desc):
    print(f"\n--- {desc} ---")
    print(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        out = (result.stdout + "\n" + result.stderr).strip()
        print(out if out else "(No output / All good)")
        return result.returncode
    except Exception as e:
        print(f"Failed to run command: {e}")
        return -1

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_audit.py <target_directory>")
        sys.exit(1)
        
    target = sys.argv[1]
    target_path = Path(target)
    
    if not target_path.exists():
        print(f"Error: Target path {target} does not exist.")
        sys.exit(1)
        
    print(f"Starting Python Health Audit for: {target}")
    
    # Ruff : dead code local
    run_command(["uvx", "ruff", "check", "--select", "F401,F841", target], "Ruff (Local Dead Code / Unused Imports)")
    
    # Vulture : dead code global
    run_command(["uvx", "vulture", target], "Vulture (Global Dead Code)")
    
    # Radon : complexité cyclomatique
    run_command(["uvx", "radon", "cc", target, "-s", "-a"], "Radon (Cyclomatic Complexity)")
    
    # Radon : Maintainability Index
    run_command(["uvx", "radon", "mi", target, "-s"], "Radon (Maintainability Index)")
    
    print("\nAudit completed. Please review the output above to compile the final report.")

if __name__ == "__main__":
    main()
