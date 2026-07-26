# Agent Graph Architecture with Smolagents & Asyncio

Ce dépôt implémente une architecture de **Graph Engineering** pour agents IA en utilisant le framework [`smolagents`](https://github.com/huggingface/smolagents) et `asyncio`.

Le but de cette architecture est de sortir d'une exécution IA linéaire basique (souvent fragile) pour aller vers un modèle distribué, parallèle et vérifiable (pattern *Fan-out -> Reduce -> Synthesize*).

## Fonctionnalités clés

1. **Parallélisation asynchrone (Fan-out)** :
   - Au lieu d'utiliser des threads bloquants, les tâches indépendantes sont distribuées de manière asynchrone via `asyncio.gather()`. Chaque tâche est gérée par son propre agent (stateless).
2. **Vérification Contradictoire (Le Juge)** :
   - Un nœud "Juge" (agent distinct) inspecte les résultats des sous-agents avant la synthèse. Il filtre les données aberrantes ou celles ayant un faible taux de confiance.
3. **Contrats de Données Stricts (Pydantic)** :
   - Chaque nœud a une entrée et une sortie strictement typée via `Pydantic`.
   - Mécanisme de **Retry Automatique** : Si le LLM échoue à générer un JSON valide (erreur très fréquente sur les petits modèles), le système catch l'erreur de parsing et demande automatiquement au LLM de se corriger.
4. **Tiering des Modèles** :
   - Les tâches basiques et massivement parallèles (Fan-out) sont envoyées à un petit modèle rapide et peu coûteux (ex: `Qwen2.5-7B`).
   - Le raisonnement complexe (Juge et Synthèse) est confié à un modèle lourd (ex: `Llama3-70B`).

## Pré-requis

- Python 3.10+
- [Ollama](https://ollama.com/) installé et en cours d'exécution localement.

## Installation

```bash
# 1. Installer les dépendances
pip install "smolagents[openai]" pydantic

# 2. Télécharger les modèles via Ollama
ollama pull qwen2.5:7b
ollama pull llama3:70b
```

## Utilisation

Assurez-vous que le serveur Ollama tourne en arrière-plan (`ollama serve`), puis exécutez le script :

```bash
python agent_graph.py
```

## Structure du Graphe

1. **`execute_worker_node`** : Prend une tâche brute, l'analyse et retourne un `WorkerOutput`.
2. **`execute_judge_node`** : Prend la liste des `WorkerOutput`, applique des règles métier (ex: confiance > 0.7) et retourne un `JudgeOutput` filtré.
3. **`execute_synth_node`** : Prend les données approuvées par le juge et rédige le `FinalSynthesis`.
