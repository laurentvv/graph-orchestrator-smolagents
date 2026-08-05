# ADR 0001 : Design des Outils MCP & Smolagents

**Statut** : Accepté
**Date** : 2026-08-05

## Contexte
L'Usine Logicielle intègre à la fois des outils natifs (`smolagents`) et des outils distribués (MCP - Model Context Protocol, ex: Puppeteer, Context7). Avec l'augmentation du nombre d'outils, la manière dont le Modèle (LLM) interagit avec ces outils devient un goulot d'étranglement majeur. Si un outil retourne des erreurs cryptiques ou inonde la fenêtre de contexte de données inutiles, l'agent échouera en boucle.

## Décision
Tous les nouveaux outils (Skills, serveurs MCP, outils natifs) doivent respecter les trois principes cardinaux inspirés par les spécifications de `mcp-builder` :

### 1. Optimisation du Contexte Limité (Optimize for Limited Context)
- **Jamais de Full Dumps** : Ne jamais retourner la totalité d'un fichier ou d'une base de données si ce n'est pas strictement nécessaire.
- **Troncature Implicite** : Si l'output dépasse 1000 lignes, l'outil DOIT tronquer lui-même la réponse avec une note `[... Truncated for context limits. Use offset/limit parameters to read more.]`.
- **Granularité** : Fournir des outils de lecture partielle (`read_file` avec offset/limit, `read_python_skeleton`).

### 2. Messages d'Erreur Actionnables (Actionable Error Messages)
- **Pas de "Error 500" aveugles** : Si l'outil échoue, il doit retourner à l'agent *pourquoi* et *comment réparer*.
- *Mauvais exemple* : `File not found`.
- *Bon exemple* : `File 'test.py' not found in /app/src. Did you mean 'tests.py'? Current directory contains: [main.py, utils.py, tests.py]`.

### 3. Design pour les Workflows (Build for Workflows)
- Les outils doivent s'enchaîner logiquement.
- L'outil doit retourner des données structurées si nécessaire, ou un résumé texte utile au LLM.
- **Idempotence** : Les outils qui modifient l'état (`write_file`, `bash_command`) doivent être pensés pour être ré-exécutables sans tout casser en cas de retry.

## Conséquences
- Augmentation de la robustesse des agents face aux erreurs d'outils.
- Réduction drastique des plantages liés au "Context Overflow".
- Nécessite d'auditer et potentiellement refactoriser certains outils plus anciens pour qu'ils respectent ces règles (notamment via la troncature active).
