# Méthodologie d'audit sécurité manuel (= spec du Security Reviewer idéal)

Ce document décrit **exactement** ce que je fais (l'agent) quand je joue le nœud Security
Reviewer à la main, étape par étape. C'est le cahier des charges du Security Reviewer idéal.

## Rôle du nœud Security Reviewer

**Entrée** : `subtask` dict avec `target_files` (code sur disque à lire) + `id`.

**Sortie** : `SecurityOutput(task_id, is_secure: bool, vulnerabilities: List[str],
findings: List[Finding])` où chaque finding = `{severity, category, location, description,
suggestion}` (rubric OWASP Top 10 + scores CVSS, defensive-only, F-44).

Le Security Reviewer cible les **failles de sécurité** (XSS, eval, injection SQL, SSRF…),
distinct du Linter (syntaxe) et du Tester (comportement). Il est **defensive-only** : il ne
propose jamais d'attaque, seulement des mitigations.

## La grille OWASP Top 10 (ce que je cherche, par catégorie)

| Catégorie | Patterns dangereux (grep) | Severity typique |
|---|---|---|
| **A03 Injection (XSS)** | `innerHTML`, `outerHTML`, `document.write`, `insertAdjacentHTML` avec input utilisateur non échappé | **high** (si input externe) |
| **A03 Injection (SQL)** | concaténation de string dans une requête SQL (`"... " + var`), f-strings dans SQL | **critical** (si input externe) |
| **A03 Injection (command)** | `os.system`, `subprocess.run(shell=True)` avec input, `eval()`, `exec()` | **critical** (RCE) |
| **A02 Crypto** | `hashlib.md5/sha1`, mots de passe en dur, `random` (pas `secrets`) pour tokens | **medium/high** |
| **A01 Access Control** | absence de check d'auth, IDOR (accès direct par ID sans vérif), `debug=True` en prod (Flask) | **high** |
| **A05 Misconfig** | CORS `*`, `ALLOWED_HOSTS = ['*']`, secrets en clair dans le code, `verify=False` TLS | **medium** |
| **A07 XSS (stockée)** | input utilisateur persisté sans échappement puis réaffiché | **high** |
| **A09 Logging** | logs de données sensibles (mot de passe, token), absence de logs sécurité | **low** |
| **A08 Désérialisation** | `pickle.loads`, `yaml.load` (sans Loader safe), `eval` de JSON externe | **high** |

## Les étapes (dans l'ordre, fail-fast)

### Étape 1 — Lire le code généré
**Ce que je fais** : je `Read` chaque fichier de `subtask.target_files`. J'ai besoin du code
**réel** pour auditer — pas d'hypothèses.
**Outil** : `Read`
**Coût** : 0 LLM, dépend de la taille

### Étape 2 — Scan des patterns dangereux (grep ciblé OWASP)
**Ce que je fais** : pour CHAQUE catégorie du tableau OWASP ci-dessus, je `grep` les
patterns dangereux dans le code lu.
**Outil** : `grep -nE "<pattern>"` sur le fichier
**Coût** : 0 LLM, instantané
**Patterns grep clés** (liste non exhaustive, le tableau ci-dessus est la source) :
```
grep -nE "innerHTML|outerHTML|document\.write|insertAdjacentHTML"   # XSS DOM
grep -nE "eval\(|new Function\(|setTimeout\([^,]*[a-zA]"            # injection JS
grep -nE "os\.system|subprocess\.(run|call|Popen).*shell=True"      # command injection
grep -nE "SELECT.*\+|INSERT.*\+|f[\"'].*SELECT"                      # SQL concat
grep -nE "pickle\.loads|yaml\.load\(|json\.loads.*input"            # désérialisation
grep -nE "md5|sha1|password\s*=\s*[\"']|api[_-]?key\s*=\s*[\"']"    # crypto/secrets
grep -nE "verify=False|CORS.*\*|ALLOWED_HOSTS.*\*|debug\s*=\s*True" # misconfig
```
**Échec type détecté** : `innerHTML = "Bonjour " + userInput` (XSS DOM, le classique).

### Étape 3 — Analyser le contexte (input externe ou contrôlé ?)
**Ce que je fais** : un pattern dangereux n'est une vuln que si l'input est **externe**
(utilisateur, URL, base de données). Je vérifie la **source** de la donnée utilisée.
**Outil** : lecture du flux de données (d'où vient la variable ?)
**Exemple discriminant** :
- `innerHTML = "<b>" + name + "</b>"` où `name` vient de `URLSearchParams` → **XSS high**
  (input externe, non échappé).
- `innerHTML = "<b>" + "Page" + "</b>"` (constante) → **pas une vuln** (input contrôlé).
**Échec type évité** : faux positif sur un `innerHTML` utilisé avec une constante. La sévérité
dépend de la **source** de l'input, pas seulement du pattern.

### Étape 4 — Évaluer la sévérité (CVSS approximatif)
**Ce que je fais** : pour chaque vuln confirmée (étape 3), j'assigne une severity selon
l'impact + l'exploitabilité.
**Outil** : mon jugement (heuristique CVSS simplifiée)
**Grille** :
- **critical** : RCE possible (`eval` input externe, command injection), injection SQL avec
  input externe. CVSS ≈ 9-10.
- **high** : XSS avec input externe, désérialisation non safe, contrôle d'accès absent sur
  fonction sensible, mot de passe en dur. CVSS ≈ 7-8.9.
- **medium** : crypto faible (md5), misconfig (CORS *, debug=True), secrets faibles. CVSS ≈
  4-6.9.
- **low** : absence de logging, comment de sécurité, headers manquants. CVSS ≈ 1-3.9.

### Étape 5 — Rédiger les findings (defensive-only, suggestions concrètes)
**Ce que je fais** : pour chaque vuln, je produis un finding `{severity, category,
location, description, suggestion}`. La suggestion est **defensive-only** : comment
**mitiger**, jamais comment exploiter.
**Bon exemple** :
```
{severity: "high", category: "XSS", location: "app.js:42",
 description: "innerHTML reçoit userInput (URLSearchParams) sans échappement → injection HTML/JS",
 suggestion: "Utiliser textContent au lieu de innerHTML, ou échapper le HTML (< → &lt;)"}
```
**Mauvais exemple** : suggestion absente, ou suggestion qui décrit l'attaque au lieu de la
mitigation.

### Étape 6 — Décider `is_secure`
**Ce que je fais** : `is_secure = (aucune finding de severity critical/high)`. Les
medium/low sont notés (findings) mais ne rendent pas le code "insécure" au sens bloquant
(le Judge décide ensuite, F-44).
**Règle** : critical/high → `is_secure=False`. Sinon → `is_secure=True`.

## Ordre optimal (fail-fast)

```
1. Read code (tous les target_files)          ──▶ connaissance du code réel
   │
   ▼
2. grep patterns OWASP (8 catégories)         ── 0 match ──▶ is_secure=True (code propre)
   │ matches
   ▼
3. Contexte : input externe ou contrôlé ?     ── contrôlé ──▶ pas une vuln (skip)
   │ externe
   ▼
4. Sévérité (CVSS approximatif)               ──▶ critical/high/medium/low
   │
   ▼
5. Findings defensive (suggestions de fix)    ──▶ findings[]
   │
   ▼
6. is_secure = (0 critical/high)              ──▶ SecurityOutput
```

## ⚠️ BIAIS — Les pièges du Security Reviewer (vécus)

**Biais n°1 — Faux positifs sur patterns constants**. Un `innerHTML` utilisé avec une
chaîne littérale n'est PAS une vuln. Contre-mesure : toujours vérifier la **source** de
l'input (étape 3) avant de flagger.

**Biais n°2 — Sur-détecter sur du code client (navigateur)**. Le JS navigateur est par
nature exposé — un `eval` sur une constante locale n'est pas une RCE serveur. Ajuster la
severity au **contexte** (navigateur vs serveur).

**Biais n°3 — Décrire l'attaque au lieu de la mitigation**. Le Security Reviewer est
**defensive-only** (F-44). La suggestion décrit comment **se protéger**, jamais comment
exploiter. Contre-mesure : relire chaque suggestion — si elle ressemble à un tutoriel
d'attaque, la reformuler en mitigation.

**Biais n°4 — Ignorer les misconfig**. Les patterns comme `debug=True` (Flask), `CORS *`,
`ALLOWED_HOSTS=['*']` sont souvent oubliés (pas du code métier). Contre-mesure : le grep
étape 2 les couvre explicitement.

**Biais n°5 — Oublier les secrets en clair**. `api_key = "sk-xxx"` ou `password = "admin"`
dans le code source est un finding high (fuite si commit). Contre-mesure : grep
`password\s*=\s*["']` et `api[_-]?key\s*=\s*["']` systématiquement.

## Pourquoi cette méthode plutôt que le LLM Security (gemma-12B)

| Critère | Security LLM (12B, think=False) | Méthode manuelle |
|---|---|---|
| Temps | ~15s-1 min | ~1-2 min (lecture + grep) |
| Détection patterns OWASP | Variable (peut oublier une catégorie) | **Systématique** (grep par catégorie) |
| Faux positifs (constantes) | Variable | **Éliminés** (vérif source étape 3) |
| CVSS / severity | Bon | Heuristique (grille simplifiée) |
| Suggestions defensive | Variable | **Garanties** (relecture anti-attaque) |

**Conclusion** : la détection (étapes 2-3) est **plus fiable en manuel** qu'en LLM — le grep
par catégorie OWASP est systématique (l'LLM peut oublier une catégorie), et la vérification
de la source de l'input élimine les faux positifs. Le LLM 12B apporte de la valeur sur
l'**évaluation CVSS fine** et la **rédaction des suggestions** (formulation pédagogique), mais
la couverture brute (quelles vulns existent) est meilleure en déterministe.
