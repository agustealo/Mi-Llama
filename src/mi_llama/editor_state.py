from __future__ import annotations

import json
from typing import Any

MAX_EDITOR_STATE_BYTES = 8_000_000
MAX_EDITOR_NODES = 100_000
MAX_EDITOR_DEPTH = 32
MAX_PLAIN_TEXT_CHARS = 2_000_000

_ALLOWED_BLOCKS = {
    "paragraph",
    "heading",
    "blockquote",
    "bulletList",
    "orderedList",
    "listItem",
    "codeBlock",
}
_ALLOWED_INLINE = {"text", "hardBreak"}
_ALLOWED_MARKS = {"bold", "italic", "strike", "underline", "code", "link"}


class EditorStateError(ValueError):
    """Editor state is malformed, unsupported, or inconsistent with canonical text."""


def project_editor_state(editor_state: dict[str, Any]) -> str:
    """Return the canonical plain-text projection for a supported editor state."""
    if not isinstance(editor_state, dict):
        raise EditorStateError("Editor state must be an object")
    try:
        encoded_size = len(
            json.dumps(editor_state, ensure_ascii=False, separators=(",", ":")).encode()
        )
    except (TypeError, ValueError) as exc:
        raise EditorStateError("Editor state must be JSON serializable") from exc
    if encoded_size > MAX_EDITOR_STATE_BYTES:
        raise EditorStateError("Editor state exceeds the maximum serialized size")

    schema = editor_state.get("schema")
    if schema == "plain_text_v1":
        if set(editor_state) != {"schema", "text"}:
            raise EditorStateError("plain_text_v1 editor state contains unsupported fields")
        text = editor_state.get("text")
        if not isinstance(text, str):
            raise EditorStateError("plain_text_v1 text must be a string")
        _validate_text_size(text)
        return text

    if schema == "tiptap_v1":
        if set(editor_state) != {"schema", "doc"}:
            raise EditorStateError("tiptap_v1 editor state contains unsupported fields")
        doc = editor_state.get("doc")
        if not isinstance(doc, dict) or doc.get("type") != "doc":
            raise EditorStateError("tiptap_v1 requires a ProseMirror doc root")
        counter = [0]
        text = _project_doc(doc, depth=0, counter=counter)
        _validate_text_size(text)
        return text

    raise EditorStateError(f"Unsupported editor state schema: {schema!r}")


def validate_editor_state(editor_state: dict[str, Any], plain_text: str) -> None:
    """Require editor state and canonical plain text to describe the same document text."""
    if not isinstance(plain_text, str):
        raise EditorStateError("Canonical plain text must be a string")
    _validate_text_size(plain_text)
    projected = project_editor_state(editor_state)
    if projected != plain_text:
        raise EditorStateError("Editor state plain-text projection does not match plain_text")


def _validate_text_size(text: str) -> None:
    if len(text) > MAX_PLAIN_TEXT_CHARS:
        raise EditorStateError("Editor state plain text exceeds the maximum manuscript size")


def _count_node(counter: list[int], depth: int) -> None:
    if depth > MAX_EDITOR_DEPTH:
        raise EditorStateError("Editor state nesting exceeds the maximum depth")
    counter[0] += 1
    if counter[0] > MAX_EDITOR_NODES:
        raise EditorStateError("Editor state exceeds the maximum node count")


def _project_doc(node: dict[str, Any], *, depth: int, counter: list[int]) -> str:
    _count_node(counter, depth)
    _validate_node_keys(node, {"type", "content"})
    content = _content(node)
    blocks = [_project_block(child, depth=depth + 1, counter=counter) for child in content]
    return "\n\n".join(blocks)


def _project_block(node: dict[str, Any], *, depth: int, counter: list[int]) -> str:
    _count_node(counter, depth)
    node_type = node.get("type")
    if node_type not in _ALLOWED_BLOCKS:
        raise EditorStateError(f"Unsupported Tiptap block node: {node_type!r}")

    if node_type == "heading":
        _validate_node_keys(node, {"type", "content", "attrs"})
        attrs = node.get("attrs", {})
        if not isinstance(attrs, dict) or set(attrs) - {"level"}:
            raise EditorStateError("Heading attrs are invalid")
        level = attrs.get("level")
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 6:
            raise EditorStateError("Heading level must be between 1 and 6")
        return _project_inline_content(_content(node), depth=depth + 1, counter=counter)

    if node_type in {"paragraph", "codeBlock"}:
        allowed = {"type", "content"} if node_type == "paragraph" else {"type", "content", "attrs"}
        _validate_node_keys(node, allowed)
        if node_type == "codeBlock":
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict) or set(attrs) - {"language"}:
                raise EditorStateError("Code block attrs are invalid")
            language = attrs.get("language")
            if language is not None and not isinstance(language, str):
                raise EditorStateError("Code block language must be a string or null")
        return _project_inline_content(_content(node), depth=depth + 1, counter=counter)

    if node_type == "blockquote":
        _validate_node_keys(node, {"type", "content"})
        children = _content(node)
        if not children:
            return ""
        return "\n".join(
            _project_block(child, depth=depth + 1, counter=counter) for child in children
        )

    if node_type in {"bulletList", "orderedList"}:
        allowed = {"type", "content"} if node_type == "bulletList" else {"type", "content", "attrs"}
        _validate_node_keys(node, allowed)
        if node_type == "orderedList":
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict) or set(attrs) - {"start"}:
                raise EditorStateError("Ordered-list attrs are invalid")
            start = attrs.get("start", 1)
            if not isinstance(start, int) or isinstance(start, bool) or start < 1:
                raise EditorStateError("Ordered-list start must be a positive integer")
        children = _content(node)
        for child in children:
            if child.get("type") != "listItem":
                raise EditorStateError("List content must contain only listItem nodes")
        return "\n".join(
            _project_block(child, depth=depth + 1, counter=counter) for child in children
        )

    if node_type == "listItem":
        _validate_node_keys(node, {"type", "content"})
        children = _content(node)
        if not children:
            return ""
        return "\n".join(
            _project_block(child, depth=depth + 1, counter=counter) for child in children
        )

    raise EditorStateError(f"Unsupported Tiptap block node: {node_type!r}")


def _project_inline_content(
    content: list[dict[str, Any]], *, depth: int, counter: list[int]
) -> str:
    return "".join(_project_inline(node, depth=depth, counter=counter) for node in content)


def _project_inline(node: dict[str, Any], *, depth: int, counter: list[int]) -> str:
    _count_node(counter, depth)
    node_type = node.get("type")
    if node_type not in _ALLOWED_INLINE:
        raise EditorStateError(f"Unsupported Tiptap inline node: {node_type!r}")

    if node_type == "hardBreak":
        _validate_node_keys(node, {"type"})
        return "\n"

    _validate_node_keys(node, {"type", "text", "marks"})
    text = node.get("text")
    if not isinstance(text, str):
        raise EditorStateError("Tiptap text nodes require a string text field")
    marks = node.get("marks", [])
    if not isinstance(marks, list):
        raise EditorStateError("Tiptap text marks must be an array")
    for mark in marks:
        _validate_mark(mark)
    return text


def _validate_mark(mark: Any) -> None:
    if not isinstance(mark, dict):
        raise EditorStateError("Tiptap marks must be objects")
    _validate_node_keys(mark, {"type", "attrs"})
    mark_type = mark.get("type")
    if mark_type not in _ALLOWED_MARKS:
        raise EditorStateError(f"Unsupported Tiptap mark: {mark_type!r}")
    attrs = mark.get("attrs", {})
    if not isinstance(attrs, dict):
        raise EditorStateError("Tiptap mark attrs must be an object")
    if mark_type != "link":
        if attrs:
            raise EditorStateError(f"{mark_type} marks do not support attrs")
        return
    if set(attrs) - {"href", "target", "rel", "class"}:
        raise EditorStateError("Link mark contains unsupported attrs")
    href = attrs.get("href")
    if not isinstance(href, str) or not href or len(href) > 2_000:
        raise EditorStateError("Link href must be a non-empty string")
    for key in ("target", "rel", "class"):
        value = attrs.get(key)
        if value is not None and not isinstance(value, str):
            raise EditorStateError(f"Link {key} must be a string or null")


def _content(node: dict[str, Any]) -> list[dict[str, Any]]:
    content = node.get("content", [])
    if not isinstance(content, list):
        raise EditorStateError("Tiptap node content must be an array")
    if not all(isinstance(child, dict) for child in content):
        raise EditorStateError("Tiptap node content must contain objects")
    return content


def _validate_node_keys(node: dict[str, Any], allowed: set[str]) -> None:
    extra = set(node) - allowed
    if extra:
        raise EditorStateError(f"Editor node contains unsupported fields: {sorted(extra)}")
