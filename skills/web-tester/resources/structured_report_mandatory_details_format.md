## Structured Report (mandatory `details` format)
Your `details` field MUST follow this structure (most important info first, it gets truncated):

```
VERDICT: success ou failure
ERREURS CONSOLE JS: <liste des erreurs/exceptions JS, ou "aucune">
ASSERTIONS FONCTIONNELLES:
  - <comportement testé 1>: PASS (résultat attendu confirmé)
  - <comportement testé 2>: FAIL — attendu: <X>, obtenu: <Y>
  - <comportement non testé car non applicable>: N/A
PROBLÈMES VISUELS: <bugs CSS/rendering observés, ou "aucun">
PROBLÈMES D'INTERACTION: <boutons/liens cassés, ou "aucun">
ÉTAPES POUR REPRODUIRE: <si failure, les étapes minimales pour reproduire le bug>
```
