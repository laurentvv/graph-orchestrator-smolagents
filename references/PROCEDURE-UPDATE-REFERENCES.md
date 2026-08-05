# Procédure : Mise à jour des références

> **Workflow reproductible** pour l'exécution périodique de mises à jour des dépôts dans `references/`.
> 
> **Objectif** : maintenir à jour l'usine logicielle avec les dernières découvertes de l'écosystème open source sans casser l'historique de réalisation ni altérer l'état de ce qui est déjà achevé.

---

## 🚀 Étape 1 — Lancement de la mise à jour

Exécuter le script de mise à jour pour synchroniser tous les sous-dépôts (`git pull`) et générer un rapport de différences.

### Commande
```bash
python references/update_references.py
```
*Le script va parcourir chaque dossier dans `references/`, faire un `git pull`, et écrire un compte rendu dans `references/update_report.md`.*

---

## 🔍 Étape 2 — Analyse des nouveautés

Ouvrir et lire le fichier généré : `references/update_report.md`.

**Objectif** : Identifier les nouveaux patterns, outils (Skills), ou workflows pertinents pour le projet (ex. nouveaux scripts MCP, nouvelles directives de prompt, etc.).
Vous pouvez vous aider de `references/PROCEDURE-AUDIT-REFERENCE.md` pour classer et évaluer la pertinence (🟢 Haute, 🟡 Moyenne, 🔴 Faible) des nouveaux éléments.

---

## 📝 Étape 3 — Mise à jour de `feature_list.json`

Pour chaque nouvelle idée ou brique actionnable identifiée, ajouter une nouvelle entrée dans le fichier `feature_list.json`.

**⚠️ RÈGLE CRITIQUE (INVARIANT) :**
- **NE JAMAIS MODIFIER** une fonctionnalité dont le statut est déjà `"completed"`.
- Tout ajout doit se faire sous forme de **nouvelle fonctionnalité** avec le statut `"pending"`.
- Si une fonctionnalité terminée a dû pivoter (changement de design majeur), **ne pas altérer la fonctionnalité terminée**. Créez une **nouvelle fonctionnalité** (ex: "Pivot v3 : ...") pour tracer ce changement de cap. Si vous modifiez des features déjà terminées, **elles ne seront pas prises en compte par le système**.

---

## 🗺️ Étape 4 — Mise à jour de `plan_usine_logicielle.md`

Intégrer les nouvelles fonctionnalités dans le backlog des priorités (P0 à P12) du fichier `plan_usine_logicielle.md`.

**⚠️ RÈGLE CRITIQUE (INVARIANT) :**
- **NE JAMAIS MODIFIER** les cases déjà cochées (`- [x]`) d'un plan terminé.
- Ajoutez les nouveautés uniquement sous forme de cases à cocher vides (`- [ ]`).
- Appliquez le formalisme habituel en citant la référence : `— *Référence : fiche **NN-<nom>** → ...*`

---

## 🔄 Étape 5 — Suivi du sprint courant (`progress.md`)

Mettez à jour `progress.md` pour refléter les avancées de l'itération en cours.
Ce fichier détaille les étapes microscopiques (jalons) du cycle actuel. Les notes et ajouts ne doivent se faire que sur les étapes non validées. Ne réécrivez pas le passé.
