# Audit comparatif : méthode manuelle (l'agent joue le nœud) vs nœuds de production

Ce rapport compare, pour chaque nœud, ma **méthode manuelle** (`MANUAL_<NODE>_METHODOLOGY.md`)
avec le **nœud de production réel** — en prenant en compte TOUS les composants branchés en
prod (prompt DSPy + rôles/invariants F-44 + skills + MCP Context7/DevTools + ajouts défensifs
truncate/sanitizer/loop_guard). Objectif : identifier où ma méthode fait mieux (gaps à
combler dans les prompts prod) et où la prod fait mieux (corriger mes docs).

C'est la **valeur de F-55** : les docs méthodologiques servent de benchmark pour auditer si
les nœuds de production font aussi bien que la méthode manuelle de référence.

## Synthèse exécutive

| Nœud | Périmètre prod | Verdict | Gaps majeurs |
|---|---|---|---|
| Router | prompt simple (0 skill, 0 MCP, 0 ajout) | 🔴 Ma doc > prod | mots-clés canoniques, règle extensions, justification |
| Architect | prompt + Context7 pré-fetch + think=True | 🟡 ÉCART BIDIRECTIONNEL | ma doc était **OBSOLÈTE sur F-15** (corrigé) ; ma doc > prod sur sections |
| Judge | prompt + rubric + truncate + security_res | 🟡 Ma doc > prod sur procédure | ordre fail-fast, grep par fonctionnalité, croisement défiant |
| Security | prompt + OWASP abstrait (0 ajout) | 🟡 Ma doc > prod sur couverture | grille OWASP concrète (patterns grep), vérif input externe |
| Linter | code déterministe (tree-sitter + py_compile) | 🟢 Doc fidèle | 1 vrai gap code : fichier absent = `is_valid=True` silencieux |

Légende : 🔴 gap prod majeur | 🟡 gaps bidirectionnels/nuances | 🟢 aligné.

---

## 1. Router — 🔴 ma méthode > prod (gaps clairs)

### Périmètre prod
`RouterSignature` (`dspy_nodes.py:40-50`) — docstring générique 5 lignes + rôle "router"
(`prompts.py:71-75`) + invariants universels. **Aucun skill, aucun MCP, aucun ajout
défensif.** Modèle fast think=False. Output `RouterOutput(language)` — **pas de champ
justification** (`models.py:78-80`).

### Gaps : ma méthode > prod
| Gap | Ma doc | Prod |
|---|---|---|
| Tableau mots-clés canoniques | 6 lignes par langage (`python`, `react`, `.tsx`, `cargo`...) | Absent (docstring générique L43-47) |
| Règle "extensions gagnent" | Étape 2 explicite : `target_files` = source de vérité | Absente. Le Router ne reçoit même pas `target_files` |
| Heuristique frontend-wins | Étape 3 multi-techno | Absente |
| 3 biais nommés | défaut javascript, html≠js, ignorer TS | Absents |
| Justification du verdict | Étape 4 obligatoire | `RouterOutput` n'a pas de champ |

### Recommandations (ajouts ciblés au prompt `RouterSignature`)
- **R1** — Injecter mini-tableau tokens canoniques (python/.py/pandas → python ; react/.tsx → typescript...).
- **R2** — Règle priorité : "si extensions de fichiers mentionnées, elles priment sur mots-clés".
- **R3** — Anti-biais (3 lignes) : ne pas déborder vers javascript par défaut ; HTML/CSS pur = html ; React/Next = typescript.
- **R4** — Ajouter `justification: str = ""` à `RouterOutput` pour auditabilité.

---

## 2. Architect — 🟡 écart BIDIRECTIONNEL (ma doc corrigée)

### Périmètre prod
`ArchitectSignature` (`dspy_nodes.py:88-135`) — docstring détaillé F-15/F-29 + rôle "architect"
(`prompts.py:77-83`, 5 axes senior + READ-ONLY) + invariants. **Context7 pré-fetch**
(`dspy_nodes.py:474-481` si `_mentions_external_lib`). **think=True (seul nœud)**. **Aucun skill**
(`BASE_SKILLS_BY_NODE["architect"]=[]`).

### Gap MAJEUR (sens inverse) — ma doc était OBSOLÈTE sur F-15 ✅ CORRIGÉ
Ma première version disait "**1 fichier = 1 sous-tâche**". C'est FAUX et c'est le **failure
mode n°1** selon le prompt prod (`dspy_nodes.py:93-97`) : découper un livrable par fichier fait
tester des fichiers isolés qui ne marchent pas seuls (index.html sans styles.css → rejet
systématique → boucle infinie). La vraie règle est **1 livrable testable = 1 sous-tâche**
(les fichiers liés sont regroupés en 1 sous-tâche `multifile`). **Doc corrigée** ce cycle
(étape 1 + biais n°1 réécrits).

### Gaps : ma méthode > prod
- **Squelette HTML en 1ère section** : ma doc impose `<!DOCTYPE>…</body></html>` comme socle
  (étape 3). La prod donne un exemple `['css','sidebar','kpi','js']` **sans ordre imposé**
  (`dspy_nodes.py:116`) → risque contenu après `</html>` (le bug dashboard).
- **Fourchette "3-7 sections"** par fichier incremental — absente du prompt prod.
- **Biais n°3 nommé** : confondre `multifile` et `incremental` (incremental sur Python = erreur).

### Gaps : prod > ma méthode
- Raisonnement **Test-driven du découpage** (L94-97) + 5 axes senior + READ-ONLY + 10 invariants.
- Cas d'usage ultra-précis (ex: "1 sous-tâche pour html+css+js liés").

### Recommandations (ajouts ciblés au prompt `ArchitectSignature`)
- Après L116 : *"La 1ère section DOIT être le squelette structural (ex: `<!DOCTYPE>…</body></html>`)."*
- Après L116 : *"Vise 3-7 sections par fichier incremental (~50-100 lignes chacune)."*
- Avertissement biais n°3 : *"ATTENTION : 'incremental' = UN gros fichier par morceaux. Ne mets JAMAIS 'incremental' sur un projet multifichier Python/TS — utilise 'multifile'."*

---

## 3. Judge — 🟡 ma méthode > prod sur procédure

### Périmètre prod
`CodeJudgeSignature` (`dspy_nodes.py:163-194`) — rubric critical/high/medium/low + in-diff
only + anti-nits + vérification comportementale (task_requirements). **`truncate_output`**
sur tests (L571) + task_requirements (L584, head=30/tail=10/max=1500). Consomme
`security_res` (L567 hasattr). Rôle "judge" (`prompts.py:108-114`). **Aucun skill.**

### Gaps : ma méthode > prod
- **Ordre de procédure imposé (fail-fast)** : ma doc impose Read → couverture → test_res →
  security → décision → feedback. Le prompt prod laisse le LLM **libre de sa séquence** — un
  12B peut juger avant d'avoir vérifié la couverture.
- **Grep systématique par fonctionnalité** : ma doc (étape 2) impose un tableau de couverture
  (Fonctionnalité | Présente ? | Implémentée ? | Finding). Le prompt prod dit "utilise
  task_requirements" **sans exiger une vérification point-par-point**.
- **Croisement défiant explicite** : ma doc impose de **défier le Tester** si SUCCESS mais
  fonctionnalité absente. C'est exactement ce qui a permis à la démo Judge de localiser
  l'opérateur fautif ligne 11 (`<` vs `>`) qu'un rapport Tester imprécis n'avait pas signalé.
- **5 biais nommés** (approbation de complaisance à l'itération 3, in-diff drift...) vs
  objectivity + anti-nits seuls.

### Gaps : prod > ma méthode
- **Protection contexte** (`truncate_output`) — absent du manuel (lecture hors-contexte).
- **Schéma Pydantic strict** force findings structurés. **Déterminisme** (exécutable à chaque run).

### Recommandations (ajouts ciblés au doc métier `CodeJudgeSignature`)
1. Imposer procédure ordonnée : "Procède dans cet ordre : (1) liste chaque exigence de task_requirements ; (2) vérifie présence+implémentation dans code ; (3) croise avec test_results ; (4) applique security_vulnerabilities ; (5) décide."
2. Exiger check couverture par exigence : "Pour CHAQUE exigence, atteste Présente/Implémentée/Testée avant de conclure."
3. Règle croisement défiant : "Si test_results dit PASS mais qu'une exigence n'est pas implémentée → finding critical, is_approved=False."
4. Localisation obligatoire : "Chaque finding DOIT citer ligne/fragment exact."

---

## 4. Security — 🟡 ma méthode > prod sur couverture OWASP

### Périmètre prod
`SecuritySignature` (`dspy_nodes.py:138-160`) — mention OWASP Top 10 + rubric CVSS +
defensive-only. Rôle "security" (`prompts.py:116-121`). Lit code depuis disque. **Aucun
truncate_output** (vs Judge L571/584), **aucun skill**. Code injecté **non tronqué**.

### Gaps : ma méthode > prod (le gap clé)
- **Pas de grille OWASP concrète**. Le prompt dit "XSS, injection..." en abstrait mais ne
  fournit **aucun pattern grep**. Ma doc donne une grille **actionnable** :
  `innerHTML`/`document.write` (A03 XSS), `os.system`/`subprocess shell=True`/`eval` (A03 cmd),
  concat SQL/f-strings, `pickle.loads`/`yaml.load` (A08), `md5`/`sha1`/`password=`/`api_key=`
  (A02), `verify=False`/`CORS *`/`debug=True` (A05) — avec sévérité typique par catégorie.
  Le prompt prod **omet A09 Logging** et ne nomme pas `pickle`/`verify=False`/secrets en clair.
- **Pas de vérification "input externe vs contrôlé"**. Ma doc élimine les faux positifs
  (innerHTML sur constante ≠ vuln). La prod ne mentionne pas la source de données → risque FP
  ou sous-détection sur un 12B sans think.
- **Pas de section "biais"** (FP constantes, sur-détection JS client, secrets oubliés).

### Gaps : prod > ma méthode
- **Schéma Pydantic strict** + JSON Mode forcé (F-44). **Dégradation gracieuse** (None,None).

### Recommandations (ajouts ciblés au `SecuritySignature`, L141-157)
1. **Liste de patterns dangereux concrets** par catégorie OWASP (reprendre le tableau ma doc
   L20-30) — pousse le modèle à chercher activement plutôt que d'"être exhaustif" en abstrait.
2. **Clause discrimination input** : "Confirme la source de la donnée avant de flagger
   (externe = vuln, littérale = FP)."
3. **Ajouter A09 Logging** explicitement (absent du prompt prod).
4. **Avertissement faux positifs** (constantes, JS client).
5. **Optionnel** : `truncate_output` sur `code_content` (L516) par parité avec Judge/Escalation.

---

## 5. Linter — 🟢 doc fidèle, 1 vrai gap code

### Périmètre prod
`linter.py` — nœud **déterministe 0-LLM** (le "prompt" = le code Python). tree-sitter (sauf
HTML) + py_compile (Python) + vérifs structurelles HTML. `execute_linter_node` (`linter.py:279-322`).

### Fidélité de ma doc
Ma doc est **un miroir très fidèle** du code (les 5 étapes, l'exception HTML, py_compile,
format details, dégradation gracieuse). Deux inexactitudes mineures à corriger dans la doc :
- Doc étape 4 dit vérifier `<!DOCTYPE>` comme test binaire ; le code le signale comme
  `[structure] Aucun <!DOCTYPE html> trouvé (recommandé).` (`:188-189`) mais ça fait quand
  même `is_valid=False` → un HTML sans DOCTYPE est **rejeté**, pas seulement signalé.
- Doc ne mentionne pas que fichier illisible/encodage cassé → **silencieusement
  `is_valid=True`** (`:238-239`) — un faux négatif possible.

### Gap code révélé par la doc (le vrai gap fonctionnel)
- **Fichier absent traité comme valide** (`linter.py:226-227`, `language="missing"`,
  `is_valid=True`). Si le Coder ne crée pas le fichier, le Linter passe — le Coder "réussit"
  sans livrer. Ma doc ne l'avait pas relevé. **Recommandation code** : envisager de traiter
  `language="missing"` comme `is_valid=False` (ou au moins remonter au Coder), sinon le Linter
  ne gate pas l'absence de livraison.

### Recommandations
- **Corriger ma doc** : préciser DOCTYPE = failure réelle ; documenter fail-open (illisible/absent).
- **Améliorer le code** : `language="missing"` → `is_valid=False` (le seul vrai gap fonctionnel).

---

## Conclusions transversales

**Pattern récurrent** : les prompts prod sont **bons sur les principes** (rubric, in-diff,
anti-nits, OWASP mentionné) mais **manquent de procédure opératoire concrète**. Ma méthode
manuelle apporte systématiquement :
1. **Un ordre fail-fast** (étapes numérotées) que les prompts prod n'imposent pas.
2. **Des patterns/grep concrets** (mots-clés Router, OWASP Security, couverture Judge) vs
   l'abstrait ("sois exhaustif").
3. **Des biais nommés + contre-mesures** que les prompts prod omettent.

**Hypothèse** : ces gaps sont la cause probable des failure modes observés en prod (Router
qui déborde vers javascript, Security qui rate pickle/secrets, Judge qui valide sans
vérifier la couverture). Combler ces gaps dans les prompts prod est un **cycle d'optimisation
future** (F-56 potentiel : "durcir les prompts prod avec la procédure concrète des docs
méthodologiques").

**Leçon F-55** : la valeur de ces docs n'est pas seulement de jouer les nœuds à la main —
c'est de servir de **benchmark** pour auditer la prod. L'audit ci-dessus a révélé 1 doc
obsolète (Architect corrigé) et ~15 recommandations d'amélioration des prompts prod.
