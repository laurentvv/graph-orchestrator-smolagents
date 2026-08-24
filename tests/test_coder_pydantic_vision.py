"""Tests F-161 — vision multimodale du Coder pydantic (phase 3.6), 0 LLM / 0 réseau.

Couvre : split_tool_result (texte/images sans str(bytes) — régression garbage
F-160), make_image_tool_return (ON/OFF), process_tool_call multimodal via faux
call_tool, purge_history_images (parité F-101 : keep=1, archive perte-zéro,
idempotence, non-mutation), build_vision_capabilities (ProcessHistory
conditionné), instructions (VISUAL CHECK vs caveat), assemblage Agent, et le
chemin complet IN-PROCESS (FastMCP ImageContent → MCPToolset → ToolReturnPart
multimodal) + sérialisation OpenAI (data-URI llama-server).
"""

import asyncio
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graph_orchestrator.coder_pydantic import (
    build_coder_agent,
    build_coder_capabilities,
    build_coder_instructions,
)
from graph_orchestrator.coder_pydantic_mcp import make_process_tool_call, render_mcp_result
from graph_orchestrator.coder_pydantic_vision import (
    build_vision_capabilities,
    make_image_tool_return,
    purge_history_images,
    split_tool_result,
)
from graph_orchestrator.config import load_settings

from pydantic_ai.messages import BinaryImage, ModelRequest, ToolReturnPart


def _base_task(**overrides) -> dict:
    task = {
        "id": "ts-001",
        "content": "Crée un visualiseur Bubble Sort en HTML/CSS/JS vanilla sur 3 fichiers.",
        "target_files": ["index.html", "styles.css", "script.js"],
        "strategy": "multifile",
        "sections": [],
        "skills": ["coding"],
        "iteration": 1,
    }
    task.update(overrides)
    return task


def _img(data: bytes = b"\xff\xd8fakejpeg", media: str = "image/jpeg") -> BinaryImage:
    return BinaryImage(data=data, media_type=media)


def _msg_with_image(n: int) -> ModelRequest:
    """Message avec un ToolReturnPart multimodal (le format stocké F-161)."""
    part = ToolReturnPart(
        tool_name="take_screenshot",
        content=[f"shot {n}", _img(data=f"bytes-{n}".encode() * 4, media="image/png")],
    )
    return ModelRequest(parts=[part])


# ============================================================
# split_tool_result — texte/images, jamais str(bytes)
# ============================================================


class TestSplitToolResult:
    def test_binary_image_alone(self):
        """Le cas prod de take_screenshot : résultat mappé = BinaryImage SEUL."""
        image = _img()
        text, images = split_tool_result(image)
        assert text == ""
        assert images == [image]

    def test_mixed_list(self):
        text, images = split_tool_result(["Screenshot captured.", _img()])
        assert text == "Screenshot captured."
        assert len(images) == 1

    def test_str_passthrough(self):
        assert split_tool_result("plain") == ("plain", [])
        assert split_tool_result(None) == ("", [])

    def test_result_object_content_blocks(self):
        """Résultat fastmcp factice (.content blocs .text) — rétrocompat."""

        class Block:
            def __init__(self, text):
                self.text = text

        class Res:
            content = [Block("a"), Block("b")]

        assert split_tool_result(Res()) == ("a\nb", [])

    def test_data_fallback_json(self):
        class Res:
            content = None
            data = {"verdict": "SORTED_AFTER_WAIT"}

        text, images = split_tool_result(Res())
        assert "SORTED_AFTER_WAIT" in text and not images

    def test_no_bytes_garbage_regression(self):
        """Régression F-160 : l'ancien render_mcp_result produisait str(bytes)
        (bruit hexadécimal dans le contexte) sur un retour image."""
        text, _ = split_tool_result(_img())
        assert "b'" not in text
        assert render_mcp_result(_img()) == ""


# ============================================================
# make_image_tool_return + process_tool_call multimodal
# ============================================================


class TestImageToolReturn:
    def test_vision_on_returns_mixed_list(self):
        image = _img()
        ret = make_image_tool_return("ok", [image], vision=True)
        assert isinstance(ret, list) and ret[1] is image
        assert "LOOK at it" in ret[0]

    def test_vision_off_returns_text_only(self):
        ret = make_image_tool_return("ok", [_img()], vision=False)
        assert isinstance(ret, str) and "vision disabled" in ret

    def test_no_images_passthrough(self):
        assert make_image_tool_return("ok", [], vision=True) == "ok"


class TestProcessToolCallVision:
    def _run(self, name, mapped_result, vision=True):
        cb = make_process_tool_call(vision=vision)

        async def fake_call_tool(n, a):
            return mapped_result

        async def scenario():
            return await cb(None, fake_call_tool, name, {})

        return asyncio.run(scenario())

    def test_screenshot_binary_image_becomes_multimodal(self):
        ret = self._run("take_screenshot", _img())
        assert isinstance(ret, list)
        assert "LOOK at it" in ret[0] and ret[1].data == b"\xff\xd8fakejpeg"

    def test_screenshot_vision_off_text_only(self):
        ret = self._run("take_screenshot", _img(), vision=False)
        assert isinstance(ret, str) and "vision disabled" in ret

    def test_text_tool_unchanged(self):
        assert self._run("navigate_page", "ok: loaded") == "ok: loaded"

    def test_screenshot_args_still_sanitized(self):
        """F-50/F-90 : filePath strippé AVANT délégation, même chemin vision."""
        captured = {}

        async def fake_call_tool(n, a):
            captured["args"] = a
            return _img()

        cb = make_process_tool_call(vision=True)

        async def scenario():
            return await cb(None, fake_call_tool, "take_screenshot", {"filePath": "x.png"})

        ret = asyncio.run(scenario())
        assert captured["args"] == {} and isinstance(ret, list)


# ============================================================
# purge_history_images — parité F-101/F-116
# ============================================================


class TestPurgeHistoryImages:
    def test_keep_last_only_and_archive(self, tmp_path):
        archive = str(tmp_path / "images")
        messages = [_msg_with_image(1), _msg_with_image(2), _msg_with_image(3)]
        purged = purge_history_images(messages, keep=1, archive_dir=archive)
        # La DERNIÈRE image reste vivante (parité F-101 « very last step's image »).
        assert purged[2].parts[0].files
        assert not purged[0].parts[0].files and not purged[1].parts[0].files
        # Placeholders perte-zéro + archives sur disque.
        assert "[Screenshot archivé:" in purged[0].parts[0].content
        assert "shot 1" in purged[0].parts[0].content  # texte d'origine conservé
        files = os.listdir(archive)
        assert len(files) == 2 and all(f.endswith(".png") for f in files)

    def test_keep_zero_purges_all(self, tmp_path):
        messages = [_msg_with_image(1), _msg_with_image(2)]
        purged = purge_history_images(messages, keep=0, archive_dir=str(tmp_path))
        assert not any(m.parts[0].files for m in purged)

    def test_no_images_unchanged(self):
        part = ToolReturnPart(tool_name="read_file", content="hello")
        messages = [ModelRequest(parts=[part])]
        assert purge_history_images(messages, keep=1) is messages

    def test_negative_keep_disabled(self):
        messages = [_msg_with_image(1)]
        assert purge_history_images(messages, keep=-1) is messages

    def test_no_mutation_of_originals(self, tmp_path):
        """Contrat ProcessHistory : parts remplacées par objets NEUFS."""
        messages = [_msg_with_image(1), _msg_with_image(2)]
        purged = purge_history_images(messages, keep=1, archive_dir=str(tmp_path))
        assert all(m.parts[0].files for m in messages)  # originaux intacts
        assert purged[0] is not messages[0]
        assert purged[1] is messages[1]  # non modifié → identité préservée

    def test_idempotent(self, tmp_path):
        archive = str(tmp_path / "images")
        messages = [_msg_with_image(1), _msg_with_image(2)]
        once = purge_history_images(messages, keep=1, archive_dir=archive)
        purge_history_images(once, keep=1, archive_dir=archive)
        assert len(os.listdir(archive)) == 1  # pas de double archivage

    def test_multiple_images_in_one_part(self, tmp_path):
        """Plusieurs images dans un même retour (F-101 : keep la dernière)."""
        part = ToolReturnPart(
            tool_name="take_screenshot",
            content=["shot", _img(data=b"one", media="image/png"), _img(data=b"two", media="image/jpeg")],
        )
        purged = purge_history_images([ModelRequest(parts=[part])], keep=1, archive_dir=str(tmp_path))
        files = purged[0].parts[0].files
        assert len(files) == 1 and files[0].data == b"two"  # la plus récente garde
        assert "[Screenshot archivé:" in purged[0].parts[0].content[0]  # texte + placeholder


# ============================================================
# build_vision_capabilities + assemblage
# ============================================================


class TestVisionCapabilities:
    def test_default_settings_yields_process_history(self):
        caps = build_vision_capabilities(load_settings())
        assert len(caps) == 1
        from pydantic_ai.capabilities.process_history import ProcessHistory

        assert isinstance(caps[0], ProcessHistory)

    def test_disabled_settings_empty(self):
        import dataclasses

        settings = dataclasses.replace(load_settings(), coder_pydantic_vision=False)
        assert build_vision_capabilities(settings) == []

    def test_capability_in_build_coder_capabilities_both_modes(self):
        """La purge est INCONDITIONNELLE (protège le contexte du flux image),
        y compris guards=False (A/B F-158)."""
        from pydantic_ai.capabilities.process_history import ProcessHistory

        settings = load_settings()
        for guards in (True, False):
            caps = build_coder_capabilities(_base_task(), settings, guards=guards)
            assert any(isinstance(c, ProcessHistory) for c in caps), guards

    def test_capability_absent_when_disabled(self):
        import dataclasses

        from pydantic_ai.capabilities.process_history import ProcessHistory

        settings = dataclasses.replace(load_settings(), coder_pydantic_vision=False)
        caps = build_coder_capabilities(_base_task(), settings, guards=True)
        assert not any(isinstance(c, ProcessHistory) for c in caps)

    def test_agent_constructs_with_vision(self):
        from pydantic_ai.models.test import TestModel

        agent = build_coder_agent(
            TestModel(), _base_task(), load_settings(), coder_max_tokens=2048, guards=False
        )
        assert agent is not None


# ============================================================
# Instructions — VISUAL CHECK vs caveat 3.5
# ============================================================


class TestInstructionsVision:
    def test_default_vision_block_has_visual_check(self):
        instructions = build_coder_instructions(_base_task(), browser_tools_available=True)
        assert "VISUAL CHECK" in instructions
        assert "AS AN IMAGE" in instructions
        # Le caveat 3.5 est retiré en mode nominal.
        assert "text confirmation only" not in instructions

    def test_vision_off_keeps_caveat(self):
        instructions = build_coder_instructions(
            _base_task(), browser_tools_available=True, vision_available=False
        )
        assert "text confirmation only" in instructions
        assert "VISUAL CHECK" not in instructions

    def test_visual_criteria_looking_at_screenshot(self):
        task = _base_task(visual_success_criteria=["30 bars visible"])
        on = build_coder_instructions(task, browser_tools_available=True)
        assert "LOOKING at your latest screenshot" in on
        off = build_coder_instructions(task, browser_tools_available=True, vision_available=False)
        assert "through DOM probes" in off

    def test_workflow_numbering_consistent(self):
        """Numérotation automatique : chaque étape a un numéro strictement croissant.
        (F-166 : l'étape MECHANICAL ERRORS insérée après le step FIX décale la
        numérotation aval d'une unité — 6→7 VISUAL CHECK, 7→8 ANIMATED.)"""
        on = build_coder_instructions(_base_task(), browser_tools_available=True)
        assert "1. `navigate_page" in on and "7. VISUAL CHECK" in on and "8. ANIMATED" in on
        off = build_coder_instructions(
            _base_task(), browser_tools_available=True, vision_available=False
        )
        assert "1. `navigate_page" in off and "7. ANIMATED" in off


# ============================================================
# Intégration IN-PROCESS (vrai MCPToolset) + sérialisation OpenAI
# ============================================================


class TestEndToEndInProcess:
    def test_image_content_through_real_mcp_toolset(self):
        """Chemin complet prod : serveur FastMCP IN-PROCESS → ImageContent →
        VRAI MCPToolset (mapping natif BinaryImage) → process_tool_call →
        ToolReturnPart multimodal dans l'historique de l'agent."""
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ImageContent

        fake_devtools = FastMCP("fake-devtools")

        @fake_devtools.tool()
        def take_screenshot() -> ImageContent:  # noqa: ANN201
            """Captures a screenshot of the current page."""
            return ImageContent(
                type="image",
                data=base64.b64encode(b"\xff\xd8fakejpeg").decode(),
                mimeType="image/jpeg",
            )

        async def scenario():
            from pydantic_ai import Agent
            from pydantic_ai.mcp import MCPToolset
            from pydantic_ai.models.test import TestModel

            ts = MCPToolset(fake_devtools, process_tool_call=make_process_tool_call(vision=True))
            agent = Agent(TestModel(), toolsets=[ts])
            async with agent:
                result = await agent.run("take a screenshot")
            return [
                p
                for m in result.all_messages()
                for p in getattr(m, "parts", [])
                if getattr(p, "part_kind", "") == "tool-return"
            ]

        returns = asyncio.run(scenario())
        images = [f for p in returns for f in p.files]
        assert images and images[0].data == b"\xff\xd8fakejpeg"
        assert images[0].media_type == "image/jpeg"

    def test_openai_serialization_data_uri(self):
        """Le ToolReturnPart multimodal part vers llama-server en message tool
        (texte) + message user (image data-URI base64) — même format que le
        chemin smolagents F-50. Interne _map_user_message (version pinée
        0.24.0) : voir pydantic_ai/models/openai.py."""
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
        from pydantic_ai.providers.openai import OpenAIProvider

        profile = OpenAIModelProfile(
            openai_supports_strict_tool_definition=False,
            openai_chat_supports_multiple_system_messages=False,
            openai_chat_supports_max_completion_tokens=False,
        )
        model = OpenAIChatModel(
            "qwen-test",
            provider=OpenAIProvider(base_url="http://127.0.0.1:1/v1", api_key="x"),
            profile=profile,
        )
        part = ToolReturnPart(
            tool_name="take_screenshot", content=["Screenshot captured.", _img()]
        )
        msg = ModelRequest(parts=[part])

        async def scenario():
            out = []
            async for m in model._map_user_message(msg):
                out.append(m)
            return out

        out = asyncio.run(scenario())
        assert [m["role"] for m in out] == ["tool", "user"]
        assert "Screenshot captured." in out[0]["content"]
        image_parts = [p for p in out[1]["content"] if p.get("type") == "image_url"]
        assert image_parts
        assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
