from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
studio = ROOT / "src/mi_llama/workspace_assets/studio.js"
text = studio.read_text()


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one studio.js match, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    """function wordCount(text) {\n  const trimmed = text.trim()\n  return trimmed ? trimmed.split(/\\s+/u).length : 0\n}\n""",
    """function wordCount(text) {\n  const trimmed = text.trim()\n  return trimmed ? trimmed.split(/\\s+/u).length : 0\n}\n\nfunction stableJson(value) {\n  if (value === null || typeof value !== 'object') return JSON.stringify(value)\n  if (Array.isArray(value)) return `[${value.map((item) => stableJson(item)).join(',')}]`\n  return `{${Object.keys(value)\n    .sort()\n    .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)\n    .join(',')}}`\n}\n\nfunction editorMatchesDraft(editor, draft = state.draft) {\n  if (!editor || !draft) return false\n  return (\n    editor.getText() === (draft.plain_text || '') &&\n    stableJson(editor.getDocumentState()) === stableJson(draft.editor_state || null)\n  )\n}\n""",
)

replace_once(
    """async function revisionSeed(document) {\n  if (!document?.current_revision_id) return ''\n  const revisions = await apiJson(\n    `/api/projects/${state.projectId}/writing/documents/${document.id}/revisions`,\n  )\n  const current = revisions.find((item) => item.id === document.current_revision_id)\n  return current?.content || ''\n}\n""",
    """async function revisionSeed(document) {\n  if (!document?.current_revision_id) {\n    return { text: '', editorState: documentStateForText('') }\n  }\n  const revisions = await apiJson(\n    `/api/projects/${state.projectId}/writing/documents/${document.id}/revisions`,\n  )\n  const current = revisions.find((item) => item.id === document.current_revision_id)\n  const text = current?.content || ''\n  return {\n    text,\n    editorState: current?.editor_state || documentStateForText(text),\n  }\n}\n""",
)

replace_once(
    """  if (!draft) {\n    const text = await revisionSeed(document)\n    try {\n      draft = await apiJson(\n        `/api/projects/${state.projectId}/writing/documents/${document.id}/draft`,\n        {\n          method: 'PUT',\n          body: JSON.stringify({\n            expected_version: null,\n            base_revision_id: document.current_revision_id,\n            editor_state: documentStateForText(text),\n            plain_text: text,\n          }),\n        },\n      )\n    } catch (error) {\n      if (error instanceof AuthError && error.status === 403) {\n        state.canEdit = false\n        draft = {\n          version: null,\n          base_revision_id: document.current_revision_id,\n          plain_text: text,\n          editor_state: documentStateForText(text),\n        }\n      } else {\n        throw error\n      }\n    }\n  }\n""",
    """  if (!draft) {\n    const seed = await revisionSeed(document)\n    try {\n      draft = await apiJson(\n        `/api/projects/${state.projectId}/writing/documents/${document.id}/draft`,\n        {\n          method: 'PUT',\n          body: JSON.stringify({\n            expected_version: null,\n            base_revision_id: document.current_revision_id,\n            editor_state: seed.editorState,\n            plain_text: seed.text,\n          }),\n        },\n      )\n    } catch (error) {\n      if (error instanceof AuthError && error.status === 403) {\n        state.canEdit = false\n        draft = {\n          version: null,\n          base_revision_id: document.current_revision_id,\n          plain_text: seed.text,\n          editor_state: seed.editorState,\n        }\n      } else {\n        throw error\n      }\n    }\n  }\n""",
)

replace_once(
    """function onEditorInput() {\n  const editor = getEditorAdapter()\n  if (!editor) return\n  state.localText = editor.getText()\n  state.dirty = state.localText !== (state.draft?.plain_text || '')\n  state.proposal = null\n""",
    """function onEditorInput() {\n  const editor = getEditorAdapter()\n  if (!editor) return\n  state.localText = editor.getText()\n  state.dirty = !editorMatchesDraft(editor)\n  state.proposal = null\n""",
)

replace_once(
    """  const expectedVersion = state.draft.version\n  const baseRevisionId = state.draft.base_revision_id\n  const text = state.localText\n  state.saving = true\n""",
    """  const expectedVersion = state.draft.version\n  const baseRevisionId = state.draft.base_revision_id\n  const text = state.localText\n  const editor = getEditorAdapter()\n  const editorState = editor?.getDocumentState() || documentStateForText(text)\n  state.saving = true\n""",
)

replace_once(
    """            editor_state: documentStateForText(text),\n            plain_text: text,\n""",
    """            editor_state: editorState,\n            plain_text: text,\n""",
)

replace_once(
    """      state.draft = updated\n      state.saveError = null\n      state.conflict = false\n      state.dirty = state.localText !== text\n      setStudioStatus(`Saved · v${updated.version}`, 'saved')\n""",
    """      state.draft = updated\n      state.saveError = null\n      state.conflict = false\n      const currentEditor = getEditorAdapter()\n      if (currentEditor) state.localText = currentEditor.getText()\n      state.dirty = currentEditor\n        ? !editorMatchesDraft(currentEditor, updated)\n        : state.localText !== (updated.plain_text || '')\n      setStudioStatus(`Saved · v${updated.version}`, 'saved')\n""",
)

studio.write_text(text)

# This maintenance helper exists only to perform the surgical controller edit.
# Remove it and its one-shot workflow in the same bot-authored commit.
Path(__file__).unlink()
workflow = ROOT / ".github/workflows/activation-maintenance.yml"
if workflow.exists():
    workflow.unlink()
