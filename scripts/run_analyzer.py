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

# Défaut du chemin DuckDB : on réutilise la constante canonique du paquet
# (data/graph_orchestrator.db, ancrée au paquet) pour rester cohérent avec le
# runner/agent_server. Fallback si le paquet n'est pas importable (script lancé
# hors venv).
try:
    from graph_orchestrator.config import DEFAULT_KG_PATH as _DEFAULT_KG_PATH
except Exception:
    _DEFAULT_KG_PATH = "data/graph_orchestrator.db"

def parse_log_file(log_path: str):
    print(f"[*] Analyse du log : {log_path}")

    metrics = {
        "total_duration_s": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "nodes": {},
        "errors": [],
        "crashes": [],
        # Signaux qualité & dégradation : problèmes d'infra/outils qui n'étaient
        # pas capturés avant (crash ActionStep/timing, MCP -32602, forbidden
        # function, timeout tester, connection LLM). Détectés post-run pour le
        # Meta-Analyst (F-61). Chaque entrée : {line, node, kind, content}.
        "signals": [],
        # Verdicts Judge : compteurs globaux par issue.
        "judge_approved": 0,
        "judge_rejected": 0,
        # Redémarrages de l'agent Tester : un "Step 1" réapparaît quand l'agent
        # smolagents relance sa boucle (contexte saturé, retry, etc.). Compter
        # ces resets signale un gaspillage de budget tokens/temps.
        "tester_restarts": 0,
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

        # Détection du nœud en cours. On normalise un nom court lisible au lieu
        # de stocker toute la ligne (qui peut faire 80+ caractères et pollue le
        # rapport). Patterns réels observés dans les logs (cf. workflows.py) :
        #   "[*] DSPy Architecte en cours..."          → Architect
        #   "[*] DSPy PromptRefiner en cours..."       → PromptRefiner
        #   "[*] DSPy Routeur en cours..."             → Router
        #   "[>] Itération 1/3 pour ts-001 (Coder)..." → Coder
        #   "[*] Tester polyvalent : techno..."        → Tester
        #   "[*] DSPy Security Reviewer sur..."        → Security
        #   "Audits terminés. Juge ... en cours"       → Judge
        _node_name = None
        if line_clean.startswith("[*] DSPy Architecte"):
            _node_name = "Architect (reasoning)"
        elif line_clean.startswith("[*] DSPy PromptRefiner"):
            _node_name = "PromptRefiner (reasoning)"
        elif line_clean.startswith("[*] DSPy Routeur"):
            _node_name = "Router (fast)"
        elif line_clean.startswith("[*] DSPy Security"):
            _node_name = "Security (reasoning)"
        elif line_clean.startswith("[*] Tester polyvalent") or line_clean.startswith("[*] Tester mode"):
            _node_name = "Tester (fast/multimodal)"
        elif "(Coder)" in line_clean and "Itération" in line_clean:
            _node_name = "Coder (fast/multimodal)"
        elif "Juge" in line_clean and "en cours" in line_clean:
            _node_name = "Judge (reasoning)"
        elif line_clean.startswith("[*] DSPy Nœud d'Escalade"):
            _node_name = "Escalation (reasoning)"

        if _node_name:
            current_node = _node_name
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
        # On exclut :
        #  - les lignes de prompt (bordures Rich '│'/'║') qui citent ces motifs
        #    dans la consigne donnée au LLM, non dans une vraie trace ;
        #  - les 'Forbidden function' : reclassées plus bas dans 'signals' avec
        #    leur cause racine (outil non déclaré), pour éviter le doublon.
        if ("InterpreterError" in line_clean or "SyntaxError" in line_clean or "ValueError" in line_clean):
            if ("│" not in line_clean and "║" not in line_clean
                    and "lèvera une 'SyntaxError'" not in line_clean
                    and "Forbidden function" not in line_clean):
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

        # ── Signaux qualité & dégradation (infra/outils) ─────────────────────
        # On exclut les lignes de prompt Rich (bordures │ ║) qui citent souvent
        # ces motifs dans la consigne donnée au LLM, non dans une vraie trace.
        is_prompt_line = "│" in line_clean or "║" in line_clean

        # Crash framework smolagents : "[-] Erreur interne (Tentative N/3): ..."
        # et "[-] Échec définitif pour <Node> après N tentatives." Le crash le
        # plus critique observé (ActionStep.__init__() missing 'timing', fixé
        # dans compaction.py) passait inaperçu — son préfixe "[-] Erreur interne"
        # n'était pas dans la liste des patterns de crash.
        if line_clean.startswith("[-] Erreur interne") or line_clean.startswith("[-] Échec définitif"):
            metrics["signals"].append({
                "line": i + 1, "node": current_node,
                "kind": "Crash framework (retry/échec définitif)",
                "content": line_clean[:200],
            })

        # Erreur d'outil MCP (Puppeteer/autres) : "MCP error -32602: Input
        # validation error: Invalid arguments for tool ...". Indique que le LLM
        # appelle un outil avec de mauvais arguments (paramètre manquant/typé).
        elif "MCP error -32602" in line_clean:
            metrics["signals"].append({
                "line": i + 1, "node": current_node,
                "kind": "Erreur outil MCP (-32602 validation)",
                "content": line_clean[:200],
            })

        # Forbidden function : l'agent smolagents tente d'appeler une fonction
        # non déclarée (read_file, click, ...) → InterpreterError. L'agent
        # gaspille alors des steps/tokens à tâtonner. À isoler des erreurs de
        # code produit (déjà capturées sous "errors" via InterpreterError) car
        # la cause racine est un mauvais prompt/registry d'outils, pas un bug
        # du code généré.
        elif "Forbidden function" in line_clean and not is_prompt_line:
            metrics["signals"].append({
                "line": i + 1, "node": current_node,
                "kind": "Forbidden function (outil non déclaré)",
                "content": line_clean[:200],
            })

        # Timeout d'un nœud : "[-] Timeout du nœud tester après 600s ...". Le
        # nœud est coupé sans verdict → le Judge poursuit à l'aveugle. Motif
        # précis pour ne PAS attraper le JS setTimeout (faux positifs).
        elif line_clean.startswith("[-] Timeout du nœud"):
            metrics["signals"].append({
                "line": i + 1, "node": current_node,
                "kind": "Timeout de nœud (sans verdict)",
                "content": line_clean[:200],
            })

        # Connection error LLM : "Error in generating model output:" suivi de
        # "Connection error." Le nœud (Security, Judge, ...) échoue par faute
        # infra, pas par logique — angle mort qualité.
        elif "Error in generating model output" in line_clean:
            metrics["signals"].append({
                "line": i + 1, "node": current_node,
                "kind": "Échec génération LLM (connection/infra)",
                "content": line_clean[:200],
            })

        # ── Verdicts Judge ───────────────────────────────────────────────────
        if "APPROUVÉ par le Juge" in line_clean:
            metrics["judge_approved"] += 1
        elif "REJETÉ par le Juge" in line_clean:
            metrics["judge_rejected"] += 1

        # ── Redémarrages du Tester ───────────────────────────────────────────
        # Un "Step 1 ━" qui apparaît alors qu'on est déjà dans le nœud Tester
        # signale un reset de boucle smolagents (retry, contexte saturé...).
        # On compte les "Step 1" survenus APRES le 1er (le initial ne compte pas).
        if current_node == "Tester (fast/multimodal)" and "━ Step 1 ━" in line:
            metrics["tester_restarts"] += 1

    # Le 1er "Step 1" est le démarrage normal, pas un restart : on décrémente.
    if metrics["tester_restarts"] > 0:
        metrics["tester_restarts"] -= 1

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
        f.write(f"- **Tokens (Output)** : {metrics['total_output_tokens']:,}\n")
        f.write(f"- **Verdicts Judge** : {metrics['judge_approved']} approuvé(s) / {metrics['judge_rejected']} rejeté(s)\n")
        f.write(f"- **Redémarrages Tester** : {metrics['tester_restarts']} (un 'Step 1' réapparu = reset de boucle)\n\n")
        
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

        # Regroupement des signaux par kind pour un résumé exécutif clair.
        f.write("\n## ⚠️ Signaux Qualité & Dégradation (infra/outils)\n")
        f.write("Problèmes d'infrastructure ou d'outils (crash framework, MCP, outils interdits, "
                "timeout, connexion LLM) — distincts des bugs de logique du code produit. "
                "Impact typique : nœud sans verdict, Judge à l'aveugle, gaspillage de budget.\n\n")
        if not metrics["signals"]:
            f.write("Aucun signal de dégradation détecté.\n")
        else:
            # Résumé par catégorie (compteurs) puis détail.
            from collections import Counter
            kind_counts = Counter(s["kind"] for s in metrics["signals"])
            f.write("**Résumé par catégorie** :\n")
            for kind, count in kind_counts.most_common():
                f.write(f"- {kind} : **{count}**\n")
            f.write("\n**Détail** (max 20) :\n")
            for sig in metrics["signals"][:20]:
                f.write(f"- **Ligne {sig['line']}** ({sig['node']}) — *{sig['kind']}* : "
                        f"`{sig['content']}`\n")
            if len(metrics["signals"]) > 20:
                f.write(f"- *... et {len(metrics['signals']) - 20} autres signaux non affichés.*\n")
                
    print(f"[+] Rapport généré : {output_path}")

def discover_latest_log(logs_dir: str) -> str | None:
    """Retourne le log le plus récent dans ``logs_dir`` (pattern ``run-*.log``).

    Découverte cross-plateforme (``os.path.join`` + ``glob``) — fini le chemin
    Windows hardcodé (``.gemini/antigravity-cli/brain``) qui cassait le
    Meta-Analyst (F-61) sur Linux/macOS. Les logs sont auto-capturés par
    ``workflows.main()`` via ``run_logging.tee_run_logging``.

    Returns:
        Chemin absolu/relatif du log le plus récent, ou ``None`` si aucun trouvé.
    """
    search_pattern = os.path.join(logs_dir, "run-*.log")
    logs = glob.glob(search_pattern)
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)


def main():
    parser = argparse.ArgumentParser(description="Analyse un log d'agent pour générer un post-mortem.")
    parser.add_argument("--log", type=str, help="Chemin du fichier log (défaut : le plus récent dans --logs-dir)")
    parser.add_argument("--logs-dir", type=str, default=os.environ.get("LOGS_DIR", "logs"),
                        help="Répertoire de découverte auto des logs (défaut : $LOGS_DIR ou 'logs')")
    parser.add_argument("--out", type=str, default="analysis_report.md", help="Fichier de sortie Markdown")
    parser.add_argument("--db", type=str, default=_DEFAULT_KG_PATH, help="Chemin de la base DuckDB (défaut : data/graph_orchestrator.db ancré au paquet)")
    args = parser.parse_args()

    log_file = args.log
    if not log_file:
        # Découverte auto du log le plus récent dans logs/ (chemin cross-plateforme).
        log_file = discover_latest_log(args.logs_dir)
        if not log_file:
            print(f"[-] Aucun log trouvé dans '{args.logs_dir}' (pattern {os.path.join(args.logs_dir, 'run-*.log')}).")
            print(f"    Lancez d'abord un run (`uv run agent_graph.py`) ou précisez --log <chemin>.")
            return
        print(f"[*] Fichier log le plus récent trouvé : {log_file}")
        
    if not os.path.exists(log_file):
        print(f"[-] Le fichier {log_file} n'existe pas.")
        return
        
    metrics = parse_log_file(log_file)
    db_metrics = parse_duckdb(args.db)
    generate_markdown_report(metrics, db_metrics, log_file, args.out)

if __name__ == "__main__":
    main()
