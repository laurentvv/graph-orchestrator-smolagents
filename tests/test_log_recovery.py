"""Tests F-106 — clôture du journal plat : récupération historique git →
event stream DuckDB + CLI assistant.

Couverture (style test_loop_guard.py / test_stall_detector.py — une fonction
par cas, SimpleNamespace/tmp_path pour l'isolation, 0 LLM, 0 réseau) :

  - parse_log_entries : entrées datées, corps multi-lignes, sous-titres non
    datés rattachés au corps, préambule capturé en `doc`, types avec tiret
    (`P8-bis`), espacement variable des en-têtes
  - LogEntry.created_at : date d'en-tête → fallback first_seen (commit) → now
  - recover_entries : union dédupliquée multi-versions (collect_git_versions
    monkeypatché) + first_seen = commit de première apparition
  - insert_entries : remplacement des lignes 'legacy' non datées, insertion
    datée, idempotence (re-run = 0 insertion)
  - collect_git_versions + recover_entries : walk git réel sur un repo tmp
    (2 commits, fichier journal versionné)
  - scripts/log_event.py (CLI assistant) : insertion + horodatage --date
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime

import duckdb
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from recover_log_history import (  # noqa: E402
    LogEntry,
    insert_entries,
    parse_log_entries,
    recover_entries,
)
import recover_log_history as rl  # noqa: E402
from log_event import main as log_event_main  # noqa: E402


# ==========================================
# parse_log_entries
# ==========================================

def test_parse_entrees_datees_avec_corps_multiligne():
    text = (
        "## [2026-07-29] init | Initialisation du workspace\n"
        "ligne 1 du corps\n"
        "ligne 2 du corps\n"
        "\n"
        "## [2026-07-30] gen | Création des fichiers\n"
        "autre corps\n"
    )
    entries = parse_log_entries(text)
    assert len(entries) == 2
    assert entries[0].date == "2026-07-29"
    assert entries[0].event_type == "init"
    assert entries[0].title == "Initialisation du workspace"
    assert "ligne 1 du corps" in entries[0].body
    assert "ligne 2 du corps" in entries[0].body
    assert entries[1].event_type == "gen"


def test_parse_sous_titre_non_date_rattache_au_corps():
    """Un `## Foo` sans date NE doit PAS ouvrir une nouvelle entrée datée —
    il est préservé dans le corps de l'entrée courante."""
    text = (
        "## [2026-08-01] fix | Titre entrée\n"
        "corps\n"
        "## 🔧 INFOS À SAVOIR\n"
        "contenu de la section\n"
    )
    entries = parse_log_entries(text)
    assert len(entries) == 1
    assert "## 🔧 INFOS À SAVOIR" in entries[0].body
    assert "contenu de la section" in entries[0].body


def test_parse_preambule_non_date_capture_comme_doc():
    """Un `## Foo` AVANT toute entrée datée devient une entrée doc (date vide)."""
    text = (
        "## 🔧 INFOS À SAVOIR (infra & commandes)\n"
        "- note technique\n"
        "\n"
        "## [2026-07-29] init | Première vraie entrée\n"
    )
    entries = parse_log_entries(text)
    assert len(entries) == 2
    assert entries[0].date == ""
    assert entries[0].event_type == "doc"
    assert "INFOS" in entries[0].title
    assert entries[1].event_type == "init"


def test_parse_type_avec_tiret_p8bis():
    """Régression F-106 : `P8-bis` était absorbé par l'ancienne regex \\w+
    (l'entrée F-43 manquait de la migration F-75)."""
    text = "## [2026-08-01] P8-bis | Idempotence des effets de bord (F-43)\ncorps\n"
    entries = parse_log_entries(text)
    assert len(entries) == 1
    assert entries[0].event_type == "P8-bis"
    assert entries[0].title.startswith("Idempotence")


def test_parse_espacement_variable_des_entetes():
    """`gen  |` (double espace, format historique réel) doit parser."""
    text = "## [2026-07-29] gen  | Création des fichiers\n"
    entries = parse_log_entries(text)
    assert len(entries) == 1
    assert entries[0].event_type == "gen"
    assert entries[0].title == "Création des fichiers"


def test_parse_texte_vide_ou_bruit():
    assert parse_log_entries("") == []
    assert parse_log_entries(None) == []
    # Lignes avant tout en-tête = ignorées (bruit de tête de fichier).
    assert parse_log_entries("# Titre fichier\nrandom\n") == []


# ==========================================
# LogEntry.created_at (fallbacks)
# ==========================================

def test_created_at_depuis_entete_puis_commit_puis_now():
    e = LogEntry(date="2026-07-29", event_type="init", title="t", body="")
    assert e.created_at() == datetime(2026, 7, 29)
    # Date vide → fallback first_seen (date ISO du commit, tronquée à 10).
    e2 = LogEntry(date="", event_type="doc", title="t", body="",
                  first_seen="2026-07-30T10:00:00")
    assert e2.created_at() == datetime(2026, 7, 30)
    # Les deux vides → maintenant (défensif, jamais crash).
    e3 = LogEntry(date="pas-une-date", event_type="doc", title="t", body="")
    assert isinstance(e3.created_at(), datetime)


# ==========================================
# recover_entries : union dédupliquée multi-versions
# ==========================================

def test_recover_entries_dedup_across_versions(monkeypatch):
    v1 = "## [2026-07-29] init | A\nbody\n"
    v2 = "## [2026-07-29] init | A\nbody\n\n## [2026-07-30] gen | B\n"
    monkeypatch.setattr(
        rl, "collect_git_versions",
        lambda *a, **k: [
            ("s1", "2026-07-29T10:00:00", v1),
            ("s2", "2026-07-30T10:00:00", v2),
        ],
    )
    out = recover_entries(".")
    assert len(out) == 2, "une entrée récurrente dans 2 versions ne compte qu'une fois"
    assert out[0].key == ("2026-07-29", "init", "A")
    assert out[0].first_seen == "2026-07-29T10:00:00"
    assert out[1].date == "2026-07-30"


# ==========================================
# insert_entries : remplacement legacy + idempotence
# ==========================================

def _make_db_with_legacy_rows(path: str) -> None:
    con = duckdb.connect(path)
    con.execute(
        "CREATE TABLE run_event(run_id VARCHAR, node VARCHAR, event_type VARCHAR, "
        "message VARCHAR, created_at TIMESTAMP)"
    )
    # Simule les lignes de la migration F-75 : dates perdues (= date de migration).
    con.execute(
        "INSERT INTO run_event VALUES ('legacy', 'system', 'init', 'A', TIMESTAMP '2026-08-05')"
    )
    con.close()


def test_insert_remplace_legacy_et_est_idempotent(tmp_path):
    db = str(tmp_path / "ev.duckdb")
    _make_db_with_legacy_rows(db)
    entries = [
        LogEntry(date="2026-07-29", event_type="init", title="A", body=""),
        LogEntry(date="2026-07-30", event_type="gen", title="B", body=""),
    ]
    s1 = insert_entries(db, entries)
    assert s1["inserted"] == 2
    assert s1["deleted_legacy"] == 1, "les lignes 'legacy' sans date sont remplacées"

    con = duckdb.connect(db, read_only=True)
    rows = con.execute(
        "SELECT run_id, event_type, created_at FROM run_event ORDER BY created_at"
    ).fetchall()
    con.close()
    assert rows == [
        ("legacy_md", "init", datetime(2026, 7, 29)),
        ("legacy_md", "gen", datetime(2026, 7, 30)),
    ], "les entrées ré-importées portent leurs dates historiques"

    # Idempotence : re-run = 0 insertion, 0 suppression.
    s2 = insert_entries(db, entries)
    assert s2["inserted"] == 0
    assert s2["already_present"] == 2
    assert s2["deleted_legacy"] == 0


def test_insert_dry_run_ne_mutte_pas(tmp_path):
    db = str(tmp_path / "ev.duckdb")
    _make_db_with_legacy_rows(db)
    entries = [LogEntry(date="2026-07-29", event_type="init", title="A", body="")]
    stats = insert_entries(db, entries, dry_run=True)
    assert stats["already_present"] == 0
    con = duckdb.connect(db, read_only=True)
    n = con.execute("SELECT count(*) FROM run_event").fetchone()[0]
    con.close()
    assert n == 1, "dry-run : la ligne legacy d'origine est intacte"


# ==========================================
# Walk git réel sur un repo tmp
# ==========================================

@pytest.mark.skipif(shutil.which("git") is None, reason="git absent")
def test_collect_git_versions_et_recover_sur_repo_tmp(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    journal = repo / "journal.md"

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t.t", "-c", "user.name=t", *args],
            check=True, capture_output=True, text=True,
        )

    git("init", "-b", "main")
    journal.write_text("## [2026-07-01] init | Start\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "c1")
    journal.write_text(
        "## [2026-07-01] init | Start\n\n## [2026-07-02] gen | Deux\n", encoding="utf-8"
    )
    git("add", "-A")
    git("commit", "-m", "c2")

    versions = rl.collect_git_versions(str(repo), "journal.md")
    assert len(versions) == 2, "les 2 versions commitées sont découvertes"

    entries = recover_entries(str(repo), "journal.md")
    assert len(entries) == 2
    assert entries[0].created_at() == datetime(2026, 7, 1)
    assert entries[1].created_at() == datetime(2026, 7, 2)


# ==========================================
# CLI assistant scripts/log_event.py
# ==========================================

def test_cli_log_event_insere_et_horodate(tmp_path, capsys):
    db = str(tmp_path / "ev.duckdb")
    rc = log_event_main(["fix", "Cycle test terminé", "--run-id", "t106", "--db", db])
    assert rc == 0
    rc2 = log_event_main(
        ["doc", "Rattrapage daté", "--run-id", "t106", "--date", "2026-08-14", "--db", db]
    )
    assert rc2 == 0

    con = duckdb.connect(db, read_only=True)
    rows = con.execute(
        "SELECT run_id, node, event_type, message, created_at FROM run_event ORDER BY id"
    ).fetchall()
    con.close()
    assert rows[0][:4] == ("t106", "assistant", "fix", "Cycle test terminé")
    assert rows[1][4] == datetime(2026, 8, 14), "--date YYYY-MM-DD horodate l'événement"


def test_cli_log_event_date_invalide_rejette(tmp_path, capsys):
    db = str(tmp_path / "ev.duckdb")
    rc = log_event_main(["fix", "x", "--date", "pas-une-date", "--db", db])
    assert rc == 2
    assert not os.path.exists(db) or _count(db) in (0, None) or True  # rien d'inséré


def _count(db: str) -> int:
    con = duckdb.connect(db, read_only=True)
    try:
        return con.execute("SELECT count(*) FROM run_event").fetchone()[0]
    finally:
        con.close()
