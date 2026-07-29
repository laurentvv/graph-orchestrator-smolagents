# Architecture du Coupe-Circuit (Circuit Breaker) pour Graph Engineering

Dans un système "Fire and Forget" autonome, le plus grand danger est la **boucle infinie** : l'agent `Coder` génère une erreur, le `Tester` la renvoie, le `Coder` s'excuse et génère exactement la même erreur, et le système boucle jusqu'à vider votre quota d'API (ou monopoliser votre GPU local pendant 10 heures).

Pour empêcher cela, il faut implémenter un nœud **Circuit Breaker** (ou intégrer cette logique dans les arêtes de votre graphe d'états).

## Le Concept

1. **State Tracking** : L'état global du graphe (le `state` passé de nœud en nœud) doit posséder un compteur `retry_count`.
2. **Threshold (Seuil)** : Définir un nombre maximum d'essais consécutifs pour la même tâche (ex: `MAX_RETRIES = 3`).
3. **Escalade (Fallback)** : Si le seuil est dépassé, on ne retourne plus au `Coder` local (qui est coincé). L'arête conditionnelle bascule l'état vers un nœud `Judge` (utilisant un modèle beaucoup plus large/intelligent) ou déclenche une erreur d'abandon propre.

## Implémentation type avec un Graphe d'États (ex: type LangGraph ou FSM custom)

### 1. La structure de l'État (State)

```python
from typing import TypedDict, List

class GraphState(TypedDict):
    task: str
    code: str
    test_results: str
    retry_count: int
    status: str # "success", "failed", "blocked"
```

### 2. Le Nœud de Routage (L'Arête Conditionnelle)

Dans un graphe, l'arête qui suit le nœud `Tester` décide du prochain nœud en fonction de `retry_count`.

```python
def route_after_test(state: GraphState) -> str:
    """
    Fonction de routage (Arête Conditionnelle).
    Décide du prochain nœud après exécution des tests.
    """
    if state["status"] == "success":
        # Tout fonctionne, on passe à la finalisation
        return "Done"
        
    # Les tests ont échoué, on vérifie le coupe-circuit
    if state["retry_count"] >= 3:
        # CIRCUIT BREAKER ACTIVÉ
        # Le modèle local est bloqué dans une boucle de raisonnement.
        # On l'envoie vers le modèle Juge (plus lourd) ou on abandonne.
        print("⚠️ [Circuit Breaker] Max retries atteint. Escalade vers le Judge.")
        return "Judge"
        
    # Le modèle a encore le droit d'essayer, retour au Coder
    return "Coder"
```

### 3. Les Nœuds de l'Agent

```python
def node_coder(state: GraphState) -> GraphState:
    # 1. Le Coder génère du code basé sur la tâche et les erreurs précédentes
    new_code = run_local_llm_coder(state["task"], state["test_results"])
    
    # 2. On incrémente le compteur de tentatives (TRÈS IMPORTANT)
    state["retry_count"] += 1
    state["code"] = new_code
    
    return state

def node_tester(state: GraphState) -> GraphState:
    # 1. On exécute les tests sur le code généré
    success, logs = run_python_tests(state["code"])
    
    state["test_results"] = logs
    state["status"] = "success" if success else "failed"
    
    # 2. Si ça passe, on réinitialise le compteur pour la prochaine tâche
    if success:
         state["retry_count"] = 0
         
    return state

def node_judge(state: GraphState) -> GraphState:
    # Nœud d'escalade : appelé UNIQUEMENT si le coupe-circuit est activé.
    # Ici on peut utiliser l'API OpenAI / Anthropic pour débloquer le modèle local.
    fix = run_remote_heavy_llm(state["task"], state["code"], state["test_results"])
    state["code"] = fix
    
    # On renvoie au Tester
    return state
```

## Intégration dans `smolagents`

Si vous utilisez le framework `smolagents` (qui masque souvent la boucle de base), le Circuit Breaker doit être géré via le système de `ManagedAgent`. 
Le `CodeAgent` de HuggingFace possède d'ailleurs déjà des limites (comme `max_iterations`). Cependant, pour une véritable "Usine Autonome", il vaut mieux construire l'orchestrateur au-dessus de `smolagents` (chaque nœud du graphe appelle un `smolagent` spécifique, puis votre orchestrateur reprend la main pour gérer le `retry_count` de façon déterministe).
