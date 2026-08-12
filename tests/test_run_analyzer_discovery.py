"""Tests unitaires de la découverte auto de log dans run_analyzer.py.

Valide que ``discover_latest_log`` trouve le log le plus récent dans ``logs/``
de façon cross-plateforme — correctif du chemin Windows hardcodé
(``.gemini/antigravity-cli/brain``) qui cassait le Meta-Analyst (F-61) sur
Linux/macOS.

Déterministes, 0 LLM, 0 parsing de vrai log.
"""
import os
import sys
import time


# scripts/ n'est pas un package importable par défaut (pas de __init__.py) :
# on ajoute le répertoire racine du projet au path pour importer run_analyzer.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.run_analyzer import discover_latest_log  # noqa: E402


# ==========================================
# discover_latest_log
# ==========================================
def test_discover_returns_none_when_dir_empty(tmp_path):
    """Répertoire vide → None (pas d'erreur)."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    assert discover_latest_log(logs_dir) is None


def test_discover_returns_none_when_no_matching_files(tmp_path):
    """Fichiers présents mais ne matchant pas run-*.log → None."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    # Fichiers avec d'autres noms (ne matchent pas le pattern).
    (tmp_path / "logs" / "random.txt").write_text("x")
    (tmp_path / "logs" / "coder_1234.log").write_text("x")
    assert discover_latest_log(logs_dir) is None


def test_discover_returns_none_when_dir_missing(tmp_path):
    """Répertoire inexistant → None (glob ne lève pas, retourne [])."""
    logs_dir = str(tmp_path / "does_not_exist")
    assert discover_latest_log(logs_dir) is None


def test_discover_finds_single_log(tmp_path):
    """Un seul log run-*.log → retourné."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    log_path = os.path.join(logs_dir, "run-20260803-120000-coding.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("[*] Coder step 1")
    result = discover_latest_log(logs_dir)
    assert result is not None
    assert os.path.normpath(result) == os.path.normpath(log_path)


def test_discover_picks_most_recent_by_mtime(tmp_path):
    """Plusieurs logs → le plus récent (par mtime) est sélectionné."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    # Ancien log (mtime plus ancien).
    old_log = os.path.join(logs_dir, "run-20260801-100000-coding.log")
    with open(old_log, "w", encoding="utf-8") as f:
        f.write("old")
    old_time = time.time() - 3600  # 1h plus tôt
    os.utime(old_log, (old_time, old_time))

    # Log récent.
    new_log = os.path.join(logs_dir, "run-20260803-160000-coding.log")
    with open(new_log, "w", encoding="utf-8") as f:
        f.write("new")
    # mtime = maintenant (plus récent que old_log).

    result = discover_latest_log(logs_dir)
    assert result is not None
    assert os.path.normpath(result) == os.path.normpath(new_log)


def test_discover_ignores_non_log_run_files(tmp_path):
    """Les fichiers run-* sans extension .log sont ignorés (ex: run-meta.txt)."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    (tmp_path / "logs" / "run-meta.txt").write_text("meta")
    log_path = os.path.join(logs_dir, "run-20260803-120000-coding.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("real log")
    result = discover_latest_log(logs_dir)
    assert result is not None
    assert os.path.normpath(result) == os.path.normpath(log_path)


def test_discover_cross_platform_path(tmp_path):
    """Le chemin retourné utilise os.path.join (séparateur natif, pas de / hardcodé)."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    log_path = os.path.join(logs_dir, "run-20260803-120000-one-shot.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("x")
    result = discover_latest_log(logs_dir)
    assert result is not None
    # Le résultat pointe bien vers le fichier existant (chemin valide sur cet OS).
    assert os.path.exists(result)


def test_discover_handles_multiple_modes(tmp_path):
    """Logs de modes différents (one-shot/coding/exploration) → le plus récent gagne."""
    logs_dir = str(tmp_path / "logs")
    os.makedirs(logs_dir)
    modes = ["one-shot", "coding", "exploration"]
    paths = []
    base_time = time.time() - 100
    for i, mode in enumerate(modes):
        p = os.path.join(logs_dir, f"run-2026080{i + 1}-100000-{mode}.log")
        with open(p, "w", encoding="utf-8") as f:
            f.write(mode)
        t = base_time + i * 10  # chacun plus récent que le précédent
        os.utime(p, (t, t))
        paths.append(p)
    result = discover_latest_log(logs_dir)
    # Le dernier créé (exploration) a le mtime le plus élevé.
    assert os.path.normpath(result) == os.path.normpath(paths[-1])
