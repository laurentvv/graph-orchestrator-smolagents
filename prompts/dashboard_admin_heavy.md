# Dashboard Admin — Heavy Single-File Task

Cahier des charges pour le comparatif ToolCallingAgent vs CodeAgent (2e test, contenu lourd).
Objectif : pousser la limite du contenu inline (~2500-3500 lignes attendues) pour
déclencher le scénario-douleur historique du TCA (corruption JSON des gros contenus).

## Cahier des charges (à passer aux scripts)

Construis un Dashboard Administrateur COMPLET dans un SEUL fichier index.html (HTML5 + CSS3 + JavaScript vanilla, sans aucune librairie externe). Le fichier doit être riche et complet (~2500-3500 lignes) — ne sacrifie pas la qualité pour la brièveté.

### Structure (layout)
- Sidebar fixe à gauche (240px) avec : logo, navigation (Tableau de bord, Utilisateurs, Produits, Commandes, Analytics, Paramètres), et un badge de notifications.
- Header en haut : barre de recherche, icône notifications (compteur dynamique), avatar utilisateur avec menu déroulant (Profil, Déconnexion).
- Zone de contenu principale à droite (scrollable), avec un fil d'Ariane.

### Thème
- Design system avec variables CSS (--bg, --surface, --surface-2, --text, --muted, --accent, --success, --warning, --danger, --border).
- Dark mode par défaut + light mode (bouton toggle dans le header, persisté via localStorage).
- Responsive : sidebar repliable sous 768px (hamburger).

### Widgets du tableau de bord (4 cartes KPI)
- Revenus (avec % d'évolution vs mois précédent, flèche verte/rouge).
- Utilisateurs actifs (même format).
- Taux de conversion (même format).
- Nouvelles commandes (même format).

### Tableau de données (Utilisateurs)
- Tableau avec ~12 utilisateurs factices (id, avatar initiale, nom, email, rôle [Admin/Editeur/Lecteur], statut [Actif/Inactif/Suspendu], date inscription, actions).
- En-têtes triables (clic = tri ascendant/descendant, icône flèche).
- Barre de recherche qui filtre les lignes en temps réel.
- Pagination (5 lignes/page, boutons Précédent/Suivant + indicateur "Page X sur Y").

### Graphique (canvas, sans lib)
- Un graphique en barres dessiné sur <canvas> (revenus sur 12 mois, valeurs aléatoires).
- Axe Y avec graduations, libellés des mois sur l'axe X, infobulle (tooltip) au survol d'une barre affichant la valeur.
- Boutons de période : 7 jours / 30 jours / 12 mois (régénère les données et redessine).

### Interactions JS
- Toutes les interactions doivent être réellement fonctionnelles (pas de mocks statiques) : tri du tableau, recherche, pagination, dessin du graphique, switch de thème, toggle sidebar, menu déroulant avatar.
- Toasts de notification (en bas à droite) quand on clique sur "Actions" (ex: "Voir", "Éditer", "Supprimer" sur une ligne du tableau → toast correspondant).
- Modal de confirmation qui s'ouvre au clic sur "Supprimer".

### Qualité
- HTML5 sémantique, CSS organisé par sections commentées, JS modulaire (IIFE ou modules).
- Code prêt pour la production : aucune fonction vide, aucun placeholder TODO, tout est câblé.
- Accessibilité : focus visible, rôles ARIA sur la navigation et le tableau, labels associés.
