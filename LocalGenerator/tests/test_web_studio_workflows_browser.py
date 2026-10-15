"""Real shipped frontend over HTTP, with local snapshot/action fixtures only.

No native controller, credentials, live model catalogs or provider calls are used.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest


@pytest.fixture
def browser_studio():
    browser_api = pytest.importorskip('playwright.sync_api')
    from infini_local.desktop.web_studio import StudioServer

    values = {'INFINI_LLM_PROVIDER': 'openai_codex', 'INFINI_CODEX_LLM_MODEL': 'fixture-model',
              'INFINI_LLM_REASONING_MODE': 'high', 'INFINI_CODEX_VISUAL_REASONING': 'inherit',
              'INFINI_TERRARIA_PORT': '7777', 'INFINI_PORT': '18875'}
    fields = [{'key': key, 'options': [], 'page': 'configure', 'advanced': False} for key in values]
    fields[1]['options'] = ['fixture-model']
    snapshot = {'values': values, 'defaults': {}, 'savedValues': values, 'savedRevision': 'disk-a',
                'savedLanEnabled': False, 'fields': fields, 'presets': {}, 'userPresets': {},
                'home': {}, 'busy': [], 'trace': {}, 'activity': '',
                'account': {'authenticated': False, 'textModels': {}}}
    server = StudioServer(Path(__file__).parents[1] / 'infini_local' / 'desktop' / 'webui')
    server.publish(snapshot)
    with browser_api.sync_playwright() as playwright:
        executable = os.environ.get('INFINI_TEST_BROWSER_EXECUTABLE') or playwright.chromium.executable_path
        if not Path(executable).is_file():
            server.close()
            pytest.skip('Frontend workflows need installed Chromium')
        server.start()
        browser = playwright.chromium.launch(headless=True, executable_path=executable)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            yield page, server, copy.deepcopy(snapshot)
            assert not errors
        finally:
            browser.close()
            server.close()


def finish_catalog(server, snapshot, command, *, ok=True):
    snapshot['fields'][1]['options'] = ['fixture-model', 'fixture-second']
    snapshot['account']['catalog'] = 'Fixture catalog ready' if ok else 'Fixture catalog unavailable'
    snapshot['actionResults'] = [{'id': command['id'], 'action': 'codexCatalog', 'ok': ok,
                                  'status': 'succeeded' if ok else 'failed',
                                  'message': snapshot['account']['catalog']}]
    server.publish(snapshot)


def test_model_refresh_restores_focus_without_stealing_newer_focus(browser_studio):
    page, server, snapshot = browser_studio
    page.goto(server.url + '#providers')
    refresh = page.locator('[data-action="codexCatalog"]')
    refresh.press('Enter')
    command = server.commands.get(timeout=3)
    assert command['action'] == 'codexCatalog'
    assert refresh.is_disabled()
    finish_catalog(server, snapshot, command)
    page.wait_for_function('() => !document.querySelector("[data-action=codexCatalog]").disabled')
    assert refresh.evaluate('(element) => element === document.activeElement'), 'Refresh lost keyboard focus after completion'
    assert page.locator('#field-INFINI_CODEX_LLM_MODEL').input_value() == 'fixture-model'

    # A later edit takes precedence over the older action's focus restoration.
    refresh.press('Enter')
    command = server.commands.get(timeout=3)
    model = page.locator('#field-INFINI_CODEX_LLM_MODEL')
    model.fill('my-newer-model')
    finish_catalog(server, snapshot, command, ok=False)
    page.wait_for_function('() => !document.querySelector("[data-action=codexCatalog]").disabled')
    assert model.evaluate('(element) => element === document.activeElement')
    assert model.input_value() == 'my-newer-model'
    assert page.locator('#toasts').inner_text().count('Fixture catalog unavailable') == 1
    page.locator('[data-ui="notifications"]').click()
    assert page.locator('.notification-history').inner_text().count('Fixture catalog unavailable') == 1
    page.keyboard.press('Escape')

    # Navigating elsewhere while waiting must not move focus back to the old route.
    refresh.click()
    command = server.commands.get(timeout=3)
    page.locator('[data-route="multiplayer"]').click()
    port = page.locator('#field-INFINI_TERRARIA_PORT')
    port.fill('7799')
    finish_catalog(server, snapshot, command)
    page.wait_for_function('() => !document.querySelector("[data-action=save]").disabled')
    assert port.evaluate('(element) => element === document.activeElement')
    assert page.locator('#save-tray').is_visible()


def test_stale_conflict_review_requires_reviewing_latest_disk(browser_studio):
    page, server, snapshot = browser_studio
    page.goto(server.url + '#multiplayer')
    port = page.locator('#field-INFINI_TERRARIA_PORT')
    port.fill('7799')
    snapshot['savedValues']['INFINI_TERRARIA_PORT'] = '7778'
    snapshot['savedRevision'] = 'disk-b'
    server.publish(snapshot)
    page.locator('[data-ui="review-conflict"]').click()
    assert 'На диске: 7778' in page.locator('#utility-body').inner_text()

    # Another writer saves again while the review is open. The clean port proves
    # that the browser has received this newer snapshot before the old approval.
    snapshot['savedValues']['INFINI_TERRARIA_PORT'] = '7780'
    snapshot['savedValues']['INFINI_PORT'] = '18877'
    snapshot['savedRevision'] = 'disk-c'
    server.publish(snapshot)
    page.wait_for_function('() => document.querySelector("#field-INFINI_PORT").value === "18877"')
    page.locator('#reconcile-draft').click()
    assert page.locator('#utility-dialog').is_visible(), 'Stale comparison was falsely acknowledged'
    assert 'На диске: 7780' in page.locator('#utility-body').inner_text()
    assert page.locator('#utility-dialog').evaluate('(element) => element.contains(document.activeElement)')
    assert port.input_value() == '7799'
    assert server.commands.empty(), 'Review must never write settings itself'
    page.locator('#reconcile-draft').click()
    assert not page.locator('#utility-dialog').is_visible()
    assert not page.locator('#draft-conflict').is_visible()
    page.locator('#save-tray [data-action="save"]').click()
    command = server.commands.get(timeout=3)
    assert command['extra']['savedRevision'] == 'disk-c'
    assert command['values']['INFINI_TERRARIA_PORT'] == '7799'
    assert command['values']['INFINI_PORT'] == '18877'


def test_prompt_reasoning_exclude_stays_inactive_after_unrelated_edit(browser_studio):
    page, server, snapshot = browser_studio
    values = dict(snapshot['values'], INFINI_LLM_PROVIDER='openrouter',
                  INFINI_LLM_REASONING_MODE='prompt_light', INFINI_LLM_REASONING_EXCLUDE='1')
    snapshot.update(values=values, savedValues=values)
    snapshot['fields'] = [{'key': key, 'options': [], 'page': 'configure', 'advanced': False,
                          'disabled': 'API reasoning only' if key == 'INFINI_LLM_REASONING_EXCLUDE' else ''}
                         for key in values]
    next(field for field in snapshot['fields'] if field['key'] == 'INFINI_LLM_REASONING_MODE')['options'] = ['prompt_light', 'high']
    server.publish(snapshot)
    page.goto(server.url + '#providers')
    row = page.locator('[data-field-row="INFINI_LLM_REASONING_EXCLUDE"]')
    # Inactive fields remain editable but are grouped and annotated honestly.
    expect = pytest.importorskip('playwright.sync_api').expect
    expect(row.locator('.field-note')).to_have_count(1)
    page.locator('[data-route="multiplayer"]').click()
    page.locator('#field-INFINI_PORT').fill('6060')
    page.locator('[data-route="providers"]').click()
    expect(row.locator('.field-note')).to_have_count(1)
    page.locator('#field-INFINI_LLM_REASONING_MODE').select_option('high')
    expect(row.locator('.field-note')).to_have_count(0)
    assert page.locator('#field-INFINI_LLM_REASONING_EXCLUDE').input_value() == '1'
