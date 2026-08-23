"""Vision multimodale du Coder pydantic — phase 3.6 (F-161).

Plan docs/PLAN_MIGRATION_PYDANTIC_HARNESS.md §3.6 : les screenshots MCP DevTools
deviennent des retours multimodaux d'outils (le modèle VOIT l'image), et la
purge perte-zéro F-101/F-116 (une seule image vivante dans le contexte, les
anciennes archivées) migre sur le seam officiel ``ProcessHistory``.

Mécanisme natif exploité (doc pydantic.dev core-concepts/input + source
``pydantic_ai/mcp.py`` / ``messages.py``) :
  - le toolset MCP mappe déjà ``ImageContent`` → ``BinaryImage`` ;
  - un ``ToolReturnPart`` au contenu mixte ``[str, BinaryImage]`` est sérialisé
    par ``OpenAIChatModel`` en message ``role=tool`` (texte) + message ``user``
    séparé portant l'image en data-URI — llama-server (FAST_MMPROJ) la décode
    via mmproj, exactement comme le chemin smolagents F-50 envoyait le base64.

Contenu :
  - ``split_tool_result`` : sépare un résultat d'appel MCP (déjà mappé par le
    toolset : ``str | BinaryContent | list`` mixte) en texte modèle-friendly +
    images — ``render_mcp_result`` (coder_pydantic_mcp) s'appuie dessus et ne
    renvoie plus ``str(bytes)`` (bruit hexadécimal) sur un retour image ;
  - ``make_image_tool_return`` : contenu de retour de ``process_tool_call``
    pour un outil image — ``[note_texte, *images]`` (ToolResult valide) ;
  - ``purge_history_images`` : processor d'historique (keep=N dernières images,
    archive disque ``.transcripts/images/`` + placeholder, objets NEUFS —
    jamais de mutation in-place, cf. MessageHistoryMutatedWarning) ;
  - ``build_vision_capabilities`` : ``ProcessHistory`` câblé avant chaque
    requête modèle (miroir du standalone DeduplicateFileReads F-159).

Parité comportementale smolagents : ``keep`` défaut 1 = F-101/F-116 (« purge
all visual memory except the very last step's image ») ; wording du placeholder
``[Screenshot archivé: …]`` identique.

Activation : ``CODER_PYDANTIC_VISION`` (défaut true). Le flag off reproduit un
monde sans vision (screenshot → texte seul, sans image dans le contexte).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Note texte accompagnant l'image dans le retour d'outil (le framework ajoute
# lui-même « This is file <id>: » devant la partie image du message user).
IMAGE_RETURN_NOTE = (
    "Screenshot captured. The image is attached below: LOOK at it and compare "
    "the rendered UI against the expected look and the visual criteria."
)

# Note quand la vision est désactivée (CODER_PYDANTIC_VISION=false).
IMAGE_DISABLED_NOTE = (
    "Screenshot captured (image content NOT delivered — vision disabled: "
    "CODER_PYDANTIC_VISION=false). Base your verdicts on console + DOM probes."
)

_PLACEHOLDER_UNAVAILABLE = "[Screenshot archivé: (archive indisponible)]"


def _is_binary_content(item: Any) -> bool:
    """Vrai pour un contenu binaire pydantic-ai (BinaryContent/BinaryImage…).

    Détection structurelle (pas d'import hard) : data bytes + media_type str,
    sans ``.text`` — un ``CallToolResult`` fastmcp ou un bloc texte n'entre
    jamais dans cette catégorie.
    """
    return (
        hasattr(item, "data")
        and hasattr(item, "media_type")
        and isinstance(getattr(item, "media_type", None), str)
        and not isinstance(item, (str, bytes))
    )


def split_tool_result(result: Any) -> Tuple[str, list]:
    """Sépare un résultat d'appel MCP en (texte modèle-friendly, images).

    ``result`` est le retour du ``call_tool`` fourni à ``process_tool_call`` —
    c'est-à-dire le résultat DÉJÀ mappé par le toolset (``str``,
    ``BinaryContent``/``BinaryImage``, ``dict``, ou liste mixte ; les tests
    fournissent aussi des ``CallToolResult`` factices .content/.data). Les
    items binaires sont extraits INTACTS (jamais rendus en ``str(bytes)``).
    """
    images: list = []

    def _render(item: Any) -> str:
        if item is None:
            return ""
        if isinstance(item, str):
            return item
        if _is_binary_content(item):
            images.append(item)
            return ""
        # Bloc de contenu MCP texte (.text) ou structure .content (résultat
        # fastmcp) : délégation au rendu réciproque de coder_pydantic_mcp.
        text = getattr(item, "text", None)
        if isinstance(text, str) and text:
            return text
        content = getattr(item, "content", None)
        if content:
            rendered = [_render(b) for b in content]
            return "\n".join(p for p in rendered if p)
        data = getattr(item, "data", None)
        if data is not None and not isinstance(data, (bytes, bytearray)):
            if isinstance(data, str):
                return data
            import json

            try:
                return json.dumps(data, ensure_ascii=False)
            except Exception:  # noqa: BLE001 — dernier repli
                return str(data)
        return str(item) if not _is_binary_content(item) else ""

    if isinstance(result, list):
        rendered = [_render(item) for item in result]
        return "\n".join(p for p in rendered if p), images
    return _render(result), images


def make_image_tool_return(text: str, images: list, vision: bool = True) -> Any:
    """Contenu de retour ``process_tool_call`` pour un outil à retour image.

    Vision ON → ``[note_texte, *images]`` : liste mixte que le framework
    éclate en tool message texte + message user image (ToolResult valide —
    doc mcp/client « Tool call customization »). Vision OFF → texte seul.
    """
    if images and vision:
        return [IMAGE_RETURN_NOTE if not text else f"{text}\n{IMAGE_RETURN_NOTE}", *images]
    if images:
        return f"{text}\n{IMAGE_DISABLED_NOTE}" if text else IMAGE_DISABLED_NOTE
    return text


# ============================================================
# Purge perte-zéro des images d'historique (F-101/F-161)
# ============================================================


def _archive_image(data: bytes, media_type: str, archive_dir: str, stem: str) -> Optional[str]:
    """Écrit l'image archivée sur disque, retourne son chemin relatif (ou None)."""
    ext = "png"
    if "jpeg" in media_type or "jpg" in media_type:
        ext = "jpg"
    elif "webp" in media_type:
        ext = "webp"
    digest = hashlib.sha256(data).hexdigest()[:8]
    path = os.path.join(archive_dir, f"{stem}_{digest}.{ext}")
    try:
        os.makedirs(archive_dir, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return path
    except Exception as exc:  # noqa: BLE001 — l'archive ne doit jamais casser la purge
        logger.warning("coder_pydantic_vision: archive image KO (%s).", exc)
        return None


def purge_history_images(messages: list, keep: int = 1,
                         archive_dir: Optional[str] = None) -> list:
    """Processor d'historique : garde les ``keep`` DERNIÈRES images en contexte.

    Miroir pydantic de ``compaction.apply_image_purge`` (F-101/F-116) : chaque
    image évincée est archivée sur disque (``archive_dir``, défaut
    ``.transcripts/images``) puis remplacée par un placeholder texte dans le
    ``ToolReturnPart`` — reconstruit en objet NEUF (``dataclasses.replace``),
    jamais muté in-place (contrat ProcessHistory / MessageHistoryMutatedWarning).
    Idempotent : les images déjà purgées sont des placeholders, donc invisibles
    à la passe suivante.

    ``keep=0`` purge tout ; ``keep<0`` désactive (retour liste identique).
    """
    if keep < 0:
        return messages
    if archive_dir is None:
        archive_dir = os.path.join(".transcripts", "images")

    from pydantic_ai.messages import ModelRequest, ToolReturnPart

    # 1. Comptage des images en partant de la fin (les plus récentes gagnent).
    parts_with_files: list = []  # (i_msg, part, files) — ordre du parcours
    for i_msg, msg in enumerate(messages):
        for part in getattr(msg, "parts", []):
            files = getattr(part, "files", None) or []
            if files and isinstance(part, ToolReturnPart):
                parts_with_files.append((i_msg, part, files))

    if not parts_with_files:
        return messages

    to_purge: dict = {}  # id(part) -> (part, [placeholder…], [images gardées])
    seen = 0
    for i_msg, part, files in reversed(parts_with_files):
        placeholders: list = []
        kept: list = []
        # Au sein d'un même part, la plus récente est la DERNIÈRE de la liste.
        for file in reversed(files):
            seen += 1
            if seen <= keep:
                kept.append(file)  # image vivante conservée
                continue
            data = getattr(file, "data", None)
            media_type = str(getattr(file, "media_type", "") or "image/png")
            archived = None
            if isinstance(data, (bytes, bytearray)):
                archived = _archive_image(bytes(data), media_type, archive_dir, f"img_msg{i_msg}")
            placeholders.append(
                f"[Screenshot archivé: {archived}]" if archived else _PLACEHOLDER_UNAVAILABLE
            )
        if placeholders:
            to_purge[id(part)] = (part, placeholders, list(reversed(kept)))

    if not to_purge:
        return messages

    # 2. Reconstruction : nouveaux messages/parts, originaux intacts.
    #    (ToolReturnPart/ModelRequest sont des dataclasses — replace() clône.)
    import dataclasses as _dc

    new_messages: list = []
    for i_msg, msg in enumerate(messages):
        if not isinstance(msg, ModelRequest):
            new_messages.append(msg)
            continue
        new_parts: list = []
        changed = False
        for part in msg.parts:
            hit = to_purge.get(id(part))
            if hit is None:
                new_parts.append(part)
                continue
            old_part, placeholders, kept = hit
            str_items = [s for s in old_part.content_items(mode="str", wrap_if_error=False) if isinstance(s, str)]
            text = "\n".join([*str_items, *placeholders])
            # Les images vivantes de ce part restent dans le contenu (liste
            # mixte str + BinaryImage — même forme que le retour d'outil F-161).
            new_parts.append(
                _dc.replace(old_part, content=[text, *kept] if kept else text)
            )
            changed = True
        new_messages.append(_dc.replace(msg, parts=new_parts) if changed else msg)
    return new_messages


# ============================================================
# Capability officielle (ProcessHistory)
# ============================================================


def build_vision_capabilities(settings) -> list:
    """Capabilities vision du profil Coder — purge avant CHAQUE requête modèle.

    Retourne ``[ProcessHistory(processor=purge…)]`` (seam officiel des history
    processors, doc pydantic.dev capabilities — équivalent exact du standalone
    DeduplicateFileReads F-159 : s'exécute à chaque requête, indépendamment du
    seuil de compaction TieredCompaction qui ne voit les images qu'après
    déclenchement). Vide si ``coder_pydantic_vision`` est désactivé.
    """
    if not getattr(settings, "coder_pydantic_vision", True):
        return []
    from pydantic_ai.capabilities.process_history import ProcessHistory

    keep = int(getattr(settings, "coder_pydantic_vision_keep", 1) or 0)

    def _purge(messages: list) -> list:
        try:
            return purge_history_images(messages, keep=keep)
        except Exception as exc:  # noqa: BLE001 — fail-open total
            logger.warning("coder_pydantic_vision: purge KO (%s) — historique intact.", exc)
            return messages

    return [ProcessHistory(processor=_purge)]
