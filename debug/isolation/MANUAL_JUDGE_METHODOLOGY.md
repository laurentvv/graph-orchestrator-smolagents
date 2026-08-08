# Méthodologie de jugement manuel (= spec du Judge idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je joue le nœud Judge à la
main, étape par étape. C'est le cahier des charges du Judge idéal.

## Rôle du nœud Judge

**Entrées** (3) :
1. `subtask` : dict avec `target_files` (code sur disque à lire) + `original_content` (cahier
   des charges, le référence pour juger la couverture comportementale) + `id`.
2. `test_res` : le rapport du Tester (`Any` — souvent un `CoderOutput` stringifié, contient
   le statut success/failure + les assertions + les erreurs console).
3. `security_res` : `SecurityOutput` (is_secure + vulnerabilities + findings) — peut être None.

**Sortie** : `CodeJudgeOutput(task_id, is_approved: bool, final_feedback: str, findings[])`
où chaque finding = `{severity, category, location, description, suggestion}` et severity ∈
{critical, high, medium, low} (rubric F-44).

Le Judge est l'**arbitre final** de la boucle Coder↔Tester. `is_approved=True` → sous-tâche
validée, on passe à la suivante. `is_approved=False` → feedback persisté dans le KG, renvoyé
au Coder pour une nouvelle itération (max 3, puis escalade).

## La rubric de sévérité (F-44, la grille de décision)

| Severity | Critère | Impact sur is_approved |
|---|---|---|
| **critical** | Code qui ne compile pas / page blanche / fonctionnalité cœur absente / crash systématique | **is_approved=False** (toujours) |
| **high** | Faille de sécurité (XSS, RCE, injection), fonctionnalité cassée, bug logique sur comportement clé | **is_approved=False** (sauf si minoritaire et le reste marche) |
| **medium** | Bug sur fonctionnalité secondaire, erreur console non fatale, layout cassé sur un breakpoint | Juge au cas par cas (penser au coût d'une itération) |
| **low** | Nit cosmétique (variable mal nommée, commentaire manquant), typo | **Ne PAS rejeter pour des low seuls** (anti-nits F-44) |

## Les étapes (dans l'ordre)

### Étape 1 — Lire le code généré (in-diff only, pas de sur-analyse)
**Ce que je fais** : je `Read` chaque fichier de `subtask.target_files`. Je juge **uniquement
ce qui est dans le code réellement produit** — pas ce qui aurait pu être fait, pas du code
imaginaire. C'est le principe **in-diff only** (F-44).
**Outil** : `Read`
**Coût** : 0 LLM, dépend de la taille du fichier
**Échec type évité** : inventer un bug sur une fonctionnalité qui n'était même pas demandée
(sur-analyse). Je reste sur le périmètre du cahier des charges.

### Étape 2 — Vérifier la couverture comportementale vs le cahier des charges
**Ce que je fais** : pour CHAQUE fonctionnalité du `original_content` (cahier des charges),
je vérifie qu'elle est **présente ET implémentée** dans le code (pas juste déclarée).
**Outil** : `grep` ciblé par fonctionnalité + lecture
**Coût** : 0 LLM
**Tableau type** (Bubble Sort) :
| Fonctionnalité (cahier) | Présente ? | Implémentée ? | Finding |
|---|---|---|---|
| Bouton Démarrer | grep `startBtn\|Démarrer` | addEventListener attaché ? | si non → critical |
| Slider vitesse | grep `input.*range` | listener branché ? | si non → high (inactif) |
| Compteur comparaisons | grep `compteur\|comparison` | incrémenté dans la boucle ? | si absent → high |
| Tri croissant | fonction bubbleSort présente | logique correcte (> pas <) | si faux → critical |
**Échec type évité** : valider un code « qui ne crash pas » alors qu'une fonctionnalité cœur
est absente (le bug historique : Tester validait SUCCESS sur un bug visuel).

### Étape 3 — Interpréter le rapport du Tester (`test_res`)
**Ce que je fais** : je lis `test_res` (souvent stringifié). Je cherche : le **statut**
(success/failure), les **assertions fonctionnelles** (PASS/FAIL par assertion), les **erreurs
console JS**. Je ne prends pas le statut du Tester pour argent comptant — je **croise** avec
ma propre lecture du code (étape 1-2).
**Outil** : lecture
**Règle** : si le Tester dit FAILURE avec une assertion FAIL précise (ex: « tableau non trié,
obtenu [8,5,4,2,1] »), c'est un signal **fort** → critical. Si le Tester dit SUCCESS mais que
mon étape 2 a trouvé une fonctionnalité absente, je **défie** le Tester (le Tester peut rater
des choses).
**Échec type évité** : valider parce que le Tester a dit SUCCESS sans vérifier moi-même.

### Étape 4 — Consommer le rapport Security (`security_res`)
**Ce que je fais** : si `security_res` est fourni et `is_secure=False`, chaque finding de
severity high/critical DOIT être considéré comme bloquant. Je ne peux PAS approuver un code
avec une vulnérabilité high/critical non corrigée.
**Outil** : lecture de `security_res.findings`
**Règle** : high/critical security → `is_approved=False`. medium/low → juger au cas par cas.
**Échec type évité** : ignorer les vulnérabilités et approuver quand même.

### Étape 5 — Décision `is_approved` (la synthèse)
**Ce que je fais** : j'applique la grille de sévérité pour décider.
**Règle de décision** :
- **critical OU high présent** (logique ou security) → `is_approved=False`.
- **Uniquement medium/low** → `is_approved=True` (ne pas rejeter pour des nits, anti-nits
  F-44). Je note les medium/low dans findings pour info mais je n'inflige pas une itération
  coûteuse au Coder pour ça.
- **Rien** (code propre, tests pass, secure) → `is_approved=True`.

### Étape 6 — Rédiger `final_feedback` (actionnable, pas de nits)
**Ce que je fais** : si `is_approved=False`, j'écris un feedback que le Coder peut **agir
directement** dessus : problème précis + localisation + suggestion de fix. Pas de « le code
pourrait être meilleur » (non actionnable).
**Bon exemple** : « La fonction bubbleSort ligne 34 compare avec `<` au lieu de `>` → tri
décroissant au lieu de croissant. Inverser l'opérateur. »
**Mauvais exemple** : « Le tri ne marche pas bien. » (trop vague).
**Si `is_approved=True`** : feedback court positif (« Code conforme au cahier des charges,
tests pass, aucune vulnérabilité. »).

## Ordre optimal (fail-fast)

```
1. Read code (in-diff only)                    ──▶ connaissance du code réel
   │
   ▼
2. Couverture vs cahier des charges (grep)     ── non ──▶ critical → is_approved=False
   │ oui
   ▼
3. Lecture test_res (assertions, console)      ── FAIL assertion ──▶ critical → is_approved=False
   │ PASS
   ▼
4. Lecture security_res (vuln high/critical?)  ── oui ──▶ high → is_approved=False
   │ non / None
   ▼
5. Décision (grille severity)                  ──▶ is_approved = (0 critical/high)
   │
   ▼
6. final_feedback actionnable                  ──▶ findings[] + feedback
```

## ⚠️ BIAIS — Les pièges du Judge (vécus)

**Biais n°1 — Biais vers l'approbation**. Après 3 itérations (circuit breaker), la tentation
est d'approuver « pour en finir ». Contre-mesure : un critical/high reste bloquant **même à
l'itération 3**. Mieux vaut une escalade (post-mortem propre) qu'une validation bâclée.

**Biais n°2 — Sur-analyse (rejets pour des nits)**. Rejeter pour un nom de variable mal
choisi ou un commentaire manquant gaspille une itération coûteuse au Coder. Contre-mesure :
**anti-nits F-44** — les low seuls ne justifient JAMAIS un rejet. On les note en findings
pour info, point.

**Biais n°3 — Faire confiance aveugle au Tester**. Le Tester peut rater des choses (ou
faire des faux échecs, ex: assertion prématurée avant la fin d'une animation async).
Contre-mesure : **croiser** le rapport Tester avec ma propre lecture du code (étape 2). Si le
Tester dit FAIL mais que le code semble correct, je creuse (vrai bug ou faux échec ?).

**Biais n°4 — In-diff drift**. Juger le code **imaginaire** (ce que le Coder aurait dû faire
selon moi) au lieu du code **réel**. Contre-mesure : in-diff only — je ne flag que ce qui est
concrètement dans les fichiers lus à l'étape 1.

**Biais n°5 — Ignorer Security**. Approuver un code fonctionnellement correct mais avec une
faille high (XSS, eval). Contre-mesure : security_res high/critical = bloquant, point.

## Pourquoi cette méthode plutôt que le LLM Judge (gemma-12B)

| Critère | Judge LLM (12B, think=False) | Méthode manuelle |
|---|---|---|
| Temps | ~15s-1 min | ~1-2 min (lecture code) |
| Couverture vs cahier | Variable (peut oublier) | **Systématique** (grep par fonctionnalité) |
| Respect rubric severity | Bon | **Binaire** (grille de décision) |
| Anti-nits | Variable | **Garanti** (low seuls ≠ rejet) |
| Croisement Tester/Security | Variable | **Systématique** |

**Conclusion** : la grille de sévérité F-44 rend la décision `is_approved` **largement
déterministe** (critical/high → False, sinon True). Le LLM 12B apporte surtout de la valeur
sur la **rédaction du feedback** (formulation pédagogique) et le jugement des cas
**borderline** (medium pile-poil). La couverture fonctionnelle (étape 2) est plus fiable en
manuel (grep systématique) qu'en LLM.
