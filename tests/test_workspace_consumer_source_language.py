from pathlib import Path


ASSETS = Path(__file__).parents[1] / "src" / "mi_llama" / "workspace_assets"


def test_grounding_review_uses_writer_facing_source_language() -> None:
    script = (ASSETS / "studio_grounding_review.js").read_text()

    assert "Sources used" in script
    assert "View saved passage" in script
    assert "These are the sources Mi-Llama used for this draft." in script
    assert "Inspect frozen passage" not in script
    assert "immutable source packet" not in script
    assert "source integrity" not in script
    assert "SHA-256" not in script
    assert "citation_id" not in script


def test_source_review_surfaces_hide_internal_release_style_vocabulary() -> None:
    closure = (ASSETS / "studio_citation_closure.js").read_text()
    repair = (ASSETS / "studio_provenance_repair.js").read_text()
    visible = closure + repair

    for phrase in (
        "Manuscript provenance health",
        "Citation closure",
        "Grounding disposition",
        "Record exact supersession",
        "Accepted repair lineage",
        "Frozen grounding evidence",
        "Resolved provenance history",
        "durably marked needs re-grounding",
    ):
        assert phrase not in visible

    assert "Source check" in closure
    assert "Citations to review" in closure
    assert "Source history" in repair
    assert "Find fresh evidence" in repair
