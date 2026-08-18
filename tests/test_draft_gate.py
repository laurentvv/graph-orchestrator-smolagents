"""Tests du Draft Gate (F-91) — check flex_column_bars (run #14, F-124).

Le bug : le draft de l'Architect/Drafter prescrit un conteneur de barres en
`flex-direction:column` + `flex:1` sur les barres → flex-basis:0 écrase
style.height → 50 bandes horizontales égales pleine largeur (le Coder 4B suit
le draft à la lettre contre la règle flex ROW du skill coding). Le gate doit
REJETER le draft AVANT injection (le Coder part de zéro).

Déterministe, 0 LLM, 0 Chrome. Focus sur le check run #14 (les checks
historiques F-91 — placeholders, doublons, animation instantanée — sont
exercés en production depuis F-91).
"""

from graph_orchestrator.draft_gate import check_draft


# Le draft fautif du run #14 : géométrie column + flex:1 sur les barres.
_RUN14_FAULTY_DRAFT = """# Plan d'implémentation

## CSS

```css
#viz {
    display: flex;
    flex-direction: column;
    gap: 4px;
    height: 300px;
}

.bar {
    flex: 1;
    min-height: 4px;
    background: #ef5350;
}
```

## JS

```js
for (let i = 0; i < values.length; i++) {
    const b = document.createElement('div');
    b.className = 'bar';
    bars.appendChild(b);
}
```
"""

# Même visualiseur avec la géométrie CORRECTE (flex ROW, règle F-124).
_RUN14_CORRECT_DRAFT = """# Plan d'implémentation

## CSS

```css
#viz {
    display: flex;
    flex-direction: row;
    align-items: flex-end;
    height: 300px;
}

.bar {
    width: 12px;
    background: #ef5350;
}
```

## JS

```js
for (let i = 0; i < values.length; i++) {
    const b = document.createElement('div');
    b.className = 'bar';
    b.style.height = values[i] + 'px';
    bars.appendChild(b);
}
```
"""

# Layout légitime en colonne (panneaux de contrôles) : PAS un visualiseur à barres.
_LEGIT_COLUMN_LAYOUT = """# Plan

```css
.controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.btn {
    flex: 1;
}
```
"""


class TestFlexColumnBars:
    def test_rejete_draft_fautif_run14(self):
        """La signature exacte du run #14 (column + flex:1 + barres) → REJET."""
        res = check_draft(_RUN14_FAULTY_DRAFT)
        assert res.should_reject, "le draft flex-column barres DOIT être rejeté"
        kinds = [i.kind for i in res.issues]
        assert "flex_column_bars" in kinds
        issue = next(i for i in res.issues if i.kind == "flex_column_bars")
        assert issue.severity == "critical"
        assert issue.action == "reject"

    def test_la_correction_est_prescrite_dans_lissue(self):
        """La description de l'issue (affichée au rejet) doit citer la
        géométrie correcte (flex ROW + align-items:flex-end) pour le
        post-mortem — le draft rejeté n'est PAS injecté, donc pas de
        warnings_block dans ce chemin (réservé aux issues warn)."""
        res = check_draft(_RUN14_FAULTY_DRAFT)
        issue = next(i for i in res.issues if i.kind == "flex_column_bars")
        assert "flex ROW" in issue.description
        assert "align-items:flex-end" in issue.description

    def test_draft_correct_flex_row_passe(self):
        """Géométrie F-124 correcte → aucun rejet, aucune issue de géométrie."""
        res = check_draft(_RUN14_CORRECT_DRAFT)
        assert not res.should_reject
        assert "flex_column_bars" not in [i.kind for i in res.issues]

    def test_column_legitime_sans_contexte_barres_passe(self):
        """flex-direction:column pour des PANNEAUX (pas des barres) = légitime
        — les 3 conditions (column + flex:1 + contexte barres) doivent être
        réunies pour rejeter, sinon faux positif sur tout layout en colonne."""
        res = check_draft(_LEGIT_COLUMN_LAYOUT)
        assert not res.should_reject
        assert "flex_column_bars" not in [i.kind for i in res.issues]

    def test_draft_vide_noop(self):
        res = check_draft("")
        assert res.is_valid and not res.should_reject
