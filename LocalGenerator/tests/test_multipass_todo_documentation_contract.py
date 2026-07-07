from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TODO = ROOT / "docs" / "TODO_ROADMAP_VERY_LATER_RU.md"


def test_unified_todo_document_exists_and_documents_multipass_validation() -> None:
    text = TODO.read_text(encoding="utf-8")
    assert "один запрос игрока" in text
    assert "Core Author" in text
    assert "Specialist Authors" in text
    assert "Code validation после каждого Specialist Author" in text
    assert "routing идёт только из structured `authoringModules`, не из prompt text" in text
    assert "Deterministic Merger" in text


def test_unified_todo_documents_applied_vs_authored_validator() -> None:
    text = TODO.read_text(encoding="utf-8")
    assert "Applied vs Authored Validator" in text
    assert "LLM authored" in text
    assert "runtimeApplied" in text
    assert "future_disabled" in text
    assert "Не превращать validator в ещё одного автора" in text


def test_unified_todo_documents_runtime_archetype_safety_boundary() -> None:
    text = TODO.read_text(encoding="utf-8")
    assert "RuntimeArchetypeSpec" in text
    assert "не убивает" in text
    assert "data-authored contract layer" in text
    assert "RuntimeArchetypeSpec must not become a hidden author" in text
    assert "No RuntimeArchetypeSpec overriding authored runtimePlan silently" in text


def test_unified_todo_documents_injection_bridge_as_very_later() -> None:
    text = TODO.read_text(encoding="utf-8")
    assert "InfiniVanillaHookBridge" in text
    assert "Very later" in text
    assert "global detour/IL bridge" in text
    assert "per-item guard" in text
    assert "No LLM-authored raw detours/IL/method names" in text


def test_old_split_todo_files_were_merged_into_single_canonical_file() -> None:
    assert TODO.exists()
    folder_docs = (ROOT / "docs" / "FOLDER_DOCS_RU.md").read_text(encoding="utf-8")
    assert "TODO_ROADMAP_VERY_LATER_RU.md" in folder_docs
    # Local historical files may exist in a dirty workspace, but the canonical docs index
    # must no longer route agents to the split TODOs.
    assert "TODO_LIST_MULTIPASS_AUTHORING_RU.md" not in folder_docs
    assert "TODO_APPLIED_VS_AUTHORED_VALIDATOR_RU.md" not in folder_docs
    assert "ARCHITECTURE_TODO_VERY_LATER_RU.md" not in folder_docs
