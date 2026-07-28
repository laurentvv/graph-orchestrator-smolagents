# Architecture DSPy & smolagents : Le Graphe Hybride

Cette documentation détaille l'implémentation de la nouvelle architecture cognitive au sein du projet **Graph Orchestrator**. 

L'objectif de cette refonte (le principe du *"coupe tout et utilise dspy"*) était de séparer l'intelligence algorithmique de l'exécution en créant une synergie entre **DSPy 3.0** (pour le raisonnement structuré) et **smolagents** (pour l'action).

---

## 1. Philosophie : "Cerveaux vs Mains"

Avant cette implémentation, le projet s'appuyait uniquement sur des `CodeAgent` et `ToolCallingAgent` via `smolagents` avec des prompts complexes (`run_with_retry`, boucles Markdown) pour extraire du JSON. Les petits modèles locaux (Gemma 2B, Qwen) échouaient souvent à respecter le format imposé.

La nouvelle architecture sépare les rôles :
- **Les Cerveaux (DSPy 3.0)** : Nœuds de réflexion pure (Routeur, Architecte, Auditeur, Juge). DSPy force nativement les modèles locaux à générer des structures JSON strictes (via Pydantic) sans avoir besoin de coder des parsers complexes à la main.
- **Les Mains (smolagents)** : Nœuds d'exécution (Codeur, Testeur QA). Ils reçoivent des ordres clairs formatés par DSPy et utilisent des outils locaux (Chrome DevTools, bash, duckdb) pour écrire et tester du code dans un bac à sable sécurisé.

---

## 2. Implémentation technique : `dspy_nodes.py`

Le fichier `dspy_nodes.py` remplace la logique de "prompting manuel" des nœuds cognitifs par des **Signatures DSPy**.

### A. La Signature (`dspy.Signature`)
Une signature est un contrat déclaratif. Au lieu d'écrire de longs prompts pour supplier le modèle de respecter un format, on déclare les entrées (Input) et les sorties (Output). DSPy se charge de formuler la requête et de garantir le format de sortie via ses adaptateurs JSON internes.

**Exemple de la Signature du Routeur :**
```python
class RouterSignature(dspy.Signature):
    """Tu es un routeur système ultra-rapide. Tu analyses la requête initiale de l'utilisateur."""
    task_content: str = dspy.InputField(desc="La requête ou instruction de l'utilisateur")
    output: RouterOutput = dspy.OutputField(desc="La décision de routage structurée strictement selon le schéma Pydantic fourni.")
```
Ici, `RouterOutput` est un modèle `Pydantic` déjà défini dans `models.py`. Dans DSPy 3.0, l'intégration est native : le framework comprend la structure Pydantic et l'injecte dans le modèle local (JSON Mode).

### B. Le Module d'Exécution (`dspy.ChainOfThought`)
Plutôt que d'utiliser un simple `dspy.Predict` (qui forçait le modèle local à recracher le JSON instantanément, provoquant des boucles infinies ou des erreurs de token max), nous utilisons `dspy.ChainOfThought`.

```python
predictor = dspy.ChainOfThought(ArchitectSignature)
result = await asyncio.to_thread(predictor, task_content=task_content)
return result.output, metrics
```
**Pourquoi ChainOfThought ?** 
Il injecte silencieusement un champ intermédiaire `reasoning` dans le prompt. Le modèle local (comme Qwen 2.5) peut alors "réfléchir" étape par étape en générant du texte libre, avant d'être contraint de remplir l'objet strict Pydantic (`result.output`). Cela empêche les hallucinations et le dépassement de limite de tokens (`max_tokens: 8192`).

---

## 3. Les 4 Nœuds Cognitifs DSPy

Voici les 4 modules migrés vers DSPy dans l'orchestrateur :

1. **`execute_router_node`** (Routeur) : 
   - *Entrée* : La phrase de l'utilisateur.
   - *Sortie* : Booléens décidant si un plan d'architecture ou un audit de sécurité est requis.
2. **`execute_architect_node`** (Architecte) :
   - *Entrée* : Le contenu de la tâche globale.
   - *Sortie* : Un tableau Pydantic de `ArchitectPlanItem`, découpant la grosse tâche en petites sous-tâches unitaires (ex: `setup_ui`, `game_loop`). C'est ce qui crée le *Fan-out* (lancement des codeurs en parallèle).
3. **`execute_security_reviewer_node`** (Security Reviewer) :
   - *Entrées* : L'ID de la sous-tâche et le code produit par le codeur.
   - *Sortie* : Un tableau strict de vulnérabilités potentielles (`SecurityVulnerability`).
4. **`execute_code_judge_node`** (Le Juge) :
   - *Entrées* : Le code, les tests du QA, les retours de sécurité.
   - *Sortie* : Un verdict Pydantic (`approved: bool`, `feedback: str`) qui décide si le graphe boucle sur une nouvelle itération ou s'il s'arrête.

---

## 4. Connexion avec l'Ollama local

L'adaptateur a été mis en place pour dialoguer avec votre instance Ollama locale de manière asynchrone (via l'interface compatible OpenAI native de DSPy v3) :

```python
def _configure_dspy(settings: Settings, model_id: str):
    lm = dspy.LM(
        f"openai/{model_id}", # Compatible avec le format LiteLLM / Ollama
        api_base=settings.ollama_api_base, # ex: http://localhost:11434/v1
        api_key="sk-none",
        max_tokens=8192, # Augmenté pour supporter la génération de ChainOfThought
        temperature=0.3, # Indispensable pour éviter la boucle de répétition locale
    )
    dspy.settings.configure(lm=lm)
```

## Conclusion et Avantages

Grâce à cette implémentation, le projet ne repose plus sur la chance du LLM pour formater ses JSON :
- **Déterministe** : Les clés Pydantic sont garanties.
- **Léger** : Plus besoin du Coder `smolagents` (et de ses lourds outils) pour faire de la simple logique.
- **Évolutif** : Le module DSPy pourra facilement accueillir des optimiseurs télé-prompteurs (MIPROv2) à l'avenir si nous voulons que l'orchestrateur optimise ses propres prompts avec le temps.

---

## 5. FAQ & Troubleshooting (Astuces Avancées)

### A. L'erreur `max_tokens` (Troncature)
**Symptôme** : DSPy renvoie un warning `LM response was truncated due to exceeding max_tokens=X`.
**Cause** : Lors de la phase de réflexion (`reasoning`), un modèle avec un décodeur très avide (Greedy Decoding avec `temperature=0`) peut entrer dans une boucle infinie de répétition ("Je dois coder... Je dois coder... Je dois coder...").
**Solution** : Toujours initialiser `dspy.LM` avec une température légèrement non-nulle (`temperature=0.3`) et allouer suffisamment de tokens (`max_tokens=8192`) pour laisser le modèle développer sa pensée.

### B. Validation Pydantic Stricte
**Symptôme** : Erreur Python liée à un type invalide ou une clé manquante (ex: `expected str, got dict`).
**Cause** : DSPy 3.0 valide rigoureusement les types fournis aux champs `InputField`. Si une signature attend `task_content: str`, il ne faut pas lui passer un objet JSON. 
**Solution** : Assurez-vous d'extraire les bonnes variables en amont (ex: `task.get('content')`).

### C. Le nommage dynamique smolagents
**Symptôme** : L'Architecte DSPy crée un plan génial, mais le Coder smolagents plante avec `ValueError: Agent name 'coder_setup-ui' must be a valid Python identifier`.
**Cause** : L'Architecte (étant très structuré) génère des identifiants sémantiques avec des tirets. `smolagents` refuse les tirets.
**Solution** : Les IDs générés par DSPy doivent être nettoyés avant l'instanciation (`task['id'].replace('-', '_')`).

### D. Tester les nœuds DSPy sans LLM
Comme DSPy renvoie des objets Pydantic fortement typés, l'écriture de tests unitaires (via `pytest`) est grandement simplifiée. Il suffit de mocker la sortie de `dspy.ChainOfThought` avec un objet Pydantic statique pour vérifier la logique métier du graphe (Fan-out, boucles de retour) sans consommer le moindre jeton.
