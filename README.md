# 🧠 Graph Orchestrator : L'Usine Logicielle Autonome

[![Status](https://img.shields.io/badge/Status-Production_Ready-success.svg)](#)
[![Stack](https://img.shields.io/badge/Stack-DSPy_3.0_%7C_smolagents_%7C_MCP-blue.svg)](#)

Bienvenue dans le **Graph Orchestrator**. Ceci n'est pas un énième chatbot IA qui génère du code au kilomètre et s'arrête à la première erreur. C'est **une véritable équipe d'ingénierie autonome**, orchestrée par des graphes, dotée d'une mémoire persistante, et conçue pour résoudre des tâches complexes de bout en bout sans la moindre intervention humaine.

Si vous avez déjà été frustré par des agents qui "tournent en rond" (Agent Loops), qui modifient du code à l'aveugle, ou qui oublient le cahier des charges en cours de route, cette architecture a été pensée *exactement* pour vous.

---

## 🚀 Pourquoi cette usine logicielle est unique au monde ?

L'écrasante majorité des agents de code existants (Roo Code, Cline, Devin) reposent sur une seule IA surpuissante qui doit tout faire : planifier, coder, tester, et s'auto-évaluer. Cela conduit inévitablement à un effondrement du contexte et à de l'aveuglement cognitif. 

Le Graph Orchestrator brise ce plafond de verre grâce au paradigme **"Brains vs Hands"** (Les Cerveaux et les Mains) :

### 1. 🧠 Les Cerveaux (DSPy) pensent l'Architecture
Nous confions la réflexion à des modèles de raisonnement profonds (Chain of Thought, 32k tokens). 
L'**Architecte**, le **Juge** et l'expert en **Sécurité** ne tapent jamais de code. Ils décomposent mathématiquement le besoin, rédigent des schémas JSON Pydantic ultra-stricts (sans halluciner), et valident impitoyablement les livrables. 

### 2. 🛠️ Les Mains (smolagents) agissent sur le Terrain
Pour chaque sous-tâche, un nœud **Coder** (modèle rapide) est réveillé. Il reçoit un ordre clair et une boîte à outils puissante. Il écrit les fichiers, navigue dans le terminal, manipule Git, et a même... des yeux !

### 3. 👀 L'Auto-Correction Visuelle (Multimodal)
Fini les interfaces web avec des boutons invisibles ou des éléments superposés. Nos agents utilisent le protocole **MCP (Model Context Protocol)** pour piloter Chrome en arrière-plan. L'agent prend une capture d'écran de son propre code, l'analyse avec ses modèles de vision, et corrige de lui-même les bugs visuels *avant même* que vous ne les voyiez. 

### 4. 📚 La Fin des Hallucinations d'API (Context7)
Un LLM ne sait pas coder avec une bibliothèque sortie hier matin. Au lieu de le laisser inventer des méthodes imaginaires, notre usine est branchée en temps réel au réseau documentaire **Context7**. Dès que l'agent détecte qu'il a besoin de *React*, *Prisma*, ou *Tailwind*, il pré-charge automatiquement la documentation officielle à jour. 

### 5. 🛡️ Les Garde-Fous Infaillibles (Zero-LLM Gates)
On ne gaspille pas l'intelligence artificielle pour vérifier une faute de frappe. Avant qu'un fichier soit validé :
- **Le Linter** scanne instantanément la syntaxe.
- **Le Static Tester** vérifie la mécanique web (les boutons sont-ils cliquables ?).
- **Le Disjoncteur Anti-Boucle** repère mathématiquement si l'agent fait la même erreur 3 fois de suite, et déclenche l'Escalade (Post-Mortem automatique).
- **Le Read-Before-Write Gate** empêche formellement un agent d'écrire dans un fichier qu'il n'a pas lu au préalable.

---

## 🗄️ Une Mémoire de Fer : Le Knowledge Graph
Toutes ces IAs (l'Architecte, le Codeur, le Testeur) ne partagent pas un simple prompt historique qui s'effacerait avec le temps. Elles échangent et persistent leur savoir dans une **base de données relationnelle locale (DuckDB)**.

Lorsqu'un Coder échoue et que le Juge rejette le code, la raison du rejet est gravée dans le Knowledge Graph. À la prochaine itération, le Coder requêtera cette base de données pour "apprendre de ses erreurs", garantissant que le système ne produit **jamais de régression**.

---

## 🛠️ Prêt à démarrer l'Usine ?

Vous voulez voir l'équipe au travail ? Le point d'entrée unique est extrêmement simple :

1. Ouvrez `tasks.json` et écrivez votre besoin métier en langage naturel.
2. Démarrez l'usine avec une seule ligne de commande :
   ```powershell
   $env:WORKFLOW_MODE="coding"
   $env:PYTHONIOENCODING="utf-8"
   uv run python -m graph_orchestrator.workflows
   ```
3. Prenez un café ☕ et regardez l'orchestrateur créer la branche, planifier, coder, s'auto-corriger visuellement, et vous fournir un projet clef-en-main, stable et audité.

---

> 📖 **Pour les Ingénieurs et Architectes Systèmes :**
> Vous voulez comprendre les entrailles du monstre ? Le routage asynchrone, les arbres de syntaxe abstraits, et les spécifications DSPy ?
> 👉 [Consultez notre documentation technique approfondie (Architecture Details)](docs/ARCHITECTURE_DETAILS.md)
