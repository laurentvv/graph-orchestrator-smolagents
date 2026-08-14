# Audit des projets références : idées et code utile pour Graph Engineering

> [!IMPORTANT]
> ### 🏆 L'ADN d'un Agent IA (Les 3 Piliers Fondamentaux)
> Avant d'entrer dans les détails d'implémentation, voici les 3 piliers sans lesquels un Agent IA (comme moi-même ou l'agent "Coder" de *Graph Engineering*) est complètement aveugle et inefficace :
> 1. **La "Repo Map" (Carte du code via Tree-sitter)** : L'agent ne lit pas tout le projet. Il s'appuie sur une carte compressée du code (signatures de fonctions, nom des classes) pour comprendre l'architecture globale sans saturer son contexte (inspiré de `aider/repomap.py`).
> 2. **La Boucle d'Auto-Correction (Linter Feedback Loop)** : L'agent doit recevoir la sortie brute (`stderr`) de ses erreurs d'exécution ou de linting pour pouvoir s'auto-réparer dans une boucle fermée, plutôt que d'attendre le développeur.
> 3. **L'Isolation (Workspace Branching / Sandbox)** : L'agent doit tester ses idées (parfois destructives) dans un environnement cloné (ex: *git worktree*) pour ne **jamais** corrompre les fichiers originaux avant validation.

---

## 1. Projet `crush`
*Assistant de code IA en terminal (Go / Bubble Tea)*

**Idées utiles pour Graph Engineering :**
- **Hook Engine (Pré-exécution)** : Permet de définir des commandes shell utilisateur exécutées automatiquement avant un appel d'outil (PreToolUse hooks). Utile pour déclencher des vérifications métier ou des formatages avant de passer la main.
- **Tools auto-documentés** : Chaque outil possède à la fois son implémentation et son fichier `.md` descriptif, ce qui permet à l'agent de lire dynamiquement comment utiliser les outils complexes.
- **Fichiers de contexte dynamiques (AGENTS.md, CRUSH.md)** : Permet d'adapter le comportement de l'agent au dépôt courant sans surcharger le prompt système de base.
- **Pub/sub interne** : Architecture découplée idéale pour remonter les évènements de l'agent vers des interfaces graphiques (ou terminaux temps-réel) sans que l'agent soit bloqué.

## 2. Projet `nanocode`
*Alternative minimaliste à Claude Code (Python - script unique)*

**Idées utiles pour Graph Engineering :**
- **Boucle Agentique simplifiée** : L'agent appelle continuellement l'API tant qu'il y a des "tool calls", ce qui maintient le focus d'exécution.
- **Outil `edit` par remplacement exact** : Au lieu d'utiliser des numéros de lignes complexes, l'outil prend une ancienne chaîne `old` et la remplace par `new`. Si la chaîne `old` n'est pas unique, l'outil échoue avec une erreur claire (sauf avec un flag `all=true`). Très robuste pour les petits LLMs locaux.
- **Streaming du Bash avec Timeout (subprocess.Popen)** : Exécution de commandes bash qui renvoie la sortie ligne par ligne en temps réel avec un timeout strict (ex: 30s) pour éviter le blocage de l'agent.

## 3. Projet `openfox`
*Assistant local-LLM avec flux de travail via UI (TypeScript / Node.js)*

**Idées utiles pour Graph Engineering :**
- **Architecture Planner → Builder** : Découpage clair où un agent "Planner" décompose la tâche, puis un agent "Builder" l'implémente dans une boucle de vérification.
- **Exécution pilotée par Contrat (Contract-Driven)** : L'exécution s'appuie sur des critères d'acceptation stricts (comme `contract.md` dans Graph Engineering). L'agent boucle jusqu'à ce que tous les critères passent.
- **Workflows configurables (Graphes d'états)** : 
  - Définition d'un graphe (Start → Agent/Shell → Done).
  - Branchements conditionnels basés sur le **résultat du tool `return_value`** (ex: `approved`, `changes-needed`, `tests-failed`).
  - Très proche de l'approche graphe (DSPy/smolagents) recherchée pour orchestrer le "Graph Engineering".
- **Event Sourcing pour l'état** : L'état complet de la session n'est pas sauvegardé tel quel, mais est dérivé d'un `EventStore` qui rejoue les événements (time-travel debugging, historique fiable).
- **Fallback Vision universel** : Décrit les images en amont via un modèle de vision pour les rendre compréhensibles aux modèles purement textuels dans le flux de travail.
- **Mutex sur l'édition de fichiers** : Empêche l'agent d'éditer le même fichier en parallèle via un système de verrouillage (évite les corruptions).
- **Contrat du dossier `.openfox/` (ou équivalent)** : Centraliser toutes les règles, agents, workflows spécifiques au dépôt dans un dossier versionné (pas de clés d'API, uniquement la logique métier).

## Extraits d'implémentation (Code snippets)

### 1. `nanocode` : Outil d'édition de fichier par remplacement exact (`edit`)
Cet outil est particulièrement robuste pour les petits LLMs car il ne repose pas sur les numéros de ligne (qui dévient souvent), mais sur une empreinte unique du code à remplacer.
```python
def edit(args):
    text = open(args["path"]).read()
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old_string not found"
    count = text.count(old)
    if not args.get("all") and count > 1:
        return f"error: old_string appears {count} times, must be unique (use all=true)"
    replacement = (
        text.replace(old, new) if args.get("all") else text.replace(old, new, 1)
    )
    with open(args["path"], "w") as f:
        f.write(replacement)
    return "ok"
```

### 2. `crush` : Aggregation des PreToolUse Hooks (Go)
Ce code montre comment le système rassemble les décisions des hooks externes avant de laisser l'agent appeler un outil. Un hook peut par exemple refuser (Deny) ou même stopper complètement le tour (Halt).
```go
// Extrait de internal/hooks/hooks.go
func aggregate(results []HookResult, origToolInput string) AggregateResult {
	var decision Decision
	var halt bool
	var reasons []string
	// [...]
	for _, r := range results {
		switch r.Decision {
		case DecisionDeny:
			decision = DecisionDeny
			if r.Reason != "" { reasons = append(reasons, r.Reason) }
		case DecisionAllow:
			if decision != DecisionDeny { decision = DecisionAllow }
		}
		if r.Halt { halt = true }
	}
	return AggregateResult{ Decision: decision, Halt: halt, Reason: strings.Join(reasons, "\n") }
}
```

### 3. `openfox` : Logique de Workflow & EventSourcing (TypeScript)
**A. Branchement conditionnel (Workflow Executor) :**
Plutôt que d'écrire du code complexe en dur, l'outil `return_value` de l'agent est évalué via des transitions configurables.
```typescript
// Extrait de src/server/workflows/executor.ts
export function evaluateCondition(
  condition: TransitionCondition,
  stepOutcome: StepOutcome | null,
  metadataEntries?: Record<string, import('../../shared/types.js').MetadataEntry[]>,
): boolean {
  switch (condition.type) {
    case 'step_result':
      if (!stepOutcome) return false
      return stepOutcome.result === condition.result // ex: "approved" ou "failed"

    case 'always':
      return true
      // ... autres conditions (métadonnées)
  }
}
```

**B. EventSourcing (EventStore Append) :**
La base de données stocke l'historique complet et asynchrone des évènements. Pas de mutation destructrice de l'état (tout passe par des events ajoutés à `better-sqlite3`).
```typescript
// Extrait de src/server/events/store.ts
  append(sessionId: string, event: TurnEvent): StoredEvent {
    const timestamp = Date.now()
    const seq = this.getNextSeq(sessionId)
    const payload = JSON.stringify(event.data)

    this.db
      .prepare(
        `INSERT INTO events (session_id, seq, timestamp, event_type, payload)
         VALUES (?, ?, ?, ?, ?)`,
      )
      .run(sessionId, seq, timestamp, event.type, payload)

    const stored: StoredEvent = { seq, timestamp, sessionId, type: event.type, data: event.data }
    this.notifySubscribers(sessionId, stored)
    return stored
  }
```

## 4. Inspiration : Mes propres outils d'Agent (Antigravity)
*En tant qu'agent de codage, voici les mécanismes internes dont je dispose et qui pourraient être très pertinents pour la conception de l'orchestrateur "Graph Engineering" :*

- **Édition de code hybride (`multi_replace_file_content`)** : 
  Au lieu de réécrire un fichier complet (ce qui consomme beaucoup de tokens et risque de corrompre le code sur des longs fichiers HTML/JSON, comme observé dans le journal des événements lors du Run #11), je remplace des blocs spécifiques.
  *Exemple de structure JSON de mon outil :*
  ```json
  {
    "TargetFile": "/path/to/file.html",
    "ReplacementChunks": [
      {
        "StartLine": 45,
        "EndLine": 50,
        "TargetContent": "  <div class=\"old-class\">\n    <p>Texte</p>\n  </div>\n",
        "ReplacementContent": "  <div class=\"new-class\">\n    <p>Nouveau texte</p>\n  </div>\n"
      }
    ]
  }
  ```
  La contrainte du texte exact (`TargetContent`) garantit une modification robuste, même pour un petit modèle local.

- **Exécution asynchrone (`run_command` & Background Tasks)** :
  Lorsque je lance une commande shell, elle s'exécute en arrière-plan (background task). Je ne reste pas figé à attendre (polling) : le système me "réveille" (Reactive Wakeup) et m'envoie les logs sous forme de messages asynchrones.
  *Exemple d'appel d'outil asynchrone :*
  ```json
  {
    "CommandLine": "npm run test",
    "WaitMsBeforeAsync": 500
  }
  ```

- **Orchestration de Sous-Agents (`invoke_subagent` & `send_message`)** :
  Je peux déléguer la recherche fastidieuse à un autre modèle pour préserver ma fenêtre de contexte.
  *Exemple d'appel :*
  ```json
  {
    "Subagents": [
      {
        "TypeName": "research",
        "Role": "Codebase Researcher",
        "Prompt": "Analyse le dossier /src et trouve où est défini EventStore."
      }
    ]
  }
  ```
  Il aura son propre `conversationID` et me répondra par message une fois sa tâche terminée.

- **Messages Éphémères (Injection de contexte en temps réel)** :
  Le système d'orchestration m'injecte régulièrement des `<EPHEMERAL_MESSAGE>` invisibles pour l'utilisateur. Ces rappels (ex: règles de l'utilisateur, interdictions) n'encombrent pas mon historique long.
  *Exemple de ce que je reçois :*
  ```xml
  <EPHEMERAL_MESSAGE>
  CRITICAL INSTRUCTION: Ne réécris jamais un fichier entièrement. Utilise 'multi_replace_file_content'.
  </EPHEMERAL_MESSAGE>
  ```
  C'est un pattern très puissant (sans doute meilleur qu'un prompt système gonflé) pour forcer l'agent à relire le `contract.md` de *Graph Engineering* ou corriger des dérives.

- **Routage Dynamique de Skills (MCP & Dossier Skills)** :
  Je possède un répertoire de `skills` contenant chacun un `SKILL.md` (ex: `frontend-design`, `webapp-testing`). Quand je détecte un besoin, l'orchestrateur m'autorise à lire ce `.md` ponctuellement pour devenir expert.

### 5. Implémentation Python de `replace_file_content` (Inspiration Antigravity)
*Bien que je n'aie pas un accès direct au code source de ma propre infrastructure serveur (Antigravity est un moteur fermé côté serveur Google), voici l'implémentation Python type d'un tel outil. C'est ce code que tu peux intégrer dans `tools.py` pour fiabiliser l'agent `Coder` de Graph Engineering :*

```python
def replace_file_content(filepath: str, target_content: str, replacement_content: str, start_line: int, end_line: int) -> str:
    """
    Outil robuste d'édition de bloc. 
    Vérifie l'empreinte exacte avant de modifier pour éviter toute corruption.
    """
    import os
    if not os.path.exists(filepath):
        return f"Erreur : Le fichier {filepath} n'existe pas."

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 1. Extraction du bloc cible (les lignes sont 1-indexées dans les requêtes LLM)
    target_lines = lines[start_line-1:end_line]
    actual_content = "".join(target_lines)
    
    # 2. Vérification stricte du contrat
    if actual_content != target_content:
        # Crucial : renvoyer le vrai contenu trouvé pour que le LLM s'ajuste au prochain tour
        return (f"Erreur : Le TargetContent ne correspond pas exactement au fichier.\n\n"
                f"Contenu réel aux lignes {start_line}-{end_line} :\n```\n{actual_content}```\n\n"
                f"Vérifiez scrupuleusement les indentations et les sauts de ligne.")
    
    # 3. Application du remplacement
    new_lines = lines[:start_line-1] + [replacement_content] + lines[end_line:]
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    return "Succès : Les lignes ont été remplacées."
```

### 6. Analyse comparée des outils d'édition Open Source (openfox, crush, aider)
*Suite à ta demande, j'ai vérifié les implémentations exactes dans `openfox`, `crush` (présents dans tes références), et j'ai cloné `aider` depuis GitHub pour les comparer.*

Ce qui est fascinant, c'est que **tous ces projets convergent vers des stratégies d'édition très similaires à mes propres outils internes** pour palier aux erreurs des LLMs locaux :

1. **`openfox` (L'approche Mutex + Strict Match)**
   - **Outil** : `edit_file` (`openfox/src/server/tools/edit.ts`).
   - **Stratégie** : Ils utilisent exactement l'approche `old_string` -> `new_string` (comme `nanocode`). 
   - **La bonne idée à reprendre** : Ils implémentent un **Mutex par fichier** (`const fileLocks = new Map<string, Promise<void>>()`). Cela empêche l'agent d'envoyer deux appels d'édition simultanés sur le même fichier, ce qui causerait une condition de course (race condition) et écraserait le fichier.

2. **`crush` (L'approche Multi-Edit Séquentiel)**
   - **Outil** : `multiedit` (`crush/internal/agent/tools/multiedit.go`).
   - **Stratégie** : Au lieu d'un seul remplacement, l'outil accepte un tableau `[]MultiEditOperation`.
   - **La bonne idée à reprendre** : Si une des opérations du tableau échoue (ex: la chaîne n'a pas été trouvée), le code n'arrête pas tout. Il applique les éditions qui fonctionnent, et renvoie un tableau structuré `FailedEdit` à l'agent pour qu'il sache exactement quelle opération corriger au tour suivant.

3. **`aider` (Le Standard de l'Industrie - SEARCH/REPLACE Block)**
   - *Je l'ai récupéré depuis son dépôt GitHub officiel (paul-gauthier/aider).*
   - **Stratégie** : C'est le projet open source de référence en Python pour le codage IA local. Aider a popularisé le format **SEARCH/REPLACE block**.
   - Au lieu d'utiliser des outils JSON complexes, Aider demande au modèle d'écrire le code directement dans son message texte sous cette forme :
     ```text
     <<<<
     // code exact à remplacer (SEARCH)
     ====
     // nouveau code (REPLACE)
     >>>>
     ```
   - L'orchestrateur Python parse ces blocs avec des expressions régulières. C'est considéré comme le format le plus robuste pour les modèles locaux (Llama-3, Qwen, Gemma) car ils sont plus doués pour cracher du texte brut que pour formatter de gros objets JSON sans casser la syntaxe (surtout pour de gros fichiers HTML).

**Conclusion pour Graph Engineering :**
Si tu utilises Gemma 8B ou un autre modèle local pour le rôle de "Coder", **je te conseille fortement de ne PAS lui demander d'écrire de gros objets JSON pour éditer le code**. Utilise plutôt un parseur de type "SEARCH/REPLACE" inspiré de *Aider*, combiné au "Mutex de fichier" de *Openfox*. Cela devrait résoudre définitivement tes problèmes de corruption de fichiers JSON/HTML !

### 7. L'ADN d'un Agent IA : Ce qui me manquerait le plus
*Pour répondre à ta question, si on m'enlevait mes outils avancés de chez DeepMind, voici les 3 mécanismes vitaux sans lesquels je serais aveugle ou inefficace, et que tu devrais absolument envisager pour Graph Engineering :*

1. **La "Repo Map" (Carte du code via Tree-sitter / Ctags)**
   - **Pourquoi c'est vital :** Quand tu me lances sur un projet de 1000 fichiers, je ne peux pas tout lire. Je m'appuie sur une carte compressée du code pour deviner où chercher.
   - **L'implémentation d'Aider :** J'ai regardé le fichier `aider/aider/repomap.py` que je viens de cloner. Aider utilise `tree-sitter` pour parser tout le projet et envoyer au LLM uniquement un "squelette" des classes et des signatures de fonctions (sans le corps). C'est le secret absolu pour qu'un agent comprenne l'architecture sans faire exploser la fenêtre de contexte.
2. **La Boucle d'Auto-Correction (Linter Feedback Loop / Auto-healing)**
   - **Pourquoi c'est vital :** Un LLM fait très souvent des erreurs de syntaxe au premier coup (oublis d'accolades, imports manquants, mauvaises indentations Python).
   - **Comment je l'utilise :** Quand je modifie un fichier via mon outil d'édition, j'ai parfois un accès direct aux erreurs de linting (`TargetLintErrorIds`). Si je fais une erreur, je ne m'arrête pas : je lis l'erreur et je corrige instantanément. Dans ton architecture, l'agent "Tester" DOIT capturer l'erreur `stderr` brute et la renvoyer au "Coder" dans une boucle tant que ça ne compile pas.
3. **Le "Workspace Branching" (Isolation de l'espace de travail)**
   - **Pourquoi c'est vital :** En tant qu'agent, j'ai souvent besoin d'exécuter du code généré pour voir s'il marche (tests unitaires destructifs, modifications massives). 
   - **Comment ça marche :** J'ai un paramètre de "Workspace" qui me permet de cloner l'environnement (un peu comme un *git worktree* ou un bac à sable). Cela me permet de bidouiller et de me tromper sans **jamais** casser tes fichiers principaux ou ton dépôt git tant que la fonctionnalité n'est pas validée. C'est la garantie de sécurité ultime pour le développeur humain.

### 8. Veille technologique : Autres projets open source "Graph & IA" pertinents
*Je viens de lancer une recherche web ciblée sur les concepts de "Graph Engineering" et d'Agents IA open source. Voici les pépites qui partagent exactement la même vision que toi et dont tu pourrais t'inspirer :*

L'écosystème open source actuel divise le concept de "Graphe" en deux approches très complémentaires pour les agents de codage :

#### A. Le Graphe comme "Orchestrateur d'États" (State Graph / LangGraph)
C'est exactement ce que tu fais avec *smolagents*. Les projets suivants gèrent le workflow (Planner -> Coder -> Tester) comme un graphe de machines à états :
- **[Open SWE](https://github.com/langchain-ai/open-swe)** : C'est un agent de codage open-source construit sur LangGraph par l'équipe LangChain. Il est conçu pour reproduire l'architecture des gros agents internes des entreprises (comme ceux qui créent des Pull Requests automatiquement). Ils gèrent très bien l'orchestration asynchrone des sous-agents.
- **[Nexus](https://github.com/bradAGI/awesome-cli-coding-agents)** (et autres CLI) : Un agent CLI autonome qui utilise LangGraph pour gérer sa machine à états (séparation claire entre le mode "Architecte/Planification" et "Code"), tout en persistants le contexte dans une base SQLite (très proche de la vision d'`openfox`).

#### B. Le Graphe comme "Carte de Connaissances" (Code Knowledge Graph)
Plutôt que d'utiliser de simples embeddings vectoriels (RAG classique), ces projets transforment le code en un véritable Graphe (Nœuds = Fonctions/Classes, Arêtes = Appels/Dépendances). 
- **[Axon](https://github.com/harshkedia177/axon)** / **[Graphify](https://github.com/Graphify-Labs/graphify)** : Ces outils indexent le code source pour créer un Knowledge Graph interrogeable. Au lieu que le LLM lise du texte, il "navigue" dans le graphe (ex: "Trouve toutes les fonctions qui appellent la classe X").
- **Pourquoi c'est intéressant pour Graph Engineering :** Coupler ton orchestrateur (le graphe d'états de *smolagents*) avec un graphe de connaissances du code (comme alternative à `repomap` de Aider) serait la combinaison ultime pour un Coder IA fonctionnant avec de petits LLMs locaux (qui ont de petites fenêtres de contexte).

### 9. Fichiers clés à explorer dans les dépôts clonés (Code local)
J'ai cloné tous les dépôts mentionnés ci-dessus dans ton dossier `references/`. Voici les chemins exacts des fichiers locaux que tu dois absolument ouvrir pour voir comment ils ont codé tout ça en Python :

* **Pour l'architecture "State Graph" (LangGraph)** :
  - L'orchestrateur de `open-swe` : [open-swe/agent/scheduler.py](file:///D:/GIT/graph-orchestrator-smolagents/references/open-swe/agent/scheduler.py) (Regarde la syntaxe `builder = StateGraph(...)` et comment ils ajoutent les nœuds et les arêtes).
  - La machine à état de `LlamaBot` : [LlamaBot/app/agents/leonardo/rails_ai_builder_agent/nodes.py](file:///D:/GIT/graph-orchestrator-smolagents/references/LlamaBot/app/agents/leonardo/rails_ai_builder_agent/nodes.py) (Un excellent exemple de définition complète des transitions).

* **Pour le "Code Knowledge Graph" (Tree-sitter)** :
  - Le parseur Python de `axon` : [axon/src/axon/core/parsers/python_lang.py](file:///D:/GIT/graph-orchestrator-smolagents/references/axon/src/axon/core/parsers/python_lang.py) (Il montre exactement comment instancier `tree_sitter_python` pour extraire toutes les fonctions d'un fichier Python afin d'en faire une carte mentale pour l'agent).

### 10. Les "System Prompts" des agents (Planification & Exécution)
Suite à ta demande, j'ai cherché comment ces agents gèrent leurs System Prompts pour la phase de "Planification" et de "Build/Code". Le fichier le plus précieux que j'ai trouvé est **[open-swe/agent/prompt.py](file:///D:/GIT/graph-orchestrator-smolagents/references/open-swe/agent/prompt.py)**. 

C'est une véritable mine d'or. Ils ne donnent pas un seul gros prompt statique. Ils "construisent" le prompt dynamiquement selon l'état du graphe. Voici les meilleures idées à voler pour tes propres prompts système :

#### A. Le Mode "Plan" (Strictement Read-Only)
Dans Open-SWE, quand l'agent est en mode "Plan", son prompt (`PLAN_MODE_SECTION`) est ultra strict :
> *"You are in a read-only research-and-planning phase. Until `approve_plan` succeeds, you MUST NOT edit files inside the repo, run state-changing commands (no git commit, no push). You MAY use read tools (grep, ls, cat) and write a plan in `/workspace/plans/`."*
**Pourquoi c'est génial :** Ça garantit que ton "Architecte" ne va pas commencer à coder ou casser le projet. Il n'a littéralement pas le droit (ni les outils) pour le faire. Son seul but est de produire un fichier Markdown structuré (le fameux "Contract").

#### B. La Règle d'Autonomie Pure
Leur prompt de base (`OPEN_SWE_SHARED_BASE`) dicte exactement l'état d'esprit d'une "Usine Autonome" :
> *"Persistence: Keep working until the task is completely resolved. Only stop when the task is done or you are genuinely blocked... Autonomy: Don't ask for permission to take the obvious next step."*
**À copier :** Pour ton système "Fire and Forget", ton prompt système doit explicitement interdire au modèle de s'arrêter pour poser une question, sauf s'il active le Circuit Breaker.

### 11. Le Piège Invisible : L'Étouffement de la Fenêtre de Contexte (Context Overflow)
En tant qu'Agent IA, s'il y a bien une chose qui me tue dans une boucle "autonome", c'est la mémoire. J'ai remarqué qu'il manque un concept fondamental dans notre architecture actuelle pour `Graph Engineering` : **La gestion du contexte au fil des boucles.**

**Le Problème :**
Si ton "Coder" échoue 4 fois de suite, ton orchestrateur va empiler dans le prompt :
`Tentative 1 + Erreur 1 + Tentative 2 + Erreur 2 + Tentative 3 + Erreur 3...`
Avec un petit modèle local (Gemma 8B = 8k tokens de contexte), au bout de la 4ème itération, le modèle va "oublier" les instructions initiales de l'Architecte, ou carrément crasher (Out of Memory).

**La Solution (Ce que font Aider et mes propres outils) :**
Dans un graphe autonome, tu dois implémenter un nœud de "Compression" ou de "Nettoyage" :
1. **Tronquer les logs d'erreurs :** Ne donne jamais tout le `stderr` brut de Python s'il fait 500 lignes. Coupe-le pour ne garder que les 20 premières et les 20 dernières lignes.
2. **Summarizer Node :** Si `retry_count > 2`, avant de renvoyer la balle au "Coder", passe par un nœud "Summarizer" (avec un LLM très rapide/léger) qui lit l'historique et le remplace par un résumé strict : *"J'ai essayé X, ça a planté avec l'erreur Y. Je ne dois pas refaire X."*
3. **Le format `smolagents` (CodeAgent) :** Utilise la fonctionnalité native de *smolagents* qui génère du Python (`CodeAgent`) plutôt que du JSON (`ToolCallingAgent`). C'est beaucoup plus robuste pour les petits LLMs locaux et ça gère mieux la taille du contexte.

### 12. La Gestion Autonome des Dépendances (L'Enfer du ModuleNotFoundError)
Dans une usine autonome, le LLM va inévitablement écrire du code qui utilise de nouvelles librairies (ex: `requests`, `numpy`, ou `beautifulsoup4`). 
Si ton nœud "Tester" se contente de faire `python script.py`, il va immédiatement crasher avec un `ModuleNotFoundError`. Puisqu'il n'y a pas d'humain pour taper `pip install`, le système va boucler et échouer.
**La Solution :** Ton nœud "Tester" (ou l'agent lui-même via un outil) doit être capable de parser les erreurs `ModuleNotFoundError` et d'exécuter `pip install` ou `uv add` automatiquement avant de relancer le test, OU bien s'exécuter dans un bac à sable comme `E2B` qui gère ça dynamiquement.

### 13. La Persistance d'État (Checkpoints)
Si ton usine logicielle tourne pendant 2 heures la nuit, et que ton script Python plante (coupure réseau, bug API), tu perds tout l'historique de la réflexion.
**La Solution :** Dans les frameworks graphes comme LangGraph, on utilise un `Checkpointer` (souvent adossé à SQLite, comme on l'a vu dans *OpenFox* ou *Nexus*). À chaque fois que tu passes d'un nœud à l'autre (ex: de Architect à Coder), l'état global du graphe (`GraphState`) est sauvegardé sur le disque. Si ça crashe, tu relances le script et il reprend exactement au nœud où il s'était arrêté !

---

## 🎯 Conclusion & Architecture Maîtresse pour "Graph Engineering"
Si ton objectif final est un **système autonome "Fire and Forget"** (Zéro humain dans la boucle après le prompt initial), l'architecture doit s'éloigner de l'assistant interactif pour devenir une véritable **Usine Logicielle**. 

Voici le schéma architectural (Le "Master Blueprint") regroupant absolument tout ce qui différencie un petit script IA d'un véritable système de production industriel (comme Devin ou Open-SWE) :

### 1. Phase de Planification (Architect Node)
- **Prompts Read-Only** : L'agent n'a pas le droit de modifier le code.
- **Livrable** : Un fichier Markdown strict (`contract.md`) généré dans un dossier isolé, contenant les tests à passer (Test-Driven Development absolu).

### 2. Phase de Code (Coder Node)
- **Repo Map** : Le LLM ne lit pas tous les fichiers, il reçoit un arbre symbolique (généré via *Tree-sitter* ou *Ctags*).
- **Édition Sécurisée** : Format `SEARCH/REPLACE` (pas de JSON) protégé par un **Mutex** par fichier pour éviter les corruptions asynchrones.

### 3. Phase de Test (Tester Node)
- **Auto-Installation** : Capacité à parser les `ModuleNotFoundError` pour installer les dépendances manquantes (`pip`/`uv`) à la volée ou via sandbox (E2B).
- **Linter Feedback** : Le nœud exécute le code et capture le `stderr` brut pour le renvoyer au Coder.

### 4. Phase d'Orchestration (Le Graphe)
- **Coupe-Circuit (Circuit Breaker)** : Un compteur `max_retries` sur l'arête `Tester -> Coder` qui bascule sur un LLM distant (Judge) au bout de 3 échecs.
- **Context Management** : Un nœud de résumé (Summarizer) ou un algorithme de troncature qui nettoie les longs logs d'erreurs pour éviter l'explosion de la mémoire (Out of Memory).
- **Checkpoints (Persistance)** : L'état du graphe (`GraphState`) est sauvegardé sur SQLite à chaque transition. En cas de coupure de courant, l'usine reprend son travail exactement au nœud précédent.

Ton projet est sur la bonne voie pour implémenter cette architecture d'avant-garde via *smolagents* !
