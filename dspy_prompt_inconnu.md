Guide : Optimiser le Node « Réécriture de Prompt » avant le Node Architecte

Contexte : Un prompt utilisateur inconnu est reçu et traiter avant le Node Arictecte

Dans un pipeline de graph engineering (type Fan‑out → Judge → Synthesize), le node architecte reçoit un prompt utilisateur et doit produire un plan (découpage en workers, routage, contrats de données).
Le problème n’est pas « juger une réponse libre » mais optimiser le nœud de pré‑traitement qui reformule/enrichit le prompt brut avant qu’il n’atteigne l’architecte.

Le pipeline visé :

```
Prompt brut utilisateur
        │
        ▼
  ┌─────────────┐
  │   Node       │   ← C'EST CE NODE QU'ON OPTIMISE AVEC DSPy
  │  Rewriter    │
  └─────────────┘
        │
        ▼
  Prompt enrichi (contraintes explicites, contexte, format attendu)
        │
        ▼
  ┌─────────────┐
  │    Node      │
  │  Architecte  │
  └─────────────┘
        │
        ▼
  Plan / Architecture (liste de workers, routage, contrats)
```

Point clé : le juge ne note jamais le prompt réécrit directement. Un prompt réécrit peut sembler clair, structuré, complet — et pourtant faire produire une architecture médiocre à l’architecte. Le seul signal fiable est end‑to‑end : réécrire → faire tourner l’architecte → juger le plan produit.

---

1. Configuration : trois rôles, trois modèles

```python
import dspy
from dspy.teleprompt import MIPROv2
import re

# Rewriter : le node qu'on optimise (léger, tourne en prod)
lm_rewriter  = dspy.LM('ollama_chat/qwen2.5:7b', api_base='http://localhost:11434', api_key='')

# Architecte : reste FIXE pendant l'optimisation
lm_architecte = dspy.LM('ollama_chat/llama3:70b', api_base='http://localhost:11434', api_key='')

# Juge : indépendant des deux autres, évalue le plan final
lm_juge      = dspy.LM('ollama_chat/gemma2:12b', api_base='http://localhost:11434', api_key='')

# On configure le LM global sur le Rewriter (c'est le module qui sera appelé par MIPRO)
dspy.settings.configure(lm=lm_rewriter)
```

---

2. Les trois Signatures (améliorées)

2.1 Rewriter – désormais avec ChainOfThought

Le ChainOfThought permet au rewriter de générer un raisonnement intermédiaire (non utilisé en aval) que MIPROv2 peut optimiser au même titre que le prompt enrichi.

```python
class ReecriturePourArchitecte(dspy.Signature):
    """Analyse la demande, puis reformule en un prompt structuré (objectif, contraintes, contexte,
    format attendu) pour l'architecte. Le résultat doit être directement exploitable."""
    prompt_brut    = dspy.InputField(desc="Requête originale de l'utilisateur, souvent vague")
    prompt_enrichi = dspy.OutputField(desc="Prompt reformulé complet et non-ambigu")
```

2.2 Architecte – plan structuré attendu

Pour aider le juge à évaluer la cohérence, on guide l’architecte vers une structure explicite.

```python
class PlanArchitecte(dspy.Signature):
    """Tu es un architecte de systèmes multi-agents. À partir d'un prompt de tâche,
    produis un plan avec les sections suivantes : Workers (nom, rôle), Routage (flux),
    Contrats de données (formats échangés)."""
    prompt_tache = dspy.InputField()
    plan         = dspy.OutputField(desc="Plan structuré : Workers, Routage, Contrats")
```

2.3 Juge – score robuste et justification

On force un format de score facilement parsable : Score: 7.

```python
class JugementPlan(dspy.Signature):
    """Tu es un architecte logiciel senior. Évalue un plan d'architecture.
    Donne une justification factuelle en 2-3 phrases, puis termine par 'Score: X'
    où X est un entier entre 0 et 10."""
    demande_initiale = dspy.InputField()
    plan_produit     = dspy.InputField()
    justification    = dspy.OutputField(desc="Justification factuelle (2-3 phrases)")
    score            = dspy.OutputField(desc="Score entier de 0 à 10, format 'Score: X'")
```

---

3. Modules (avec ChainOfThought pour le Rewriter)

```python
rewriter_module   = dspy.ChainOfThought(ReecriturePourArchitecte)   # CoT optimisable
architecte_module = dspy.Predict(PlanArchitecte)
juge_module       = dspy.Predict(JugementPlan)
```

---

4. Métrique end‑to‑end (le rewriter n’est jamais jugé seul)

```python
def metrique_end_to_end(example, pred, trace=None):
    # pred.prompt_enrichi = sortie du rewriter (le rationale CoT est ignoré)

    # 1. Appel à l'architecte (modèle fixe) sur le prompt réécrit
    with dspy.context(lm=lm_architecte):
        resultat_architecte = architecte_module(prompt_tache=pred.prompt_enrichi)

    # 2. Jugement du PLAN produit
    with dspy.context(lm=lm_juge):
        jugement = juge_module(
            demande_initiale=example.prompt_brut,
            plan_produit=resultat_architecte.plan
        )

    # 3. Extraction robuste du score
    score_texte = jugement.score
    match = re.search(r'\b([0-9]|10)\b', score_texte)   # cherche "7", "10", etc.
    if match:
        note = int(match.group(1))
    else:
        # fallback : dernier nombre trouvé dans la chaîne
        nombres = re.findall(r'\b\d+\b', score_texte)
        note = int(nombres[-1]) if nombres else 0
    note = max(0, min(10, note))
    return note / 10.0
```

Coût : chaque trial appelle désormais 3 LM (rewriter → architecte → juge). Avec auto="light" et ~8 exemples, c’est gérable en local, mais prévoir ~25 trials.

---

5. Dataset : prompts bruts typiques + cas ambigus

On conserve les prompts réalistes et on ajoute des demandes volontairement très ambiguës pour forcer le rewriter à expliciter les compromis.

```python
dataset = [
    dspy.Example(prompt_brut="Fais-moi un système qui analyse des logs et alerte si problème.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Je veux un agent qui compare des offres d'emploi et note leur pertinence.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Crée un pipeline qui résume des documents PDF longs.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Un truc pour surveiller des prix sur plusieurs sites et m'envoyer un mail.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Système multi-agents pour classer des tickets de support par urgence.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Agent qui vérifie la réputation IP en croisant plusieurs sources.").with_inputs('prompt_brut'),
    # Prompts très flous → obligent le rewriter à lever les ambiguïtés
    dspy.Example(prompt_brut="Système qui gère tout seul la compta et le support client.").with_inputs('prompt_brut'),
    dspy.Example(prompt_brut="Un truc rapide pour détecter les fraudes, sans erreurs.").with_inputs('prompt_brut'),
]
```

---

6. Optimisation avec MIPROv2

On utilise ChainOfThought comme module de base, on augmente un peu le nombre de trials et on garde auto="light" pour une exploration efficace.

```python
optimiseur = MIPROv2(
    metric=metrique_end_to_end,
    auto="light",
    num_trials=25,                # exploration plus poussée
    max_labeled_demos=3,          # quelques démonstrations pour guider
)

module_base = rewriter_module    # déjà ChainOfThought
print("⚙️  Optimisation du node Rewriter (Qwen 7B CoT) via impact sur l'Architecte (Llama 70B)...")
module_optimise = optimiseur.compile(module_base, trainset=dataset)

# Sauvegarde
module_optimise.save("rewriter_pour_architecte_optimise.json")
```

---

7. Option allégée (si le end‑to‑end est trop coûteux/lent)

Si 3 appels LM par trial est trop lourd, on peut temporairement faire juger le prompt réécrit sur des critères proxy (présence de contraintes, clarté). Cela divise le coût par ~1.5, mais c’est moins fidèle. Mieux vaut utiliser cette approche uniquement pour une première exploration rapide, puis revenir à la métrique end‑to‑end pour la validation finale.

---

8. Test rapide après optimisation

```python
# Charger le module optimisé
rewriter_opt = dspy.ChainOfThought(ReecriturePourArchitecte)
rewriter_opt.load("rewriter_pour_architecte_optimise.json")

brut = "Je veux un truc qui surveille les réseaux sociaux et alerte en cas de bad buzz."
with dspy.context(lm=lm_rewriter):
    result = rewriter_opt(prompt_brut=brut)
print("PROMPT ENRICHI :", result.prompt_enrichi)

with dspy.context(lm=lm_architecte):
    plan = architecte_module(prompt_tache=result.prompt_enrichi)
print("PLAN PRODUIT :", plan.plan)
```

---

En synthèse

· Le nœud optimisé est le rewriter, et il est désormais un ChainOfThought (raisonnement optimisable).
· Le juge évalue la sortie de l’architecte, produite à partir du prompt réécrit — jamais le prompt réécrit isolément.
· L’architecte reste un modèle fixe ; seul le prompt qui l’alimente varie.
· Le parsing du score a été fiabilisé (regex cherchant un nombre entre 0 et 10).
· Le dataset inclut des demandes très ambigües pour pousser le rewriter à expliciter.
· Les signatures guident l’architecte vers une structure stable, facilitant l’évaluation.

Ce pipeline est directement exécutable et devrait produire un rewriter sensiblement meilleur, car optimisé sur ce qui compte vraiment : la qualité du plan généré en aval.
