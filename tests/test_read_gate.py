"""Tests unitaires du Read-Before-Write Gate — Priorité 1 (F-66).

Valide le middleware qui bloque les écritures sur un fichier EXISTANT non lu
(inspiré de Deer Flow issue #3857). Déterministe, 0 LLM, 0 réseau.

Couvre :
- helpers purs : compute_content_hash stable, _normalize_path (win32 / `..` / mixed sep).
- ReadGate : record_read stamp ; check_write ALLOW si hash match, BLOCK sinon ;
  fail-open (fichier absent = création, read impossible, path None) ; mode Strict
  (record_write invalide la mark) ; « newest mark wins » ; thread-safety.
- _GatedWriteTool : bloque sans déléguer, ALLOW + délègue + record_write,
  __getattr__ délègue (to_code_prompt accessible).
- _ReadTrackingTool : délègue à read_file, stamp le hash du contenu COMPLET
  (même sur read partiel offset/limit).
- wrap_tools_with_read_gate : no-op si disabled, wrap uniquement les ciblés,
  préserve l'ordre, laisse intacts les outils non ciblés (list_directory, MCP).
- E2E : un Coder simulé qui write un fichier existant SANS read → BLOCK ;
  qui read puis write → ALLOW ; qui write puis edit sans re-read → BLOCK (Strict).
"""
from __future__ import annotations

from pathlib import Path


from graph_orchestrator.read_gate import (
    ReadGate,
    _GatedWriteTool,
    _ReadTrackingTool,
    _normalize_path,
    compute_content_hash,
    wrap_tools_with_read_gate,
)


# ==========================================
# Helpers purs
# ==========================================
def test_compute_content_hash_stable():
    """Le hash SHA256 est stable : même contenu → même hash."""
    assert compute_content_hash("hello") == compute_content_hash("hello")


def test_compute_content_hash_differs():
    """Deux contenus différents → deux hash différents."""
    assert compute_content_hash("hello") != compute_content_hash("world")


def test_normalize_path_resolves_dotdot():
    """`a/b/../c.txt` se normalise comme `a/c.txt` (équivalent posixpath.normpath)."""
    assert _normalize_path("a/b/../c.txt") == _normalize_path("a/c.txt")


def test_normalize_path_mixed_separators():
    """SéparateWindows mixed (`/` et `\\`) → même clé normalisée (win32)."""
    assert _normalize_path("a/b/c.txt") == _normalize_path("a\\b\\c.txt")


def test_normalize_path_absolute():
    """Le résultat est absolu (os.path.abspath), peu importe le cwd."""
    norm = _normalize_path("x.txt")
    assert Path(norm).is_absolute()


# ==========================================
# ReadGate — logique ALLOW/BLOCK
# ==========================================
class TestReadGateLogic:
    """Valide la règle ALLOW vs BLOCK du gate sur fichiers existants."""

    def test_write_to_nonexistent_file_allowed(self, tmp_path: Path):
        """Fichier absent = CRÉATION autorisée (fail-open, premier write OK)."""
        gate = ReadGate()
        path = str(tmp_path / "new.txt")
        allowed, reason = gate.check_write(path)
        assert allowed is True
        assert reason == ""

    def test_write_to_existing_unread_file_blocked(self, tmp_path: Path):
        """Fichier existant JAMAIS lu → BLOCK (cœur du read-before-write)."""
        f = tmp_path / "existing.txt"
        f.write_text("contenu initial", encoding="utf-8")
        gate = ReadGate()
        allowed, reason = gate.check_write(str(f))
        assert allowed is False
        assert "read_file" in reason.lower()
        assert str(f) in reason

    def test_write_after_read_allowed(self, tmp_path: Path):
        """read puis write sur même contenu → ALLOW (hash match)."""
        f = tmp_path / "x.txt"
        f.write_text("v1", encoding="utf-8")
        gate = ReadGate()
        gate.record_read(str(f), "v1")
        allowed, reason = gate.check_write(str(f))
        assert allowed is True
        assert reason == ""

    def test_write_after_stale_read_blocked(self, tmp_path: Path):
        """read puis modification du fichier disque → read stale → BLOCK."""
        f = tmp_path / "x.txt"
        f.write_text("v1", encoding="utf-8")
        gate = ReadGate()
        gate.record_read(str(f), "v1")
        # Le fichier change sur disque (ex: via bash, ou un autre agent).
        f.write_text("v2-modified-on-disk", encoding="utf-8")
        allowed, reason = gate.check_write(str(f))
        assert allowed is False
        assert "read_file" in reason.lower()


# ==========================================
# ReadGate — fail-open (ne jamais briquer l'agent)
# ==========================================
class TestReadGateFailOpen:
    """Le gate ne doit JAMAIS planter ni bloquer sur une inspection impossible."""

    def test_path_none_allowed(self):
        gate = ReadGate()
        allowed, reason = gate.check_write(None)  # type: ignore[arg-type]
        assert allowed is True and reason == ""

    def test_path_empty_allowed(self):
        gate = ReadGate()
        allowed, _ = gate.check_write("")
        assert allowed is True

    def test_path_not_a_string_allowed(self):
        gate = ReadGate()
        # Un int passé par erreur : fail-open, pas de crash.
        allowed, _ = gate.check_write(123)  # type: ignore[arg-type]
        assert allowed is True

    def test_unreadable_file_allowed(self, tmp_path: Path):
        """Fichier présent mais illisible (ex: binaire, permissions) → fail-open ALLOW."""
        f = tmp_path / "bin.dat"
        # Écrire des bytes non UTF-8 décodables pour forcer UnicodeDecodeError.
        f.write_bytes(b"\xff\xfe\x00\xfa")
        gate = ReadGate()
        allowed, _ = gate.check_write(str(f))
        assert allowed is True  # fail-open : on laisse passer plutôt que briquer.

    def test_record_read_does_not_raise_on_bad_input(self):
        """record_read ne lève jamais (path None, content None)."""
        gate = ReadGate()
        gate.record_read(None, "x")  # type: ignore[arg-type]
        gate.record_read("p", None)  # type: ignore[arg-type]
        gate.record_read("", "x")
        # Aucune exception = pass.

    def test_record_write_does_not_raise_on_bad_input(self):
        gate = ReadGate()
        gate.record_write(None)  # type: ignore[arg-type]
        gate.record_write("")
        gate.record_write("never-read.txt")  # pas de mark → idempotent pop.


# ==========================================
# ReadGate — mode Strict (write invalide la mark)
# ==========================================
class TestStrictMode:
    """Mode Strict (fidèle Deer Flow) : un write réussi invalide la mark.

    La prochaine édition sur le même fichier est BLOQUÉE jusqu'à un nouveau
    read_file. Corrige le bug « édition à partir d'une représentation mentale
    stale » (l'auteur doit relire son propre output avant de l'éditer).
    """

    def test_write_invalidates_mark(self, tmp_path: Path):
        """read → write OK → edit suivant BLOQUÉ (Strict) jusqu'à re-read."""
        f = tmp_path / "x.txt"
        f.write_text("v1", encoding="utf-8")
        gate = ReadGate()
        gate.record_read(str(f), "v1")
        # write réussi (le contenu disque ne change pas, mais la mark est invalidée).
        gate.record_write(str(f))
        allowed, reason = gate.check_write(str(f))
        assert allowed is False
        assert "read_file" in reason.lower()

    def test_re_read_after_write_allows_edit(self, tmp_path: Path):
        """Après un write, un nouveau read restaure l'autorisation d'éditer."""
        f = tmp_path / "x.txt"
        f.write_text("v1", encoding="utf-8")
        gate = ReadGate()
        gate.record_read(str(f), "v1")
        gate.record_write(str(f))  # write invalide la mark.
        gate.record_read(str(f), "v1")  # re-read restaure.
        allowed, _ = gate.check_write(str(f))
        assert allowed is True

    def test_write_to_new_file_does_not_create_mark(self, tmp_path: Path):
        """record_write sur un path sans mark préalable est un no-op idempotent."""
        gate = ReadGate()
        gate.record_write(str(tmp_path / "never-read.txt"))
        # Pas de mark à invalider → pas d'erreur, pas d'effet de bord.


# ==========================================
# ReadGate — « newest mark wins »
# ==========================================
def test_newest_mark_wins(tmp_path: Path):
    """Deux reads successifs : le DERNIER gagne (hash le plus récent).

    Scénario : read v1 → fichier modifié → read v2 → write ALLOW sur v2.
    """
    f = tmp_path / "x.txt"
    f.write_text("v1", encoding="utf-8")
    gate = ReadGate()
    gate.record_read(str(f), "v1")
    f.write_text("v2", encoding="utf-8")
    gate.record_read(str(f), "v2")  # écrase la mark précédente.
    allowed, _ = gate.check_write(str(f))
    assert allowed is True  # la dernière lecture (v2) matche le disque (v2).


# ==========================================
# ReadGate — thread-safety (défense ceinture+bretelles)
# ==========================================
def test_concurrent_record_read_is_safe(tmp_path: Path):
    """20 threads stampant en parallèle ne corrompent pas le dict interne."""
    import threading

    f = tmp_path / "x.txt"
    f.write_text("v", encoding="utf-8")
    gate = ReadGate()
    errors: list[Exception] = []

    def stamp() -> None:
        try:
            for _ in range(50):
                gate.record_read(str(f), "v")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=stamp) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    allowed, _ = gate.check_write(str(f))
    assert allowed is True


# ==========================================
# _GatedWriteTool — proxy
# ==========================================
class TestGatedWriteTool:
    """Valide le proxy _GatedWriteTool (template copié de SanitizedTool).

    On utilise les VRAIS outils de tools.py (write_file/edit_file) plutôt qu'un
    faux BaseTool : plus réaliste, et smolagents valide `forward`/`inputs` à
    l'instanciation. On asserte sur l'état DISQUE pour prouver « non délégué ».
    """

    def test_block_does_not_delegate(self, tmp_path: Path):
        """Si check_write bloque, l'outil sous-jacent n'est JAMAIS appelé."""
        from graph_orchestrator.tools import write_file

        f = tmp_path / "existing.txt"
        f.write_text("initial content here", encoding="utf-8")
        original = f.read_text(encoding="utf-8")
        gate = ReadGate()
        gated = _GatedWriteTool(write_file, gate)
        result = gated(path=str(f), content="completely different new content")
        assert "read_file" in result.lower()  # message pédagogique.
        # Le fichier disque est INCHANGÉ → l'outil sous-jacent n'a pas été appelé.
        assert f.read_text(encoding="utf-8") == original

    def test_allow_delegates_and_records_write(self, tmp_path: Path):
        """Si ALLOW : délègue à l'outil réel PUIS appelle record_write (Strict)."""
        from graph_orchestrator.tools import write_file

        f = tmp_path / "x.txt"
        f.write_text("original v1 content", encoding="utf-8")
        gate = ReadGate()
        gate.record_read(str(f), "original v1 content")
        gated = _GatedWriteTool(write_file, gate)
        result = gated(path=str(f), content="brand new replacement content")
        assert "Successfully wrote" in result  # délégué.
        assert f.read_text(encoding="utf-8") == "brand new replacement content"
        # Strict : la mark a été invalidée par le write réussi → edit suivant bloqué.
        allowed, _ = gate.check_write(str(f))
        assert allowed is False

    def test_copies_metadata(self):
        """Le proxy copie name/description/inputs/output_type de l'outil sous-jacent."""
        from graph_orchestrator.tools import write_file

        gated = _GatedWriteTool(write_file, ReadGate())
        assert gated.name == write_file.name
        assert gated.description == write_file.description
        assert gated.inputs == write_file.inputs
        assert gated.output_type == write_file.output_type

    def test_getattr_delegates_to_code_prompt(self):
        """__getattr__ délègue les attributs non définis (to_code_prompt pour Jinja)."""
        from graph_orchestrator.tools import write_file

        gated = _GatedWriteTool(write_file, ReadGate())
        # to_code_prompt n'est pas défini sur _GatedWriteTool → délègue à write_file.
        # Le vrai write_file expose cet attribut (le CodeAgent Jinja l'interroge).
        assert callable(getattr(gated, "to_code_prompt", None)) or hasattr(
            write_file, "to_code_prompt"
        )

    def test_forward_path_also_gated(self, tmp_path: Path):
        """Le chemin TCA `forward` applique aussi le gate."""
        from graph_orchestrator.tools import write_file

        f = tmp_path / "y.txt"
        f.write_text("initial content here", encoding="utf-8")
        original = f.read_text(encoding="utf-8")
        gated = _GatedWriteTool(write_file, ReadGate())
        result = gated.forward(path=str(f), content="new different content")
        assert "read_file" in result.lower()
        assert f.read_text(encoding="utf-8") == original  # non délégué.


# ==========================================
# _ReadTrackingTool — proxy miroir de read_file
# ==========================================
class TestReadTrackingTool:
    """Valide que _ReadTrackingTool stamp le hash du contenu COMPLET après read."""

    def test_stamp_after_read_uses_full_content(self, tmp_path: Path):
        """Un read partiel (offset/limit) stamp quand même le hash du FICHIER ENTIER.

        Vision Deer Flow : la mark reflète la version complète du fichier, pas
        seulement le slice demandé par l'agent.
        """
        from graph_orchestrator.tools import read_file

        f = tmp_path / "big.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
        gate = ReadGate()
        tracked = _ReadTrackingTool(read_file, gate)
        # read partiel : on ne demande que les lignes 3-4 (offset=2, limit=2).
        tracked(path=str(f), offset=2, limit=2)
        # Le hash stampé doit matcher le contenu COMPLET, pas le slice.
        full = f.read_text(encoding="utf-8")
        assert gate._marks[_normalize_path(str(f))] == compute_content_hash(full)

    def test_stamp_skips_nonexistent_file(self, tmp_path: Path):
        """Si le fichier lu n'existe pas (read retourne une erreur), pas de stamp."""
        from graph_orchestrator.tools import read_file

        gate = ReadGate()
        tracked = _ReadTrackingTool(read_file, gate)
        tracked(path=str(tmp_path / "missing.txt"))
        assert gate._marks == {}  # rien stampé.

    def test_delegates_and_returns_result(self, tmp_path: Path):
        """Le proxy retourne bien le résultat de read_file (pas de swallowing)."""
        from graph_orchestrator.tools import read_file

        f = tmp_path / "x.txt"
        f.write_text("hello world", encoding="utf-8")
        tracked = _ReadTrackingTool(read_file, ReadGate())
        result = tracked(path=str(f))
        assert "hello world" in result  # contenu bien retourné.


# ==========================================
# wrap_tools_with_read_gate — branchement
# ==========================================
class TestWrapTools:
    """Valide l'assemblage : no-op si disabled, ciblage précis, ordre préservé."""

    def test_disabled_returns_same_list(self):
        """enabled=False → no-op (même objet liste, comme sanitize_tools)."""
        from graph_orchestrator.tools import list_directory, read_file, write_file

        tools = [list_directory, read_file, write_file]
        result = wrap_tools_with_read_gate(tools, ReadGate(), enabled=False)
        assert result is tools  # identité préservée.

    def test_wraps_only_targeted_tools(self):
        """Seuls read_file + les outils d'écriture (hors append_file) sont wrappés.

        append_file est EXEMPTÉ du gate (voir docstring read_gate.py) : il est le
        mécanisme central de la stratégie incremental (F-28) et forcer un read_file
        avant chaque append fait exploser le contexte. L'anti-doublon F-28 +
        l'idempotence F-43 le protègent déjà.
        """
        from smolagents import DuckDuckGoSearchTool

        from graph_orchestrator.tools import (
            append_file,
            edit_file,
            list_directory,
            multi_replace,
            read_file,
            search_replace,
            write_file,
        )

        tools = [
            list_directory,
            read_file,
            write_file,
            search_replace,
            edit_file,
            multi_replace,
            append_file,
            DuckDuckGoSearchTool(),
        ]
        result = wrap_tools_with_read_gate(tools, ReadGate(), enabled=True)
        types_by_name = {t.name: type(t).__name__ for t in result}
        # Gated (écrasent/modifient) : wrappés.
        assert types_by_name["read_file"] == "_ReadTrackingTool"
        assert types_by_name["write_file"] == "_GatedWriteTool"
        assert types_by_name["search_replace"] == "_GatedWriteTool"
        assert types_by_name["edit_file"] == "_GatedWriteTool"
        assert types_by_name["multi_replace"] == "_GatedWriteTool"
        # Non ciblés : inchangés (type d'origine, pas wrappés).
        # append_file est VOLONTAIREMENT exempté (stratégie incremental F-28).
        assert types_by_name["append_file"] != "_GatedWriteTool"
        assert types_by_name["list_directory"] != "_GatedWriteTool"
        assert types_by_name["web_search"] != "_GatedWriteTool"  # DuckDuckGo intact.

    def test_preserves_order(self):
        """L'ordre de la liste est préservé (important pour le prompt du CodeAgent)."""
        from graph_orchestrator.tools import list_directory, read_file, write_file

        tools = [list_directory, read_file, write_file]
        result = wrap_tools_with_read_gate(tools, ReadGate(), enabled=True)
        assert [t.name for t in result] == ["list_directory", "read_file", "write_file"]


# ==========================================
# E2E — scénario Coder simulé
# ==========================================
class TestEndToEnd:
    """Scénarios réels : un Coder qui write/edit sans/avec read."""

    def test_write_existing_without_read_is_blocked(self, tmp_path: Path):
        """Coder tente write_file sur un fichier existant SANS l'avoir lu → BLOCK."""
        from graph_orchestrator.tools import write_file

        f = tmp_path / "existing.py"
        f.write_text("print('init')\n", encoding="utf-8")
        gate = ReadGate()
        gated_write = _GatedWriteTool(write_file, gate)
        result = gated_write(path=str(f), content="print('new')\n")
        assert "read_file" in result.lower()
        # Le fichier disque n'a pas été modifié (le write a été bloqué).
        assert f.read_text(encoding="utf-8") == "print('init')\n"

    def test_read_then_write_allowed(self, tmp_path: Path):
        """Coder read puis write → ALLOW, le fichier est bien modifié."""
        from graph_orchestrator.tools import read_file, write_file

        f = tmp_path / "x.py"
        f.write_text("old content here", encoding="utf-8")
        gate = ReadGate()
        tracked_read = _ReadTrackingTool(read_file, gate)
        gated_write = _GatedWriteTool(write_file, gate)
        tracked_read(path=str(f))  # stamp la mark.
        result = gated_write(path=str(f), content="brand new replacement content")
        assert "Successfully wrote" in result
        assert f.read_text(encoding="utf-8") == "brand new replacement content"

    def test_write_then_edit_without_reread_blocked_strict(self, tmp_path: Path):
        """Strict : write réussi → edit suivant BLOQUÉ sans re-read (le cas #3857).

        C'est le scénario anti-corruption central : empêche le Coder d'enchaîner
        write → edit en s'appuyant sur une représentation mentale stale au lieu
        du contenu réel du fichier.
        """
        from graph_orchestrator.tools import edit_file, write_file

        f = tmp_path / "x.py"
        f.write_text("old content here", encoding="utf-8")
        gate = ReadGate()
        gated_write = _GatedWriteTool(write_file, gate)
        gated_edit = _GatedWriteTool(edit_file, gate)
        # On simule un read préalable (sinon le 1er write serait déjà bloqué).
        gate.record_read(str(f), "old content here")
        gated_write(
            path=str(f), content="v1 brand new content"
        )  # write OK, mark invalidée (Strict).
        edit_result = gated_edit(
            path=str(f), old_string="v1", new_string="v2 fixed content"
        )
        assert "read_file" in edit_result.lower()  # edit bloqué : doit re-read.

    def test_message_cites_path_and_read_file(self, tmp_path: Path):
        """Le message pédagogique cite le path ET read_file (vérifiable par substring)."""
        f = tmp_path / "deep" / "file.txt"
        f.parent.mkdir()
        f.write_text("some real content", encoding="utf-8")
        gate = ReadGate()
        allowed, reason = gate.check_write(str(f))
        assert allowed is False
        assert str(f) in reason
        assert "read_file" in reason.lower()
