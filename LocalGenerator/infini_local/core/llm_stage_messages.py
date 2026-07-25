"""Attributed Chat History and Agent Handoff for the finite LLM pipeline.

``role`` preserves Chat Completions authority, stage-specific system content and the
latest user packet define model-visible authority/current truth, ``name`` is a finite
trace/provider hint, and ``agentHandoff`` records stage provenance.
"""

from __future__ import annotations

from typing import Any


# Canonical speaker identities for OpenAI-compatible Chat Completions.  ``role``
# keeps transport authority (system/user/assistant); ``name`` identifies the
# concrete InfiniCrafter pipeline participant for traces and compatible providers.
# Correctness must not depend on the model reading optional ``name`` metadata.
STAGE_MESSAGE_NAMES = frozenset({
    "item_author_contract",
    "recipe_context",
    "item_planner",
    "final_wire_compiler",
    "authoring_contract_gate",
    "author_repair_contract",
    "author_repair_context",
    "visual_director_contract",
    "visual_director_context",
    "visual_director",
    "visual_repair_contract",
    "visual_repair_context",
    "vfx_director_contract",
    "vfx_director_context",
    "vfx_director",
    "vfx_repair_contract",
    "vfx_repair_context",
    "vfx_validator",
    "pipeline_orchestrator",

})

ATTRIBUTED_PLANNER_HISTORY_KIND = "attributed_planner_history_v1"
_PLANNER_HISTORY_SIGNATURE = (
    ("system", "item_author_contract"),
    ("user", "recipe_context"),
    ("assistant", "item_planner"),
)


def stage_chat_message(role: str, name: str, content: str) -> dict[str, str]:
    """Build one attributed Chat Completions message from a finite speaker set."""
    role = str(role or "").strip().lower()
    name = str(name or "").strip()
    content = str(content or "")
    if role not in {"system", "user", "assistant"}:
        raise ValueError(f"unsupported chat role: {role!r}")
    if name not in STAGE_MESSAGE_NAMES:
        raise ValueError(f"unsupported pipeline message name: {name!r}")
    return {"role": role, "name": name, "content": content}


def agent_handoff(
    *,
    previous_speaker: str,
    current_speaker: str,
    next_speaker: str,
    cause_by: str,
    artifact_source: str,
) -> dict[str, Any]:
    """Attach agent provenance and the next speaker without summarizing chat history."""
    for speaker in (previous_speaker, current_speaker, next_speaker):
        if speaker not in STAGE_MESSAGE_NAMES:
            raise ValueError(f"unsupported pipeline speaker: {speaker!r}")
    return {
        "schema": "infini.llm-handoff.v1",
        "previousSpeaker": previous_speaker,
        "currentSpeaker": current_speaker,
        "nextSpeaker": next_speaker,
        "causeBy": str(cause_by or "").strip(),
        "artifactSource": str(artifact_source or "").strip(),
    }


def attributed_planner_history(system: str, user: str, assistant: str) -> dict[str, Any]:
    """Store Planner continuation as canonical named messages, not parallel string fields."""
    return {
        "kind": ATTRIBUTED_PLANNER_HISTORY_KIND,
        "messages": [
            stage_chat_message("system", "item_author_contract", system),
            stage_chat_message("user", "recipe_context", user),
            stage_chat_message("assistant", "item_planner", assistant),
        ],
    }


def attributed_planner_messages(value: Any) -> list[dict[str, str]] | None:
    """Validate and clone the one supported transient Planner-history contract."""
    if not isinstance(value, dict) or value.get("kind") != ATTRIBUTED_PLANNER_HISTORY_KIND:
        return None
    raw = value.get("messages")
    if not isinstance(raw, list) or len(raw) != len(_PLANNER_HISTORY_SIGNATURE):
        return None
    messages: list[dict[str, str]] = []
    for message, (expected_role, expected_name) in zip(raw, _PLANNER_HISTORY_SIGNATURE):
        if not isinstance(message, dict):
            return None
        role = str(message.get("role") or "")
        name = str(message.get("name") or "")
        content = str(message.get("content") or "")
        if (role, name) != (expected_role, expected_name) or not content.strip():
            return None
        messages.append(stage_chat_message(role, name, content))
    return messages


def planner_history_state(data: Any) -> str:
    """Classify transient Planner context without treating malformed as absent."""
    if not isinstance(data, dict) or "_llmHistory" not in data:
        return "absent"
    return "valid" if attributed_planner_messages(data.get("_llmHistory")) is not None else "malformed"


__all__ = [
    "STAGE_MESSAGE_NAMES",
    "ATTRIBUTED_PLANNER_HISTORY_KIND",
    "stage_chat_message",
    "agent_handoff",
    "attributed_planner_history",
    "attributed_planner_messages",
    "planner_history_state",
]
