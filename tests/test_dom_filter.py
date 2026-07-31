"""Tests unitaires du Nettoyage DOM (Priorité 6 du plan usine logicielle, LlamaBot).

Valide le filtre de troncature HTML qui strippe <script>/<style>/<svg>/<canvas>/
<iframe>/<noscript>/<template>/<head> et les commentaires avant envoi au LLM.

Déterministe, 0 LLM, 0 navigateur. Couvre :
- Suppression de chaque famille de balises bruyantes (contenu inclus).
- Suppression des commentaires HTML.
- Préservation du contenu sémantique (texte, div, attributs id/class/aria-*).
- Compactage whitespace (espaces en fin de ligne, series de newlines).
- Troncature à max_chars (filet de sécurité).
- Cas limites : None, vide, HTML déjà propre.
- Variants auto-fermants et casse (XHTML/casse).
- Gain effectif (ratio de réduction sur un HTML réaliste).
"""
from graph_orchestrator.dom_filter import clean_dom_for_llm


# ==========================================
# Suppression des balises bruyantes (contenu inclus)
# ==========================================
def test_strips_script_block():
    """<script> et son contenu JS sont supprimés (le tester les a déjà exécutés)."""
    html = '<div id="app">Hello</div><script>console.log("bruit"); const x=42;</script>'
    out = clean_dom_for_llm(html)
    assert "<script>" not in out
    assert 'console.log' not in out
    assert 'Hello' in out  # contenu sémantique préservé


def test_strips_style_block():
    """<style> et le CSS sont supprimés."""
    html = '<p>texte</p><style>body { color: red; margin: 0; }</style>'
    out = clean_dom_for_llm(html)
    assert "<style>" not in out
    assert "color: red" not in out
    assert "texte" in out


def test_strips_svg_block():
    """<svg> (icônes vectorielles verbeuses) supprimé."""
    html = '<button>OK</button><svg viewBox="0 0 24 24"><path d="M0 0 L1 1"/></svg>'
    out = clean_dom_for_llm(html)
    assert "<svg" not in out
    assert "viewBox" not in out
    assert "OK" in out


def test_strips_canvas_block():
    """<canvas> (blob de pixels illisible) supprimé."""
    html = '<main>UI</main><canvas id="chart" width="800" height="600"></canvas>'
    out = clean_dom_for_llm(html)
    assert "<canvas" not in out
    assert "UI" in out


def test_strips_iframe_block():
    """<iframe> et son contenu imbriqué supprimés."""
    html = '<section>principal</section><iframe src="ad.html">fallback</iframe>'
    out = clean_dom_for_llm(html)
    assert "<iframe" not in out
    assert "principal" in out


def test_strips_head_block():
    """<head> (meta/link/title : bruit pour la logique applicative) supprimé."""
    html = '<head><title>Page</title><meta charset="utf-8"><link rel="stylesheet" href="x.css"></head><body><h1>Titre</h1></body>'
    out = clean_dom_for_llm(html)
    assert "<head" not in out
    assert "<title>" not in out
    assert "Titre" in out  # h1 préservé


def test_strips_all_noisy_tags_together():
    """Une page avec toutes les balises bruyantes mélangées → tout est nettoyé."""
    html = """
    <html>
      <head><title>T</title></head>
      <body>
        <div id="content">visible</div>
        <script>var a = 1;</script>
        <style>.x { color: blue; }</style>
        <svg><path d="M0"/></svg>
        <canvas></canvas>
      </body>
    </html>
    """
    out = clean_dom_for_llm(html)
    for noisy in ("<script", "<style", "<svg", "<canvas", "<head", "<title"):
        assert noisy not in out
    assert "visible" in out


# ==========================================
# Casse / variants auto-fermants (HTML malformé / XHTML)
# ==========================================
def test_case_insensitive():
    """<SCRIPT> en majuscules est aussi supprimé (HTML tolère la casse)."""
    html = '<p>ok</p><SCRIPT>alert(1)</SCRIPT>'
    out = clean_dom_for_llm(html)
    assert "<SCRIPT>" not in out
    assert "alert" not in out


def test_self_closing_svg():
    """Variants auto-fermants (XHTML) supprimés."""
    html = '<div>x</div><svg xmlns="http://www.w3.org/2000/svg" />'
    out = clean_dom_for_llm(html)
    assert "<svg" not in out


# ==========================================
# Commentaires HTML
# ==========================================
def test_strips_html_comments():
    """Les commentaires <!-- ... --> (gros contenu conditionnel) sont supprimés."""
    html = '<!--[if IE]><script>old code</script><![endif]--><p>ok</p>'
    out = clean_dom_for_llm(html)
    assert "<!--" not in out
    assert "old code" not in out
    assert "ok" in out


# ==========================================
# Préservation du contenu sémantique
# ==========================================
def test_preserves_semantic_content():
    """Le texte, div, attributs id/class/aria-* sont préservés (utiles aux assertions)."""
    html = (
        '<table id="data" class="grid" aria-label="Données">'
        '<tr><td role="cell">42</td></tr>'
        '</table>'
    )
    out = clean_dom_for_llm(html)
    assert 'id="data"' in out
    assert 'aria-label' in out
    assert 'role="cell"' in out
    assert "42" in out


# ==========================================
# Compactage whitespace + troncature
# ==========================================
def test_compacts_whitespace():
    """Les espaces en fin de ligne et series de newlines sont compactés."""
    html = '<div>a</div>   \n\n\n\n   <div>b</div>'
    out = clean_dom_for_llm(html)
    assert "   \n" not in out  # pas d'espaces trailing avant newline
    assert "\n\n\n" not in out  # pas de 3+ newlines consécutives


def test_truncates_to_max_chars():
    """Filet de sécurité : un div géant est tronqué après nettoyage."""
    huge = "<div>" + ("x" * 20000) + "</div>"
    out = clean_dom_for_llm(huge, max_chars=500)
    assert len(out) <= 600  # max_chars + marqueur de troncature
    assert "[tronqué par dom_filter]" in out


def test_default_max_chars_8000():
    """Le défaut (8000) est cohérent avec les autres budgets du projet."""
    huge = "<div>" + ("y" * 20000) + "</div>"
    out = clean_dom_for_llm(huge)
    assert "[tronqué par dom_filter]" in out
    assert len(out) <= 8100


# ==========================================
# Cas limites
# ==========================================
def test_none_returns_empty():
    assert clean_dom_for_llm(None) == ""


def test_empty_string_returns_empty():
    assert clean_dom_for_llm("") == ""


def test_already_clean_html_unchanged_semantically():
    """Un HTML sans balises bruyantes garde tout son contenu sémantique."""
    html = '<div id="a"><p class="b">texte</p></div>'
    out = clean_dom_for_llm(html)
    assert 'id="a"' in out
    assert "texte" in out


# ==========================================
# Gain effectif (ratio de réduction sur un HTML réaliste)
# ==========================================
def test_significant_token_reduction_on_realistic_page():
    """Un HTML réaliste (script+style+svg volumineux) est réduit drastiquement.

    Justification ROI du plan : 'économise massivement les tokens sur le Web Tester'.
    On vérifie que le nettoyage divise la taille par au moins ~3 sur un cas réaliste.
    """
    # Page type : 80% de bruit (JS+CSS+SVG), 20% de sémantique.
    html = (
        '<!DOCTYPE html><html><head>'
        f'<style>{"body{color:red}" * 500}</style>'
        '<script>function f(){ return ' + "1+" * 500 + '1; }</script>'
        '</head><body>'
        '<svg viewBox="0 0 24 24"><path d="' + "M0 0 L1 1 " * 100 + '"/></svg>'
        '<div id="app"><h1>Titre</h1><ul id="items"><li>A</li><li>B</li></ul></div>'
        '</body></html>'
    )
    out = clean_dom_for_llm(html)
    # Le rapport sémantique/nettoyage doit être très favorable.
    assert len(out) < len(html) / 3
    # Le contenu utile est intact.
    assert "Titre" in out
    assert 'id="items"' in out
    assert "A" in out and "B" in out
