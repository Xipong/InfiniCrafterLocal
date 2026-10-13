"""Read-only account catalog callbacks: saved choices, errors and retired results."""
from __future__ import annotations

import threading

from infini_local.services import codex_auth, codex_catalog
from infini_local.services.codex_catalog import CodexModel
from test_settings_gui_contract import (
    _GuiWorkflowHarness, _UiVar, _SpriteGuiHarness, held_gui_call,
)


class Combo:
    def __init__(self, values=()):
        self.values = values
        self.owner = threading.get_ident()

    def configure(self, *, values):
        assert threading.get_ident() == self.owner, "worker configured a Tk widget"
        self.values = tuple(values)


class Harness(_GuiWorkflowHarness):
    def __init__(self):
        super().__init__()
        self.vars = {key: _UiVar(value) for key, value in {
            "INFINI_CODEX_LLM_MODEL": "saved-custom",
            "INFINI_LLM_REASONING_MODE": "high",
            "INFINI_CODEX_VISUAL_REASONING": "inherit",
        }.items()}
        self.codex_model_combo = Combo(("saved-custom",))
        self.codex_reasoning_combo = Combo()
        self.codex_visual_reasoning_combo = Combo()
        self.codex_catalog_var = _UiVar()
        self.codex_image_account_var = _UiVar()


def test_catalog_refresh_keeps_saved_model_and_unsupported_effort(held_gui_call):
    gui = Harness()
    models = [CodexModel("account-model", "Account", ("low", "medium", "ultra"), "low", 1)]
    hold = held_gui_call(codex_catalog, "list_text_models", models)
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)
    assert gui.codex_model_combo.values == ("saved-custom",)
    hold.release.set()
    gui.drain_until(lambda: "account-model" in gui.codex_model_combo.values)
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    gui.vars["INFINI_CODEX_LLM_MODEL"].set("account-model")
    gui._update_codex_efforts()
    assert gui.codex_reasoning_combo.values == ("off", "low", "medium")
    assert gui.codex_visual_reasoning_combo.values == ("inherit", "model_default", "low", "medium")
    assert gui.vars["INFINI_LLM_REASONING_MODE"].get() == "high"
    assert "не поддерживается" in gui.codex_catalog_var.get()


def test_failed_new_refresh_discards_held_old_success(monkeypatch, held_gui_call):
    gui = Harness()
    hold = held_gui_call(codex_catalog, "list_text_models", [CodexModel("old", "Old", ("low",), "low", 1)])
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)

    def failed():
        raise RuntimeError("FAKE-SECRET-CANARY")

    monkeypatch.setattr(codex_catalog, "list_text_models", failed)
    gui.refresh_codex_text_catalog()
    gui.drain_until(lambda: "не удалось" in gui.codex_catalog_var.get().lower())
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui.jobs)
    assert gui.codex_model_combo.values == ("saved-custom",)
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    assert "CANARY" not in gui.codex_catalog_var.get() + gui.status_var.get()


def test_image_ping_is_read_only_and_does_not_claim_image_entitlement(held_gui_call):
    gui = Harness()
    hold = held_gui_call(codex_catalog, "list_text_models", [])
    gui.ping_codex_image_account()
    assert hold.entered.wait(1)
    hold.release.set()
    gui.drain_until(lambda: not gui.jobs)
    assert len(hold.calls) == 1
    assert gui.codex_model_combo.values == ("saved-custom",)
    assert "image-доступ не проверен" in gui.codex_image_account_var.get()
    assert "image-доступ не проверен" in gui.status_var.get()


def test_logout_discards_pending_catalog_and_image_results(monkeypatch, held_gui_call):
    monkeypatch.setattr(codex_auth, "logout", lambda: None)
    gui = Harness()
    hold = held_gui_call(codex_catalog, "list_text_models", [CodexModel("old", "Old", ("low",), "low", 1)])
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)
    gui.ping_codex_image_account()
    gui.codex_logout()
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui.jobs)
    assert gui.codex_model_combo.values == ("saved-custom",)
    assert gui.vars["INFINI_CODEX_LLM_MODEL"].get() == "saved-custom"
    assert "доступен" not in gui.codex_image_account_var.get()
    assert "удалена" in gui.status_var.get()


def test_codex_text_and_visual_controls_follow_llm_provider():
    gui = _SpriteGuiHarness()
    gui._refresh_visibility()
    assert gui.field_state["INFINI_CODEX_LLM_MODEL"][0] is False
    assert gui.field_state["INFINI_LLM_MAX_TOKENS"][0] is True
    assert gui.field_state["INFINI_LLM_TEMPERATURE"][0] is True
    gui.vars["INFINI_LLM_PROVIDER"].set("openai_codex")
    gui.vars["INFINI_IMAGE_BACKEND"].set("openai_codex")
    gui._refresh_visibility()
    assert gui.field_state["INFINI_CODEX_LLM_MODEL"][0] is True
    assert gui.field_state["INFINI_CODEX_VISUAL_REASONING"][0] is True
    assert gui.field_state["INFINI_CODEX_IMAGE_QUALITY"][0] is True
    assert gui.field_state["INFINI_LLM_MAX_TOKENS"][0] is False
    for key in ("INFINI_LLM_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", "INFINI_LLM_REASONING_EXCLUDE"):
        assert gui.field_state[key][0] is False, key
