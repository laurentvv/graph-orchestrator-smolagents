# ==============================================================================
# Tests : skills_loader.load_skill_body_resolved (F-97 / MA-5)
# ==============================================================================
# Résolution de la progressive disclosure F-92 côté serveur : inline les
# resources/*.md dans le bloc injecté pour éviter que le Tester n'épuise son
# budget steps à les lire une à une. 0 LLM, 0 réseau.
# ==============================================================================

from graph_orchestrator import skills_loader
from graph_orchestrator.skills_loader import load_skill_body_resolved


# === Mécaniques (skills synthétiques sous un SKILLS_DIR tmp) ==================

def test_skill_sans_resources_retourne_le_corps_brut(monkeypatch, tmp_path):
    """Un skill non refactoré (pas de resources/) → identique à load_skill_body."""
    sk = tmp_path / "plain"
    sk.mkdir()
    (sk / "SKILL.md").write_text("---\nname: plain\n---\n# Plain\nFais ceci.", encoding="utf-8")
    monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(tmp_path))

    out = load_skill_body_resolved("plain")
    assert out == "# Plain\nFais ceci."
    assert "RESSOURCES" not in out


def test_skill_refactore_inline_les_resources(monkeypatch, tmp_path):
    """Skill refactoré F-92 : le contenu des resources/*.md est inliné."""
    sk = tmp_path / "refactored"
    sk.mkdir()
    (sk / "SKILL.md").write_text(
        "# Skill\nIntro.\n\n## Dynamic Resources (Progressive Disclosure)\n\n"
        "You MUST use your view_file tool.\n"
        "- [resources/a.md](file:///x): Read this.\n",
        encoding="utf-8",
    )
    res = sk / "resources"
    res.mkdir()
    (res / "a.md").write_text("Contenu A détaillé.", encoding="utf-8")
    (res / "b.md").write_text("Contenu B détaillé.", encoding="utf-8")
    monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(tmp_path))

    out = load_skill_body_resolved("refactored")
    # Le corps intro est conservé, la section pointeur est retirée, les resources inlinées.
    assert "# Skill" in out and "Intro." in out
    assert "Contenu A détaillé." in out
    assert "Contenu B détaillé." in out
    # L'instruction contradictoire view_file disparaît du bloc injecté.
    assert "view_file" not in out
    assert "## Dynamic Resources" not in out
    # La bannière anti-re-read est présente.
    assert "NE PAS" in out and "read_file" in out.upper().replace("READ_FILE", "read_file")


def test_inline_ordre_deterministe(monkeypatch, tmp_path):
    """Les resources sont inlinées dans un ordre stable (tri par nom de fichier)."""
    sk = tmp_path / "ordered"
    sk.mkdir()
    (sk / "SKILL.md").write_text("Intro\n## Dynamic Resources\nptrs", encoding="utf-8")
    res = sk / "resources"
    res.mkdir()
    (res / "zeta.md").write_text("Z", encoding="utf-8")
    (res / "alpha.md").write_text("A", encoding="utf-8")
    (res / "mid.md").write_text("M", encoding="utf-8")
    monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(tmp_path))

    out = load_skill_body_resolved("ordered")
    assert out.index("A") < out.index("M") < out.index("Z")


def test_skill_absent_retourne_vide(monkeypatch, tmp_path):
    monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(tmp_path))
    assert load_skill_body_resolved("nexiste-pas") == ""


def test_resources_dir_vide_retourne_corps_sans_pointeur(monkeypatch, tmp_path):
    """resources/ présent mais vide → on retire quand même le pointeur, aucun inline."""
    sk = tmp_path / "emptyres"
    sk.mkdir()
    (sk / "SKILL.md").write_text("Intro\n## Dynamic Resources\nptrs", encoding="utf-8")
    (sk / "resources").mkdir()
    monkeypatch.setattr(skills_loader, "SKILLS_DIR", str(tmp_path))

    out = load_skill_body_resolved("emptyres")
    assert out.strip() == "Intro"
    assert "Dynamic Resources" not in out


# === Intégration : la VRAIE skill web-tester (cas production MA-5) ============

def test_web_tester_skill_est_resolver_apres_f92():
    """La skill web-tester réelle (refactorée par F-92) doit être résolue :
    resources inlinées, section pointeur retirée, plus d'instruction view_file."""
    out = load_skill_body_resolved("web-tester")
    assert out, "Le corps résolu de web-tester ne doit pas être vide"
    # La section pointeur F-92 (avec view_file) doit avoir disparu du bloc.
    assert "## Dynamic Resources" not in out
    assert "view_file" not in out
    # Au moins un contenu de resource connu doit être inliné (workflow obligatoire).
    assert "RESSOURCES" in out  # bannière anti-re-read
    # Les 5 resources de web-tester présentes à l'audit (par titre reconstitué).
    lowered = out.lower()
    assert "mandatory testing workflow" in lowered or "mandatory_testing_workflow" in out.lower()


def test_web_tester_resolver_ninclut_pas_les_liens_file_des_resources():
    """Le bloc résolu ne doit plus exposer les liens file:///D:/... des resources
    comme cibles de lecture (le modèle ne doit plus les copier dans read_file)."""
    out = load_skill_body_resolved("web-tester")
    # La section pointeur (qui contenait les file:///...resources/*.md) est retirée.
    assert "file:///D:/GIT/graph-orchestrator-smolagents/skills/web-tester/resources/" not in out
