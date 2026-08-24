"""Tests F-167 — densité prescriptive du draft Drafter.

Leçon F164-6 + A/B F-167 (2026-08-24) : le FORMAT DE SORTIE creux du prompt
Drafter (introduit F-150/F-154 le 22/08) faisait cloner à Ornith-1.0 ET 1.5 le
même draft creux de 1260 octets — variables :root listées sans valeurs, hauteurs
% sans parent px. Le Coder 4B suit le draft à la lettre → :root jamais écrit
(thème mort) + board vide au chargement. Trois gardes testées ici :

  1. draft_gate : détermination déterministe des 2 signatures de creux (draft
     réel du run 1448 — identique octet pour octet à ceux des runs 0857 et
     isolation — rejeté ; golden run #19 du 18/08 passe).
  2. build_density_feedback : bloc de feedback retry injectable au Drafter.
  3. workflows._drafter_with_density_retry : retry UNIQUE avec feedback, sans
     polluer le sub_dict du Coder ; rejets structurels = pas de retry (zéro
     direct F-91 historique) ; crash Drafter = pas de draft.
"""

import asyncio
from types import SimpleNamespace

from graph_orchestrator.draft_gate import (
    DENSITY_REJECT_KINDS,
    build_density_feedback,
    check_draft,
)
from graph_orchestrator.workflows import _drafter_with_density_retry


# Le draft creux EXACT du run 1448 (2026-08-24, E2E post-F-166) — identique à
# celui du run 0857 et aux reproductions isolation A/B (Ornith-1.0 comme 1.5) :
# variables listées sans valeurs + hauteur % sans référent px.
HOLLOW_RUN1448 = """## Fichier : index.html
- Structure : `<div id="app">` → `<h1>`, `<div id="board">`, bloc contrôles.
- IDs : `#board`, `#start-btn`, `#reset-btn`, `#speed-slider` (range 100-2000, value 500), `#value-display`, `#comparison-counter`.
- `<link>` vers styles.css, `<script src="script.js">` en fin de body.

## Fichier : styles.css
- `:root` : `--bg`, `--surface`, `--text`, `--default`, `--comparing`, `--sorted`, `--accent`.
- Flex layout, `#board` align-items flex-end, `.bar` avec transition height + background.
- Classes : `.comparing` (bleu), `.sorted` (vert), `.default` (gris).
- Responsive via media query.

## Fichier : script.js
- Vars : `arr`, `n=50`, `isSorting`, `speed`, `comparisons`, `bars[]`.
- `sleep(ms)` : Promise + setTimeout unique.
- `generateArray()` → `draw()` (hauteur `(v/100)*100%`, classe `.default`).
- `updateBar(i)` sync, `swap(i,j)` sync (échange + MAJ hauteur).
- `bubbleSort()` async : par comparaison incrémenter compteur + `.comparing` sur j,j+1 + `await sleep(speed)` + comparer + swap → `.sorted` + retirer `.comparing`; marquer triées à la fin de chaque `i`.
- Listeners : start (guard `!isSorting`), reset (`generateArray`), speed (live update).
- `init()` robuste via `document.readyState`."""

# Le draft dense du golden run #19 (2026-08-18, livrable parfait en 1 itération) —
# embedding complet : preuve byte-exact qu'aucun des nouveaux checks ne le rejette.
GOLDEN_RUN19 = """## Fichier : index.html

**Structure :**
- `<div id="container">` conteneur principal flex
- `<h1 id="title">` titre "Bubble Sort Visualizer"
- `<div id="chart">` conteneur des barres (flex, gap)
- `<div id="controls">` flex row avec :
  - `<button id="startBtn">` Start Sort
  - `<button id="resetBtn">` Reset
  - `<input id="speedRange" type="range" min="1" max="100">` slider vitesse
  - `<span id="counter">` compteur comparaisons
- `<script src="script.js"></script>`

**IDs DOM exacts :** container, title, chart, startBtn, resetBtn, speedRange, counter

**Initialisation :** appeler `generateArray()` au chargement pour afficher ≥1 barre immédiatement.

---

## Fichier : styles.css

**Thème sombre avec variables CSS :**
- `--bg: #1a1a2e`, `--bar-default: #6366f1`, `--comparing: #f59e0b`, `--sorted: #10b981`, `--text: #e2e8f0`
- Body : bg `--bg`, text `--text`, font sans-serif, margin 0, padding 20px
- `#container` : display flex, flex-direction column, align-items center, max-width 900px, margin auto
- `#chart` : display flex, gap 4px, height 200px, align-items flex-end, overflow-x auto
- `.bar` : width 20px, min-width 20px, transition height 0.3s ease, transition background-color 0.3s ease, border-radius 3px 3px 0 0, flex 1
- `#controls` : display flex, gap 12px, align-items center, margin-top 20px, flex-wrap wrap
- `#startBtn` : bg `--sorted`, color white, padding 10px 20px, border none, border-radius 6px, cursor pointer, font-weight bold
- `#resetBtn` : bg `--comparing`, color white, padding 10px 20px, border none, border-radius 6px, cursor pointer
- `#speedRange` : width 150px
- `#counter` : font-size 16px, color `--text`
- **Responsive :** `@media (max-width: 600px)` → max-width 100%, padding 10px, gap 2px, bar width 15px, font-size 14px

---

## Fichier : script.js

**Variables globales :**
- `arr = []` tableau de valeurs
- `isSorting = false` verrouillage pendant le tri
- `speed = 50` délai par défaut (ms)
- `comparisons = 0` compteur
- `N = 30` nombre d'éléments
- `maxVal = 100` valeur max

**Fonctions :**

1. **`generateArray()`**
   - Créer tableau `arr` de N valeurs aléatoires entre 1 et maxVal
   - Appeler `draw()` pour afficher les barres
   - Reset `comparisons = 0`

2. **`draw()`**
   - Nettoyer `#chart`
   - Pour chaque valeur dans `arr` :
     - Créer `<div class="bar">` avec `style.height = value + 'px'`
     - Ajouter au `#chart`
   - Utiliser `requestAnimationFrame` pour sync DOM après chaque ajout

3. **`bubbleSort()`**
   - Vérifier `!isSorting`, sinon return
   - Appeler `startBtn.disabled = true`
   - Boucle externe `while (true)` :
     - `let swapped = false`
     - Boucle interne `for (i = 0; i < arr.length - 1; i++)` :
       - Incrémenter `comparisons`
       - Si `arr[i] > arr[i+1]` :
         - Changer couleur des barres i et i+1 vers `--comparing`
         - Échanger `arr[i]` et `arr[i+1]`
         - Mettre à jour `bar.style.height` des deux barres correspondantes
         - `swapped = true`
       - `await sleep(speed)`
     - Si `!swapped` → break
   - Changer toutes les barres vers `--sorted`
   - Appeler `draw()` pour sync final
   - Appeler `startBtn.disabled = false`

4. **`sleep(ms)`**
   - `return new Promise(r => setTimeout(r, ms))`

5. **Event listeners:**
   - `startBtn` → `bubbleSort()`
   - `resetBtn` → `generateArray()`
   - `speedRange` → `speed = parseInt(this.value)`

**Edge cases:**
- Verrouillage `isSorting` empêche double clic Start Sort
- `await sleep` avec 1 itération par appel async (pas de boucle for complète)
- Sync DOM après chaque swap (hauteur + couleur)
- Init : `generateArray()` au chargement → ≥1 barre visible
- Responsive : layout s'adapte sans casser la visualisation"""

# Draft dense minimal (pour les tests retry) : valeurs + parent px + compteur sain.
DENSE = """## Fichier : styles.css
- Thème sombre : bloc :root complet `--bg: #0f172a; --text: #e2e8f0; --sorted: #22c55e;`
- #board : flex row, align-items flex-end, height 240px, gap 4px
- .bar : flex 1, height = (v/maxVal)*100%, transition height .3s ease

## Fichier : script.js
- Variables : arr[], N = 30, maxVal = 100, isSorting, speed = 50, comparisons = 0
- bubbleSort() : async, comparisons++ à CHAQUE paire testée AVANT l'éventuel swap,
  await sleep(speed), swap = échange + MAJ bar.style.height"""


class TestGateDensity:
    """Check_draft : les 2 signatures de creux (F-167)."""

    def test_run1448_hollow_draft_rejected_both_kinds(self):
        """Le draft creux réel (runs 1448/0857, cloné par 1.0 ET 1.5) est rejeté
        sur les DEUX signatures : variables sans valeurs + % sans parent."""
        result = check_draft(HOLLOW_RUN1448, spec_hint="visualizer animation")
        kinds = {i.kind for i in result.issues}
        assert result.should_reject
        assert "css_vars_no_values" in kinds
        assert "pct_height_no_parent" in kinds

    def test_golden_run19_passes(self):
        """Le golden #19 (draft dense, livrable parfait) : aucun rejet — les
        définitions AVEC valeurs et la référence parente px ne flaggent pas."""
        result = check_draft(GOLDEN_RUN19, spec_hint="visualizer animation")
        kinds = {i.kind for i in result.issues}
        assert not result.should_reject
        assert "css_vars_no_values" not in kinds
        assert "pct_height_no_parent" not in kinds

    def test_var_usage_not_flagged(self):
        """Les USAGES var(--x) ne sont pas des listes de définitions."""
        draft = "## styles.css\n- body { color: var(--text); background: var(--bg); }"
        result = check_draft(draft)
        assert not any(i.kind == "css_vars_no_values" for i in result.issues)

    def test_prose_reference_to_defined_vars_passes(self):
        """Une ligne qui RÉFÉRENCE en prose des variables définies ailleurs avec
        valeurs (pattern du golden : « Body : bg --bg, text --text ») passe."""
        draft = (
            "## styles.css\n"
            "- :root : `--bg: #1a1a2e`, `--text: #e2e8f0`\n"
            "- Body : bg `--bg`, text `--text`, font sans-serif\n"
        )
        result = check_draft(draft)
        assert not any(i.kind == "css_vars_no_values" for i in result.issues)

    def test_partial_definition_still_flagged(self):
        """Si certaines variables sont définies ailleurs mais pas toutes, la
        liste incomplète reste fautive (variables orphelines)."""
        draft = (
            "## styles.css\n"
            "- `:root` : `--bg`, `--surface`, `--text`.\n"
            "- ailleurs : `--bg: #111111`\n"
        )
        result = check_draft(draft)
        assert any(i.kind == "css_vars_no_values" for i in result.issues)

    def test_pct_height_with_px_parent_passes(self):
        """Hauteur % de barres AVEC hauteur fixe px du conteneur = sain."""
        draft = (
            "## styles.css\n- #board : height 240px, flex row, align-items flex-end\n"
            "## script.js\n- .bar height = (v/100)*100%\n"
        )
        result = check_draft(draft)
        assert not any(i.kind == "pct_height_no_parent" for i in result.issues)

    def test_pct_height_without_parent_rejected(self):
        """Hauteur % sans AUCUN px dans le plan = board vide → rejet."""
        draft = "## script.js\n- draw() : hauteur `(v/100)*100%`, classe .default"
        result = check_draft(draft)
        assert any(i.kind == "pct_height_no_parent" for i in result.issues)

    def test_px_heights_only_passes(self):
        """Un plan 100 % px (aucun pourcentage) ne déclenche pas le check."""
        draft = "## script.js\n- bar.style.height = value + 'px' (N = 30, maxVal = 100)"
        result = check_draft(draft)
        assert not any(i.kind == "pct_height_no_parent" for i in result.issues)


class TestDensityFeedback:
    """build_density_feedback : bloc de retry F-167."""

    def test_feedback_contains_both_signatures(self):
        result = check_draft(HOLLOW_RUN1448)
        feedback = build_density_feedback(result.issues)
        assert "DRAFTER GATE" in feedback
        assert ":root" in feedback  # correctif variables
        assert "hauteur FIXE" in feedback  # correctif parent px

    def test_feedback_empty_for_structural_only(self):
        """Un rejet structurel (placeholder) ne produit AUCUN feedback retry."""
        result = check_draft("## script.js\n- function main() { /* TODO */ }")
        assert result.should_reject
        assert build_density_feedback(result.issues) == ""

    def test_density_kinds_match_gate_kinds(self):
        """Les kinds du constant = exactement les kinds détectés comme rejetables."""
        assert DENSITY_REJECT_KINDS == {"css_vars_no_values", "pct_height_no_parent"}


class TestDrafterRetry:
    """workflows._drafter_with_density_retry : retry unique, sans pollution."""

    @staticmethod
    def _make_drafter(sequence):
        """Fake execute_drafter_node : consomme `sequence` (draft_markdown ou None).

        Retourne (fake_async, calls) — calls enregistre le subtask_dict de
        chaque appel pour vérifier contenu et non-pollution.
        """
        calls = []

        async def fake(subtask_dict, reasoning_model, settings):
            calls.append(subtask_dict)
            md = sequence[len(calls) - 1] if len(calls) <= len(sequence) else sequence[-1]
            if md is None:
                return None, None
            return SimpleNamespace(draft_markdown=md), SimpleNamespace(node="fake")

        return fake, calls

    def _run(self, fake):
        sub_dict = {
            "id": "st1",
            "content": "Sous-tâche d'origine",
            "strategy": "multifile",
            "target_files": ["index.html", "styles.css", "script.js"],
            "original_content": "visualizer animation spec",
        }
        metrics = []
        draft_res, gate = asyncio.run(
            _drafter_with_density_retry(sub_dict, None, SimpleNamespace(), metrics)
        )
        return draft_res, gate, sub_dict, metrics

    def test_retry_recovers_dense_draft(self, monkeypatch):
        """Creux au 1er appel → retry AVEC feedback → dense accepté. Le contenu
        d'origine du sub_dict n'est PAS pollué par le feedback."""
        fake, calls = self._make_drafter([HOLLOW_RUN1448, DENSE])
        monkeypatch.setattr(
            "graph_orchestrator.dspy_nodes.execute_drafter_node", fake
        )
        draft_res, gate, sub_dict, metrics = self._run(fake)

        assert len(calls) == 2
        assert "DRAFTER GATE" in calls[1]["content"]  # feedback injecté au retry
        assert calls[0]["content"] == "Sous-tâche d'origine"  # 1er appel propre
        assert sub_dict["content"] == "Sous-tâche d'origine"  # PAS de pollution
        assert draft_res is not None
        assert draft_res.draft_markdown == DENSE
        assert not gate.should_reject
        assert len(metrics) == 2

    def test_always_hollow_gives_up_after_single_retry(self, monkeypatch):
        """Toujours creux → exactement 2 appels, puis verdict rejeté consommé
        par l'appelant (Coder from scratch, sémantique F-91)."""
        fake, calls = self._make_drafter([HOLLOW_RUN1448])
        monkeypatch.setattr(
            "graph_orchestrator.dspy_nodes.execute_drafter_node", fake
        )
        draft_res, gate, _, metrics = self._run(fake)

        assert len(calls) == 2  # jamais 3
        assert gate.should_reject
        assert any(i.kind in DENSITY_REJECT_KINDS for i in gate.issues)
        assert len(metrics) == 2

    def test_structural_reject_has_no_retry(self, monkeypatch):
        """Un rejet NON densité (placeholder) ne consomme AUCUN retry —
        comportement F-91 historique préservé."""
        structural = "## script.js\n- function main() { /* TODO implémenter */ }"
        fake, calls = self._make_drafter([structural])
        monkeypatch.setattr(
            "graph_orchestrator.dspy_nodes.execute_drafter_node", fake
        )
        draft_res, gate, _, _ = self._run(fake)

        assert len(calls) == 1
        assert gate.should_reject
        assert all(i.kind not in DENSITY_REJECT_KINDS for i in gate.issues)

    def test_drafter_crash_first_call(self, monkeypatch):
        """Crash Drafter (None, None) → pas de draft, pas de gate, pas de retry."""
        fake, calls = self._make_drafter([None])
        monkeypatch.setattr(
            "graph_orchestrator.dspy_nodes.execute_drafter_node", fake
        )
        draft_res, gate, _, _ = self._run(fake)

        assert len(calls) == 1
        assert draft_res is None
        assert gate is None

    def test_drafter_crash_on_retry_keeps_rejection(self, monkeypatch):
        """Creux puis crash au retry → verdict rejeté du 1er draft conservé :
        l'appelant voit should_reject=True (Coder from scratch)."""
        fake, calls = self._make_drafter([HOLLOW_RUN1448, None])
        monkeypatch.setattr(
            "graph_orchestrator.dspy_nodes.execute_drafter_node", fake
        )
        draft_res, gate, _, _ = self._run(fake)

        assert len(calls) == 2
        assert gate is not None and gate.should_reject
