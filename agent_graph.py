"""Entry point mince : délègue au dispatcher workflows.main().

Usage : uv run agent_graph.py

Le mode est piloté par WORKFLOW_MODE (.env / env système) :
  - "one_shot" (défaut) : Fan-out → Reduce → Adversaire → Synth (runner.run_graph_workflow)
  - "exploration"       : boucle Loop-until-dry
  - "coding"            : Architect → Coder → Tester → Judge (multi-agent)
"""
from graph_orchestrator.workflows import main
import os

if __name__ == "__main__":
    main()
    os._exit(0)
