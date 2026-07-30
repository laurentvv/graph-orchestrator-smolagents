"""Tests unitaires de la troncature de feedback (feedback_utils).

Logique pure, déterministe, sans LLM. Couvre truncate_output (head+tail + marqueur)
et truncate_history (plafond cumulé + priorité aux items récents).
"""

from graph_orchestrator.feedback_utils import truncate_output, truncate_history


# ==========================================
# truncate_output — cas de base
# ==========================================

def test_short_text_returned_intact():
    """Un texte court (sous les seuils) revient à l'identique."""
    text = "ligne1\nligne2\nligne3\n"
    assert truncate_output(text, head_lines=20, tail_lines=20, max_chars=2000) == text


def test_empty_and_none_return_empty_string():
    """None / vide → chaîne vide, jamais None (pas de crash downstream)."""
    assert truncate_output(None) == ""
    assert truncate_output("") == ""


def test_text_within_line_budget_returned_intact():
    """Moins de head+tail lignes → intact même si max_chars large."""
    text = "\n".join(f"ligne {i}" for i in range(10))
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=10000)
    assert out == text


# ==========================================
# truncate_output — troncature effective
# ==========================================

def test_long_text_truncated_with_marker():
    """Un texte long est coupé et le marqueur de troncature est présent."""
    lines = [f"ligne {i}" for i in range(100)]
    text = "\n".join(lines)
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=100000)
    assert "tronquées" in out  # le marqueur est là
    assert "ligne 0" in out    # la tête est conservée
    assert "ligne 99" in out   # la queue est conservée


def test_head_and_tail_preserved():
    """Les head_lines premières et tail_lines dernières lignes sont présentes."""
    lines = [f"L{i}" for i in range(60)]
    text = "\n".join(lines)
    out = truncate_output(text, head_lines=10, tail_lines=10, max_chars=100000)
    # Tête
    for i in range(10):
        assert f"L{i}" in out
    # Queue
    for i in range(50, 60):
        assert f"L{i}" in out
    # Milieu coupé
    assert "L30" not in out


def test_middle_dropped_line_count_in_marker():
    """Le marqueur indique le bon nombre de lignes coupées."""
    lines = [f"L{i}" for i in range(100)]
    text = "\n".join(lines)
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=100000)
    # 100 - 20 - 20 = 60 lignes coupées
    assert "60" in out


def test_head_plus_tail_covers_all_no_truncation():
    """Si head+tail ≥ nombre total de lignes, pas de troncature par ligne."""
    text = "\n".join(f"L{i}" for i in range(15))
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=100000)
    assert "tronquées" not in out
    assert out == text


# ==========================================
# truncate_output — plafond caractères
# ==========================================

def test_long_single_line_capped_by_chars():
    """Une seule ligne très longue (ex. minified JS) est bornée par max_chars."""
    text = "x" * 5000  # une seule "ligne" géante
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=1000)
    assert len(out) <= 2000  # borne max_chars + marge marqueur
    assert "tronquées" in out


def test_huge_traceback_practical_case():
    """Cas réaliste : un traceback Python de 500 lignes devient compact."""
    # Simule un traceback : en-tête d'erreur + 490 lignes de stack + cause finale.
    head = ["Traceback (most recent call last):"]
    stack = [f'  File "mod{i}.py", line {i}, in func{i}' for i in range(490)]
    tail = ["AssertionError: expected 42, got 7"]
    text = "\n".join(head + stack + tail)
    out = truncate_output(text, head_lines=20, tail_lines=20, max_chars=2000)
    # Compact : bien plus court que l'original.
    assert len(out) < len(text) / 2
    # L'erreur (en tête) et la cause (en queue) sont conservées.
    assert "Traceback" in out
    assert "AssertionError" in out
    # Le milieu bruyant est coupé.
    assert "mod250" not in out


# ==========================================
# truncate_history
# ==========================================

def test_history_empty_returns_empty():
    """Liste vide → chaîne vide."""
    assert truncate_history([], max_chars=2000) == ""


def test_history_short_items_all_kept():
    """Quelques items courts → tous conservés, dans l'ordre."""
    items = ["bug1: typo", "bug2: missing import"]
    out = truncate_history(items, max_chars=2000)
    assert "bug1" in out
    assert "bug2" in out


def test_history_respects_char_cap():
    """L'historique tronqué ne dépasse jamais max_chars."""
    items = ["abcdefghijklmnopqrstuvwxyz" * 10 for _ in range(50)]
    out = truncate_history(items, max_chars=500, header="[BUGS]")
    assert len(out) <= 500


def test_history_prioritizes_recent_items():
    """Quand le plafond est atteint, les items les plus RÉCENTS sont prioritaires."""
    # items[i] = i (chronologique). Dernier = "récent".
    items = [f"bug-{i:03d}" + "x" * 80 for i in range(30)]
    out = truncate_history(items, max_chars=1000)
    # L'item le plus récent (bug-029) doit être présent.
    assert "bug-029" in out
    # Un vieux item (bug-000) doit être absent (pas assez de place).
    assert "bug-000" not in out


def test_history_skipped_count_reported():
    """Les items omis sont résumés par un compteur transparent."""
    items = ["z" * 100 for _ in range(50)]
    out = truncate_history(items, max_chars=500)
    assert "non affiché" in out  # le marqueur de comptage est présent


def test_history_header_included():
    """L'en-tête optionnel est repris en tête de la sortie."""
    out = truncate_history(["bug1"], max_chars=2000, header="[TICKETS]")
    assert out.startswith("[TICKETS]")
