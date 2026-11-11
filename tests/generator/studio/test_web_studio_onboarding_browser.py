"""First-run guide over the real HTTP bridge and controller, without provider calls."""
from __future__ import annotations

import os
from pathlib import Path
import threading
import time

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
    # wait_for_function treats an async predicate's Promise as truthy before its
    # resolved value is checked. Await each read so reload cannot race the save.
    deadline = time.monotonic() + 10
    while True:
        actual = page.evaluate('''async () => {
          const state = await fetch('/api/state', {headers:{'X-Infini-Token':window.INFINI_BOOTSTRAP.token}}).then(r=>r.json());
          return state.onboarding;
        }''')
        if all(actual.get(key) == value for key, value in expected.items()):
            return
        if time.monotonic() >= deadline:
            pytest.fail(f'Onboarding progress did not reach {expected}: {actual}')
        page.wait_for_timeout(20)


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
    assert page.locator('a[href="https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free"]').count() == 1
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


@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
@pytest.mark.parametrize('color_scheme', ['light', 'dark'])
def test_current_step_keeps_readable_hover_and_keyboard_focus(onboarding_browser, viewport, color_scheme):
    page, server, config, original, requests = onboarding_browser
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    page.emulate_media(color_scheme=color_scheme)
    page.goto(server.url)
    current = page.locator('[data-onboarding-step="0"]')
    current.click()
    assert current.get_attribute('aria-current') == 'step'

    def contrast():
        return current.evaluate(r"""button => {
          const color = value => value.match(/[\d.]+/g).slice(0, 3).map(Number);
          const bg = color(getComputedStyle(button).backgroundColor);
          const label = button.querySelector('span');
          const style = getComputedStyle(label);
          const opacity = Number(style.opacity);
          const fg = color(style.color).map((c, i) => c * opacity + bg[i] * (1 - opacity));
          const luminance = rgb => rgb.map(c => {
            c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          }).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
          const a = luminance(fg), b = luminance(bg);
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        }""")

    # Re-establish hover after any asynchronous localized render.
    current.hover()
    assert current.evaluate("e => e.matches(':hover')")
    assert contrast() >= 4.5
    page.mouse.move(0, 0)
    page.locator('.onboarding-top [data-onboarding-close]').focus()
    page.keyboard.press('Tab')
    assert current.evaluate("e => document.activeElement === e && e.matches(':focus-visible')")
    assert current.evaluate("e => getComputedStyle(e).outlineStyle !== 'none'")
    assert contrast() >= 4.5
    page.keyboard.press('Enter')
    assert page.locator('#onboarding-title').inner_text() == 'Твоя идея. Новый предмет.'


@pytest.mark.parametrize('language', ['ru', 'en'])
def test_model_guidance_recommends_current_models_and_accurate_setup(onboarding_browser, language):
    page, server, config, original, requests = onboarding_browser
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(server.url)
    page.locator('#onboarding-dialog').wait_for(state='visible')
    page.keyboard.press('Escape')
    page.locator('#language-select').select_option(language)
    page.locator('#onboarding-launcher').click()
    page.locator('[data-onboarding-step="0"]').click()
    welcome = page.locator('#onboarding-dialog').inner_text()
    assert ('Доступный старт' if language == 'ru' else 'Accessible start') in welcome
    assert ('Более сильные модели' if language == 'ru' else 'Stronger models') in welcome
    assert 'VPN' in welcome and 'Google AI Studio' in welcome and 'OpenRouter' in welcome
    assert ('запрещает обход' if language == 'ru' else 'prohibits bypassing') in welcome
    assert page.locator('a[href="https://openrouter.ai/terms"]').count() == 1
    page.locator('[data-onboarding-step="1"]').click()
    text = page.locator('#onboarding-dialog').inner_text()
    assert ('БЕСПЛАТНЫЙ СТАРТ' if language == 'ru' else 'FREE START') in text
    assert ('Более сильный автор механики' if language == 'ru' else 'A stronger mechanics author') in text
    assert 'ChatGPT / Codex' in text
    assert 'NVIDIA Nemotron 3.5 Super VL' in text
    assert 'Gemma' not in text and 'XingChen' not in text
    assert page.locator('a[href="https://openrouter.ai/nvidia/nemotron-3.5-super-vl:free"]').count() == 1
    assert ('бесплатных и платных' if language == 'ru' else 'free and paid') in text
    assert ('не гарантируют качество' if language == 'ru' else 'do not guarantee quality') in text
    page.locator('[data-onboarding-step="2"]').click()
    images = page.locator('#onboarding-dialog').inner_text()
    assert ('РЕКОМЕНДУЕМ ЛОКАЛЬНО' if language == 'ru' else 'RECOMMENDED LOCAL MODEL') in images
    assert page.locator('.onboarding-feature h3').inner_text() == 'Microsoft Mage-Flow Turbo'
    assert 'gpt-image-2' in images and 'medium' in images
    assert 'high' not in images
    assert 'Qwen3-VL' in images and 'VAE' in images and 'sd.cpp' in images
    assert ('Доступ зависит от аккаунта' if language == 'ru' else 'Access depends on your account') in images
    assert 'нет готового встроенного подключения' not in images and 'no built-in Studio integration' not in images
    assert '2.5' not in images and '2.6' not in images
    assert 'BEST FOR' not in images and 'ЛУЧШЕ ДЛЯ' not in images
    assert page.locator('#onboarding-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    assert page.locator('.onboarding-content').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    page.locator('[data-onboarding-step="3"]').click()
    setup = page.locator('#onboarding-dialog').inner_text()
    assert 'Mage-Flow Turbo' in setup and 'Qwen3-VL' in setup and 'VAE' in setup
    assert 'nvidia/nemotron-3.5-super-vl:free' in setup
    assert page.locator('[data-onboarding-copy="nvidia/nemotron-3.5-super-vl:free"]').count() == 1
    assert page.locator('.onboarding-content').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    page.locator('[data-onboarding-step="2"]').click()
    page.locator('[data-onboarding-field="INFINI_IMAGE_BACKEND"]').click()
    page.locator('#onboarding-dialog').wait_for(state='hidden')
    assert page.locator('#field-INFINI_IMAGE_BACKEND').evaluate('(e)=>document.activeElement===e')
    assert all(r['action'] == 'onboardingProgress' and r['values'] == {} for r in requests)
