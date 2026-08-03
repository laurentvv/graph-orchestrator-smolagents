#!/usr/bin/env python3
"""
F-60: run_analyzer.py
Parse les logs d'exécution (et potentiellement DuckDB) pour extraire des métriques (temps, tokens, erreurs)
et générer un rapport post-mortem Markdown afin d'améliorer l'agent.
"""
import os
import re
import glob
import json
import argparse
from datetime import datetime

def parse_log_file(log_path: str):
    print(f"[*] Analyse du log : {log_path}")
    
    metrics = {
        "total_duration_s": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "nodes": {},
        "errors": [],
        "crashes": []
    }
    
    current_node = None
    node_starts = {}
    
    # Regex pour les metrics de step
    # Ex: [Step 1: Duration 48.49 seconds| Input tokens: 15,513 | Output tokens: 2,580]
    step_pattern = re.compile(r"\[Step \d+: Duration ([\d.]+) seconds(?:\| Input tokens: ([\d,]+) \| Output tokens: ([\d,]+))?\]")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines):
        line_clean = line.strip()
        
        # Détection du nœud en cours
        if "[*] DSPy" in line_clean or "[*] Code Judge" in line_clean:
            current_node = line_clean
            if current_node not in metrics["nodes"]:
                metrics["nodes"][current_node] = {
                    "duration_s": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "steps": 0
                }
                
        # Parsing des metrics de l'étape
        match = step_pattern.search(line_clean)
        if match:
            duration = float(match.group(1))
            in_tok = int(match.group(2).replace(',', '')) if match.group(2) else 0
            out_tok = int(match.group(3).replace(',', '')) if match.group(3) else 0
            
            metrics["total_duration_s"] += duration
            metrics["total_input_tokens"] += in_tok
            metrics["total_output_tokens"] += out_tok
            
            if current_node:
                metrics["nodes"][current_node]["duration_s"] += duration
                metrics["nodes"][current_node]["input_tokens"] += in_tok
                metrics["nodes"][current_node]["output_tokens"] += out_tok
                metrics["nodes"][current_node]["steps"] += 1
                
        # Détection d'erreurs d'exécution de code ou SyntaxError
        # On exclut les lignes de prompt (qui contiennent souvent '│' ou '║' dues aux bordures Rich)
        if ("InterpreterError" in line_clean or "SyntaxError" in line_clean or "ValueError" in line_clean):
            if "│" not in line_clean and "║" not in line_clean and "lèvera une 'SyntaxError'" not in line_clean:
                metrics["errors"].append({
                    "line": i + 1,
                    "node": current_node,
                    "content": line_clean[:200]
                })
            
        # Crash framework / LLM / DSPy
        if "[-] Pydantic a échoué" in line_clean or "[-] Le sauvetage DSPy" in line_clean or "Traceback (" in line_clean:
            metrics["crashes"].append({
                "line": i + 1,
                "node": current_node,
                "content": line_clean[:200]
            })
            
        # Tests échoués
        if "Observation" in line_clean and "FAIL" in line_clean:
            metrics["errors"].append({
                "line": i + 1,
                "node": current_node,
                "content": line_clean[:200]
            })

    return metrics

def parse_duckdb(db_path: str):
    metrics = {"entities": 0, "claims": 0, "open_claims": 0}
    if not os.path.exists(db_path):
        return metrics
        
    try:
        import duckdb
        conn = duckdb.connect(db_path, read_only=True)
        metrics["entities"] = conn.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
        metrics["claims"] = conn.execute("SELECT COUNT(*) FROM claim").fetchone()[0]
        metrics["open_claims"] = conn.execute("SELECT COUNT(*) FROM claim WHERE status='open'").fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"[-] DuckDB inaccessible (peut-être verrouillé par un run en cours) : {e}")
        
    return metrics

def generate_markdown_report(metrics: dict, db_metrics: dict, log_path: str, output_path: str):
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Rapport d'Analyse Post-Mortem\n")
        f.write(f"**Source** : `{log_path}`\n")
        f.write(f"**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 📊 Métriques Globales\n")
        f.write(f"- **Durée totale (steps)** : {metrics['total_duration_s']:.2f} s\n")
        f.write(f"- **Tokens (Input)** : {metrics['total_input_tokens']:,}\n")
        f.write(f"- **Tokens (Output)** : {metrics['total_output_tokens']:,}\n\n")
        
        f.write("## 🗄️ Base de Connaissances (DuckDB)\n")
        f.write(f"- **Entités créées** : {db_metrics['entities']}\n")
        f.write(f"- **Revendications (Claims)** : {db_metrics['claims']} (dont {db_metrics['open_claims']} 'open')\n\n")
        
        f.write("## 🏗️ Répartition par Nœud\n")
        f.write("| Nœud | Étapes | Durée (s) | Input Tokens | Output Tokens |\n")
        f.write("|------|--------|-----------|--------------|---------------|\n")
        for node, m in metrics["nodes"].items():
            name = node.replace("|", "").strip()[:50]
            f.write(f"| `{name}` | {m['steps']} | {m['duration_s']:.2f} | {m['input_tokens']:,} | {m['output_tokens']:,} |\n")
            
        f.write("\n## 🚨 Erreurs de Logique / Syntaxe\n")
        if not metrics["errors"]:
            f.write("Aucune erreur détectée.\n")
        else:
            for err in metrics["errors"][:15]:
                f.write(f"- **Ligne {err['line']}** ({err['node']}) : `{err['content']}`\n")
            if len(metrics["errors"]) > 15:
                f.write(f"- *... et {len(metrics['errors']) - 15} autres erreurs non affichées.*\n")
                
        f.write("\n## 💥 Crashes Framework & LLM (Sauvetage, Pydantic, Exceptions)\n")
        if not metrics["crashes"]:
            f.write("Aucun crash détecté.\n")
        else:
            for crash in metrics["crashes"]:
                f.write(f"- **Ligne {crash['line']}** ({crash['node']}) : `{crash['content']}`\n")
                
    print(f"[+] Rapport généré : {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Analyse un log d'agent pour générer un post-mortem.")
    parser.add_argument("--log", type=str, help="Chemin du fichier log (défaut : le plus récent dans .system_generated/tasks/)")
    parser.add_argument("--out", type=str, default="analysis_report.md", help="Fichier de sortie Markdown")
    parser.add_argument("--db", type=str, default="graph_orchestrator.db", help="Chemin de la base DuckDB")
    args = parser.parse_args()
    
    log_file = args.log
    if not log_file:
        # Chercher le log le plus récent
        base_dir = r"C:\Users\lvolff\.gemini\antigravity-cli\brain"
        # On cherche tous les répertoires de conversation, puis les logs
        search_pattern = os.path.join(base_dir, "*", ".system_generated", "tasks", "task-*.log")
        logs = glob.glob(search_pattern)
        if not logs:
            print(f"[-] Aucun fichier log trouvé avec le pattern {search_pattern}")
            return
        log_file = max(logs, key=os.path.getmtime)
        print(f"[*] Fichier log le plus récent trouvé : {log_file}")
        
    if not os.path.exists(log_file):
        print(f"[-] Le fichier {log_file} n'existe pas.")
        return
        
    metrics = parse_log_file(log_file)
    db_metrics = parse_duckdb(args.db)
    generate_markdown_report(metrics, db_metrics, log_file, args.out)

if __name__ == "__main__":
    main()
