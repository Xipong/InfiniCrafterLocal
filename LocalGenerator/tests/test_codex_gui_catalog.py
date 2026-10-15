"""Read-only account catalog callbacks: saved choices, errors and retired results."""
from __future__ import annotations

import pytest

from infini_local.services import codex_auth, codex_catalog
from infini_local.services.codex_catalog import CodexModel
from test_settings_gui_contract import _GuiWorkflowHarness, _SpriteGuiHarness, held_gui_call


class Harness(_GuiWorkflowHarness):
    def __init__(self, config_path):
        super().__init__(config_path)
        self.values.update(INFINI_CODEX_LLM_MODEL='saved-custom', INFINI_LLM_REASONING_MODE='high', INFINI_CODEX_VISUAL_REASONING='inherit')
        self.codex_models = ['saved-custom']


@pytest.fixture
def catalog_studio(tmp_path):
    from infini_local.desktop.web_studio import StudioController, StudioServer

    gui = Harness(tmp_path / 'config.env')
    server = StudioServer(tmp_path)
    yield gui, StudioController(gui, server)
    gui.on_close()
    server.close()


def test_catalog_refresh_keeps_saved_model_and_unsupported_effort(catalog_studio, held_gui_call):
    gui, controller = catalog_studio
    models = [CodexModel("account-model", "Account", ("low", "medium", "ultra"), "low", 1)]
    hold = held_gui_call(codex_catalog, "list_text_models", models)
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)
    assert gui.codex_models == ["saved-custom"]
    hold.release.set()
    gui.drain_until(lambda: "account-model" in gui.codex_models)
    snapshot = controller.snapshot()
    model_field = next(row for row in snapshot['fields'] if row['key'] == 'INFINI_CODEX_LLM_MODEL')
    assert model_field['options'] == ['saved-custom', 'account-model']
    assert snapshot['values']["INFINI_CODEX_LLM_MODEL"] == "saved-custom"
    assert snapshot['account']['textModels'] == {'account-model': {'efforts': ['low', 'medium'], 'defaultEffort': 'low'}}
    gui.update_values({"INFINI_CODEX_LLM_MODEL": "account-model", "INFINI_CODEX_VISUAL_REASONING": "max"})
    selected = controller.snapshot()
    assert selected['values']["INFINI_CODEX_LLM_MODEL"] == "account-model"
    assert selected['values']["INFINI_LLM_REASONING_MODE"] == "high"
    assert selected['values']["INFINI_CODEX_VISUAL_REASONING"] == "max"
    assert selected['account']['textModels'] == snapshot['account']['textModels']
    gui.update_values({"INFINI_CODEX_LLM_MODEL": "manual-slug"})
    assert controller.snapshot()['values']["INFINI_CODEX_LLM_MODEL"] == "manual-slug"
    assert not gui.config_path.exists()


def test_failed_new_refresh_discards_held_old_success(tmp_path, monkeypatch, held_gui_call):
    gui = Harness(tmp_path / "config.env")
    hold = held_gui_call(codex_catalog, "list_text_models", [CodexModel("old", "Old", ("low",), "low", 1)])
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)

    def failed():
        raise RuntimeError("FAKE-SECRET-CANARY")

    monkeypatch.setattr(codex_catalog, "list_text_models", failed)
    gui.refresh_codex_text_catalog()
    hold.release.set()
    gui.drain_until(lambda: "не удалось" in gui.codex_catalog.lower())
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui._scheduled_ids)
    assert gui.codex_models == ["saved-custom"]
    assert gui.values["INFINI_CODEX_LLM_MODEL"] == "saved-custom"
    assert "CANARY" not in gui.codex_catalog + gui.status


def test_image_ping_is_read_only_and_does_not_claim_image_entitlement(tmp_path, held_gui_call):
    gui = Harness(tmp_path / "config.env")
    hold = held_gui_call(codex_catalog, "list_text_models", [])
    gui.ping_codex_image_account()
    assert hold.entered.wait(1)
    hold.release.set()
    gui.drain_until(lambda: not gui._scheduled_ids)
    assert len(hold.calls) == 1
    assert gui.codex_models == ["saved-custom"]
    assert "image-доступ не проверен" in gui.codex_image_account
    assert "image-доступ не проверен" in gui.status


def test_logout_discards_pending_catalog_and_image_results(tmp_path, monkeypatch, held_gui_call):
    monkeypatch.setattr(codex_auth, "logout", lambda: None)
    gui = Harness(tmp_path / "config.env")
    hold = held_gui_call(codex_catalog, "list_text_models", [CodexModel("old", "Old", ("low",), "low", 1)])
    gui.refresh_codex_text_catalog()
    assert hold.entered.wait(1)
    gui.ping_codex_image_account()
    gui.codex_logout()
    hold.release.set()
    assert hold.finished.wait(1)
    gui.drain_until(lambda: not gui._scheduled_ids)
    assert gui.codex_models == ["saved-custom"]
    assert gui.values["INFINI_CODEX_LLM_MODEL"] == "saved-custom"
    assert "доступен" not in gui.codex_image_account
    assert "удалена" in gui.status


def test_codex_text_and_visual_controls_follow_llm_provider(tmp_path):
    gui = _SpriteGuiHarness(tmp_path / "config.env")
    gui._refresh_visibility()
    assert (not gui.field_disabled_reasons.get("INFINI_CODEX_LLM_MODEL")) is False
    assert (not gui.field_disabled_reasons.get("INFINI_LLM_MAX_TOKENS")) is True
    assert (not gui.field_disabled_reasons.get("INFINI_LLM_TEMPERATURE")) is True
    gui.update_values({"INFINI_LLM_PROVIDER": "openai_codex"})
    gui.update_values({"INFINI_IMAGE_BACKEND": "openai_codex"})
    gui._refresh_visibility()
    assert (not gui.field_disabled_reasons.get("INFINI_CODEX_LLM_MODEL")) is True
    assert (not gui.field_disabled_reasons.get("INFINI_CODEX_VISUAL_REASONING")) is True
    assert (not gui.field_disabled_reasons.get("INFINI_CODEX_IMAGE_QUALITY")) is True
    assert (not gui.field_disabled_reasons.get("INFINI_LLM_MAX_TOKENS")) is False
    for key in ("INFINI_LLM_TEMPERATURE", "INFINI_LLM_REAUTHOR_TEMPERATURE", "INFINI_VISUAL_DIRECTOR_TEMPERATURE", "INFINI_LLM_REASONING_EXCLUDE"):
        assert (not gui.field_disabled_reasons.get(key)) is False, key
