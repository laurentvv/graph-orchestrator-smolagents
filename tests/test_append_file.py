"""Tests unitaires de l'outil append_file (découpage incrémental, F-XX).

Pas de LLM, déterministes. Couvre le contrat complet :
- Création from scratch + append sur existant.
- Gardes anti-placeholder / anti-contenu-vide (fichier non modifié).
- Anti-doublon léger (content == fin du fichier → signalé, non réécrit).
- Feedback taille/lignes.
- Sous-dossiers créés automatiquement.
- Mutex (2 appends concurrents ne se corrompent pas).
"""
import threading

from graph_orchestrator.tools import append_file


def test_append_creates_file_if_missing(tmp_path):
    """append_file sur un fichier inexistant le crée (mode 'a')."""
    f = tmp_path / "new.txt"
    res = append_file(str(f), "première ligne\n")

    assert f.exists()
    assert f.read_text(encoding="utf-8") == "première ligne\n"
    assert "Appended" in res


def test_append_preserves_existing_content(tmp_path):
    """append_file ajoute à la fin SANS écraser le contenu existant."""
    f = tmp_path / "cumul.txt"
    f.write_text("BASE\n", encoding="utf-8")

    append_file(str(f), "section A\n")
    append_file(str(f), "section B\n")

    content = f.read_text(encoding="utf-8")
    assert content == "BASE\nsection A\nsection B\n"


def test_append_rejects_empty_content(tmp_path):
    """content vide → rejeté, fichier non modifié."""
    f = tmp_path / "empty.txt"
    f.write_text("GARDE\n", encoding="utf-8")
    size_before = f.stat().st_size

    res = append_file(str(f), "")

    assert "ERROR" in res
    assert "EMPTY" in res
    assert f.stat().st_size == size_before  # fichier intact
    assert f.read_text(encoding="utf-8") == "GARDE\n"


def test_append_rejects_placeholder(tmp_path):
    """content placeholder (TODO, ...) → rejeté, fichier non modifié."""
    f = tmp_path / "ph.txt"
    f.write_text("base\n", encoding="utf-8")

    res = append_file(str(f), "TODO")

    assert "ERROR" in res
    assert "placeholder" in res.lower()
    assert f.read_text(encoding="utf-8") == "base\n"  # rien ajouté


def test_append_duplicate_guard(tmp_path):
    """Si content == fin exacte du fichier, on le signale SANS réécrire."""
    f = tmp_path / "dup.txt"
    f.write_text("debut\nfin\n", encoding="utf-8")

    res = append_file(str(f), "fin\n")

    assert "NOTICE" in res
    assert "duplicate" in res.lower() or "already" in res.lower()
    # Le fichier n'a pas changé (pas de "fin\n" en double).
    assert f.read_text(encoding="utf-8") == "debut\nfin\n"


def test_append_creates_parent_dirs(tmp_path):
    """Le dossier parent est créé automatiquement (cohérent avec write_file)."""
    f = tmp_path / "sous" / "dossier" / "profond.txt"
    assert not f.parent.exists()

    res = append_file(str(f), "contenu\n")

    assert f.exists()
    assert f.read_text(encoding="utf-8") == "contenu\n"
    assert "Appended" in res


def test_append_feedback_reports_size_and_lines(tmp_path):
    """Le feedback contient la nouvelle taille (chars) ET le nombre de lignes."""
    f = tmp_path / "metrics.txt"
    f.write_text("ligne1\nligne2\n", encoding="utf-8")

    res = append_file(str(f), "ligne3\n")

    assert "Appended" in res
    assert "chars" in res
    assert "lines" in res
    # 3 lignes attendues après l'append.
    assert "3 lines" in res


def test_append_concurrent_does_not_corrupt(tmp_path):
    """2 appends concurrents sur le même fichier : pas de corruption (mutex).

    Le mutex par fichier (openfox pattern) sérialise les écritures. Sans lui, le
    2e append pourrait lire/écrire en plein milieu du 1er → perte de données.
    """
    f = tmp_path / "conc.txt"
    f.write_text("", encoding="utf-8")

    def append_chunk(marker: str):
        for i in range(20):
            append_file(str(f), f"{marker}-{i}\n")

    t1 = threading.Thread(target=append_chunk, args=("A",))
    t2 = threading.Thread(target=append_chunk, args=("B",))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    content = f.read_text(encoding="utf-8")
    lines = content.splitlines()
    # 40 lignes au total (20 A + 20 B), aucune perdue par race condition.
    assert len(lines) == 40
    assert sum(1 for line in lines if line.startswith("A-")) == 20
    assert sum(1 for line in lines if line.startswith("B-")) == 20
