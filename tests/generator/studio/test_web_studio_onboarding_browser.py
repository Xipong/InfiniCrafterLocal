"""First-run guide over the real HTTP bridge and controller, without provider calls."""
from __future__ import annotations

import os
from pathlib import Path
import threading

import pytest
from suite_paths import GENERATOR_ROOT


@pytest.fixture
def onboarding_browser(tmp_path, monkeypatch):
    browser_api = pytest.importorskip('playwright.sync_api')
    from infini_local.desktop.settings_controller import SettingsController
    from infini_local.desktop.settings_env import write_env
    from infini_local.desktop.web_studio import StudioController, StudioServer
    from infini_local.services import codex_auth
    monkeypatch.setattr(codex_auth, 'auth_status', lambda: {'authenticated': False})
    config = tmp_path / 'config.env'
    write_env(config, {'INFINI_USE_LLM': '0', 'INFINI_IMAGE_BACKEND': 'off',
                      'INFINI_SDCPP_SERVER_AUTOSTART': '0', 'INFINI_HOST': '127.0.0.1',
                      'INFINI_LLM_PROVIDER': 'openai_compat', 'INFINI_LANGUAGE': 'ru',
                      'INFINI_OPENAI_COMPAT_API_KEY': 'fixture-secret-never-copy',
                      'INFINI_CACHE_DIR': str(tmp_path / 'cache')})
    original = config.read_bytes()
    app = SettingsController(config_path=config)
    server = StudioServer(GENERATOR_ROOT / 'infini_local' / 'desktop' / 'webui')
    controller = StudioController(app, server)
    server.publish(controller.snapshot())
    done = threading.Event()
    failures = []
    def pump():
        try:
            app.after(0, controller.tick)
            while not done.is_set():
                app.pump()
                done.wait(.01)
        except Exception as error:
            failures.append(error)
    with browser_api.sync_playwright() as playwright:
        executable = os.environ.get('INFINI_TEST_BROWSER_EXECUTABLE') or playwright.chromium.executable_path
        if not Path(executable).is_file():
            server.close()
            pytest.skip('First-run guide tests need installed Chromium')
        try:
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
        except Exception:
            server.close()
            app.on_close()
            raise
        server.start()
        worker = threading.Thread(target=pump, daemon=True)
        worker.start()
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.post_data_json) if request.method == 'POST' else None)
        try:
            yield page, server, config, original, requests
            assert not errors
            assert config.read_bytes() == original, 'Help must not save generator settings'
        finally:
            browser.close()
            done.set()
            worker.join(timeout=3)
            server.close()
            app.on_close()
        assert not worker.is_alive()
        assert not failures


def wait_progress(page, **expected):
    page.wait_for_function('''async expected => {
      const state = await fetch('/api/state', {headers:{'X-Infini-Token':window.INFINI_BOOTSTRAP.token}}).then(r=>r.json());
      return Object.entries(expected).every(([key,value])=>state.onboarding[key] === value);
    }''', arg=expected)


def test_first_visit_resume_completion_and_new_origin(onboarding_browser):
    from infini_local.desktop.studio_onboarding import load_progress
    from infini_local.desktop.web_studio import StudioServer
    page, server, config, original, requests = onboarding_browser
    page.goto(server.url)
    page.locator('#onboarding-dialog').wait_for(state='visible')
    assert page.locator('#onboarding-title').inner_text() == 'Твоя идея. Новый предмет.'
    assert page.locator('#onboarding-title').evaluate('(e)=>document.activeElement===e')
    wait_progress(page, seen=True)
    page.locator('[data-onboarding-next]').click()
    assert 'мозг' in page.locator('#onboarding-title').inner_text()
    assert page.locator('a[href="https://openrouter.ai/google/gemma-4-31b-it:free"]').count() == 1
    page.locator('[data-onboarding-next]').click()
    wait_progress(page, step=2)
    page.keyboard.press('Escape')
    page.locator('#onboarding-dialog').wait_for(state='hidden')
    page.reload()
    page.locator('#onboarding-launcher:not(:disabled)').wait_for()
    assert not page.locator('#onboarding-dialog').is_visible()
    page.locator('#onboarding-launcher').click()
    assert 'характер' in page.locator('#onboarding-title').inner_text()
    page.locator('[data-onboarding-step="4"]').click()
    page.locator('[data-onboarding-next]').click()
    wait_progress(page, step=4, completed=True)
    assert not page.locator('#onboarding-dialog').is_visible()
    assert requests and all(r['action'] == 'onboardingProgress' and r['values'] == {} for r in requests)
    assert all('fixture-secret' not in str(r) for r in requests)
    # A new launch port is a different browser origin; progress is still persisted.
    other = StudioServer(GENERATOR_ROOT / 'infini_local' / 'desktop' / 'webui')
    snapshot = page.evaluate("async()=>fetch('/api/state',{headers:{'X-Infini-Token':window.INFINI_BOOTSTRAP.token}}).then(r=>r.json())")
    snapshot['onboarding'] = load_progress(config)
    other.publish(snapshot)
    other.start()
    try:
        page.goto(other.url)
        page.locator('#onboarding-launcher:not(:disabled)').wait_for()
        assert not page.locator('#onboarding-dialog').is_visible()
    finally:
        other.close()


def test_navigation_draft_keyboard_and_localization(onboarding_browser):
    page, server, config, original, requests = onboarding_browser
    page.goto(server.url + '#providers')
    page.locator('#onboarding-dialog').wait_for(state='visible')
    page.keyboard.press('Escape')
    page.locator('#field-INFINI_LLM_TEMPERATURE').fill('0.65')
    assert page.locator('#save-tray').is_visible()
    page.locator('#onboarding-launcher').click()
    page.locator('[data-onboarding-step="1"]').click()
    page.locator('[data-onboarding-field="INFINI_LLM_PROVIDER"]').click()
    page.locator('#onboarding-dialog').wait_for(state='hidden')
    assert page.locator('#field-INFINI_LLM_TEMPERATURE').input_value() == '0.65'
    assert page.locator('#save-tray').is_visible()
    page.locator('#language-select').select_option('en')
    page.locator('#onboarding-launcher').click()
    assert page.locator('#onboarding-title').inner_text() == 'Choose the creative brain'
    page.keyboard.press('Escape')
    assert page.locator('#onboarding-launcher').evaluate('(e)=>document.activeElement===e')
    page.locator('#onboarding-launcher').click()
    # Browser history/navigation dismisses the guide and leaves a coherent route.
    page.evaluate("location.hash='images'")
    page.locator('#onboarding-dialog').wait_for(state='hidden')
    page.wait_for_function("()=>document.body.dataset.page==='images'")
    assert page.locator('#save-tray').is_visible()


def test_mobile_steps_no_overflow_and_external_links_safe(onboarding_browser):
    page, server, config, original, requests = onboarding_browser
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(server.url)
    page.locator('#onboarding-dialog').wait_for(state='visible')
    for index in range(5):
        page.locator(f'[data-onboarding-step="{index}"]').click()
        assert page.locator('#onboarding-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
        assert page.locator('.onboarding-content').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
        assert page.locator('[data-onboarding-next]').evaluate('(e)=>{const r=e.getBoundingClientRect();return r.top>=0 && r.bottom<=innerHeight;}')
        assert page.locator('#onboarding-dialog').evaluate("e=>[...e.querySelectorAll('a')].every(a=>a.protocol==='https:' && a.rel.includes('noreferrer') && a.rel.includes('noopener'))")
        assert 'fixture-secret-never-copy' not in page.locator('#onboarding-dialog').inner_text()
    page.keyboard.press('Escape')
    page.locator('#onboarding-launcher').click()
    page.keyboard.press('Tab')
    assert page.locator('#onboarding-dialog').evaluate('(e)=>e.contains(document.activeElement)')
