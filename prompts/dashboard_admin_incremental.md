# Dashboard Admin — Incremental Build Task

Cahier des charges pour le comparatif ToolCallingAgent vs CodeAgent (3e test, découpage incrémental).
Objectif : valider que le pattern squelette + append_file section par section rend la génération
de gros fichiers viable sur CPU-only (vs le pattern monolithique qui prenait 1h+ sans finir le step 1).

## ⚙️ WORKFLOW OBLIGATOIRE (découpage incrémental — NE TENTE PAS un seul write_file massif)

Construis le dashboard EN PLUSIEURS PETITES ÉTAPES avec append_file. Chaque appel doit rester
PETIT (< ~400 lignes) — c'est ce qui rend la génération viable. Procède EXACTEMENT ainsi :

1. **write_file(squelette)** — UNE SEULE FOIS. La structure HTML de base :
   - `<!DOCTYPE html>`, `<head>` (title, meta), `<body>` avec un `<div id="app">` vide.
   - Les balises `<style></style>` et `<script></script>` vides (tu les rempliras via append).
   - `< 80 lignes`. NE mets PAS encore le CSS/JS.

2. **append_file (CSS)** — le bloc `<style>...</style>` complet (design system, layout sidebar,
   KPI cards, table, responsive, dark/light mode).

3. **append_file (HTML sidebar + header)** — la structure de la sidebar et du header à l'intérieur de `<body>` / `<div id="app">`.

4. **append_file (HTML KPI cards)** — les 4 cartes KPI (Revenus, Utilisateurs actifs, Taux de
   conversion, Nouvelles commandes) avec leur markup.

5. **append_file (HTML tableau utilisateurs)** — le tableau avec ~12 utilisateurs factices.

6. **append_file (JS partie 1)** — initialisation, génération des données, rendu KPI.

7. **append_file (JS partie 2)** — logique de tri, recherche, pagination du tableau.

8. **append_file (JS partie 3)** — graphique canvas (dessin + tooltip + switch période), toasts, modal, toggle thème, toggle sidebar.

9. **final_answer** quand tout est assemblé.

**RÈGLE ANTI-BOUCLE** : UN seul append_file PAR section. Si append_file répond "Appended ... File now ...",
la section est FAITE — passe à la suivante. Ne ré-appelle PAS append_file avec le même contenu
(l'outil a une garde anti-doublon qui le détectera). Ne relis pas le fichier après chaque append.

## Spécification fonctionnelle du dashboard

Construis un Dashboard Administrateur COMPLET dans un SEUL fichier index.html (HTML5 + CSS3 + JavaScript vanilla, sans aucune librairie externe). Le fichier final doit être riche (~2500-3500 lignes) — la richesse vient de l'accumulation des sections, pas d'un seul gros bloc.

### Structure (layout)
- Sidebar fixe à gauche (240px) : logo, navigation (Tableau de bord, Utilisateurs, Produits, Commandes, Analytics, Paramètres), badge de notifications.
- Header : barre de recherche, icône notifications (compteur dynamique), avatar utilisateur avec menu déroulant (Profil, Déconnexion).
- Zone de contenu principale (scrollable) avec fil d'Ariane.

### Thème
- Design system avec variables CSS (--bg, --surface, --surface-2, --text, --muted, --accent, --success, --warning, --danger, --border).
- Dark mode par défaut + light mode (bouton toggle dans le header, persisté via localStorage).
- Responsive : sidebar repliable sous 768px (hamburger).

### Widgets tableau de bord (4 cartes KPI)
- Revenus (% d'évolution vs mois précédent, flèche verte/rouge).
- Utilisateurs actifs (même format).
- Taux de conversion (même format).
- Nouvelles commandes (même format).

### Tableau de données (Utilisateurs)
- ~12 utilisateurs factices (id, avatar initiale, nom, email, rôle [Admin/Editeur/Lecteur], statut [Actif/Inactif/Suspendu], date inscription, actions).
- En-têtes triables (clic = tri ascendant/descendant, icône flèche).
- Barre de recherche filtrant les lignes en temps réel.
- Pagination (5 lignes/page, boutons Précédent/Suivant + indicateur "Page X sur Y").

### Graphique (canvas, sans lib)
- Graphique en barres sur `<canvas>` (revenus sur 12 mois, valeurs aléatoires).
- Axe Y avec graduations, libellés des mois sur l'axe X, infobulle (tooltip) au survol d'une barre.
- Boutons de période : 7 jours / 30 jours / 12 mois (régénère les données et redessine).

### Interactions JS
- Tout doit être réellement fonctionnel : tri du tableau, recherche, pagination, dessin du graphique, switch de thème, toggle sidebar, menu déroulant.
- Toasts de notification (bas à droite) au clic sur "Actions" (Voir/Éditer/Supprimer).
- Modal de confirmation qui s'ouvre au clic sur "Supprimer".

### Qualité
- HTML5 sémantique, CSS organisé par sections commentées, JS modulaire (IIFE ou modules).
- Code prêt pour la production : aucune fonction vide, aucun placeholder TODO, tout câblé.
- Accessibilité : focus visible, rôles ARIA sur la navigation et le tableau, labels associés.
