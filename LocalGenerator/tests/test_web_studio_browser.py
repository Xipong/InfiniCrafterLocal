"""Optional real-browser regression: delayed POST acknowledgements versus draft state.

Requires Tk/display and Playwright Chromium; ordinary headless pytest skips this
integration while HTTP/controller coverage remains in test_web_studio.py.
"""
from __future__ import annotations

import threading
import time
import traceback

import pytest


def test_delayed_save_and_transform_ack_never_hide_unsaved_draft(tmp_path, monkeypatch):
    from infini_local.desktop.tk_compat import TKINTER_AVAILABLE, tk
    if not TKINTER_AVAILABLE:
        pytest.skip('Browser integration needs native Tk and a display')
    browser_api = pytest.importorskip('playwright.sync_api')
    browser_executable = None
    with browser_api.sync_playwright() as browser_probe:
        from pathlib import Path
        if not Path(browser_probe.chromium.executable_path).exists():
            candidates = sorted((Path.home() / '.cache/ms-playwright').glob('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell'))
            if not candidates:
                pytest.skip('Browser integration needs installed Playwright Chromium')
            browser_executable = str(candidates[-1])
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip('Browser integration needs a display')
    from infini_local.desktop import settings_gui, settings_gui_trace_state, settings_gui_server_controls
    from infini_local.desktop.settings_env import write_env, parse_env
    from infini_local.desktop.web_studio import StudioServer, StudioController
    from pathlib import Path
    config = tmp_path / 'config.env'
    write_env(config, {'INFINI_USE_LLM':'0', 'INFINI_IMAGE_BACKEND':'off',
                      'INFINI_SDCPP_SERVER_AUTOSTART':'0', 'INFINI_HOST':'127.0.0.1',
                      'INFINI_MP_ASSET_TRANSPORT':'native', 'INFINI_PRIVATE_UNKNOWN':'retained',
                      'INFINI_CACHE_DIR':str(tmp_path / 'cache'),
                      'INFINI_SPRITE_DOWNSCALE_FILTER':'bilinear',
                      'INFINI_SPRITE_PREMULTIPLIED_RESIZE':'0'})
    for owner in (settings_gui, settings_gui_trace_state, settings_gui_server_controls):
        monkeypatch.setattr(owner, 'CONFIG_PATH', config)
    app = settings_gui.SettingsGui()
    app.withdraw()
    server = StudioServer(Path(settings_gui.__file__).with_name('webui'))
    controller = StudioController(app, server)
    server.publish(controller.snapshot())
    server.start()
    done = threading.Event()
    errors = []

    def browser_work():
        try:
            with browser_api.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=browser_executable)
                try:
                    page = browser.new_page(viewport={'width':1440, 'height':1000})
                    page.goto(server.url + '#configure')
                    page.wait_for_selector('#preset-select')
                    page.locator('details[data-details="all-settings"]').evaluate('(e)=>e.open=true')
                    cache = str(tmp_path / 'new-cache')
                    page.locator('#field-INFINI_CACHE_DIR').fill(cache)
                    page.locator('#save-tray [data-action="save"]').click()
                    page.locator('#save-tray').wait_for(state='hidden', timeout=8000)
                    assert parse_env(config)['INFINI_CACHE_DIR'] == cache
                    # Hold the real response after the server has handled the request.
                    # A later LAN edit must not become the saved baseline.
                    page.locator('[data-route="multiplayer"]').click()
                    page.locator('#field-INFINI_TERRARIA_PORT').fill('7799')
                    def delayed_save(route):
                        response = route.fetch()
                        page.wait_for_timeout(1200)
                        route.fulfill(response=response)
                    page.route('**/api/action', delayed_save)
                    page.evaluate('()=>{setTimeout(()=>document.querySelector("#lan-enabled").click(),250);document.querySelector("#save-tray [data-action=save]").click();}')
                    page.wait_for_timeout(2600)
                    assert page.locator('#lan-enabled').is_checked()
                    assert page.locator('#save-tray').is_visible(), 'LAN edit after submit was falsely acknowledged as saved'
                    page.unroute('**/api/action', delayed_save)
                    # Save the pending LAN choice, so the next dirty state is reset-only.
                    page.locator('#save-tray [data-action="save"]').click()
                    page.locator('#save-tray').wait_for(state='hidden', timeout=8000)
                    page.locator('[data-route="sprites"]').click()
                    def delayed_transform(route):
                        response = route.fetch()
                        page.wait_for_timeout(3000)
                        route.fulfill(response=response)
                    page.route('**/api/action', delayed_transform)
                    page.locator('[data-ui="reset-sprite"]').click()
                    page.locator('#confirm-submit').click()
                    page.wait_for_timeout(4600)
                    assert page.locator('#field-INFINI_SPRITE_DOWNSCALE_FILTER').input_value() == 'box'
                    assert parse_env(config)['INFINI_SPRITE_DOWNSCALE_FILTER'] == 'bilinear'
                    assert page.locator('#save-tray').is_visible(), 'Pre-ack poll absorbed a prepared transform into disk baseline'
                    assert parse_env(config)['INFINI_PRIVATE_UNKNOWN'] == 'retained'
                finally:
                    browser.close()
        except Exception:
            errors.append(traceback.format_exc())
        finally:
            done.set()

    worker = threading.Thread(target=browser_work, daemon=True)
    worker.start()
    deadline = time.monotonic() + 45
    def finish():
        if done.is_set() or time.monotonic() > deadline:
            app.quit()
        else:
            app.after(50, finish)
    app.after(0, controller.tick)
    app.after(50, finish)
    try:
        app.mainloop()
    finally:
        server.close()
        app.destroy()
        worker.join(timeout=3)
    assert done.is_set(), 'Browser integration exceeded its bounded deadline'
    assert not errors, '\n'.join(errors)


def test_studio_frontend_credentials_search_and_mobile_focus(tmp_path):
    """Real frontend/HTTP with explicit snapshot fixture, independent of native Tk.

    This verifies browser interactions, not native controller or model readiness.
    Set INFINI_TEST_BROWSER_EXECUTABLE to an installed Chromium when needed.
    """
    import os
    from pathlib import Path
    from infini_local.desktop.web_studio import StudioServer
    browser_api = pytest.importorskip('playwright.sync_api')
    values = {'INFINI_LLM_MAX_TOKENS': '6000', 'INFINI_EXTENSION_SECRET': 'secret-fixture',
              'INFINI_EXTENSION_CREDENTIAL': 'credential-fixture', 'INFINI_LLM_PROVIDER': 'local'}
    fields = [{'key': key, 'options': [], 'page': 'configure', 'advanced': False} for key in values]
    assets = Path(__file__).parents[1] / 'infini_local' / 'desktop' / 'webui'
    server = StudioServer(assets)
    snapshot = {'values': values, 'defaults': values, 'savedValues': values,
                'savedLanEnabled': False, 'fields': fields, 'presets': {},
                'userPresets': {}, 'home': {}, 'busy': [], 'trace': {}, 'activity': ''}
    server.publish(snapshot)
    with browser_api.sync_playwright() as playwright:
        executable = os.environ.get('INFINI_TEST_BROWSER_EXECUTABLE') or playwright.chromium.executable_path
        if not Path(executable).is_file():
            server.close()
            pytest.skip('Frontend integration needs installed Playwright Chromium')
        server.start()
        browser = None
        try:
            browser = playwright.chromium.launch(headless=True, executable_path=executable)
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(server.url + '#configure')
            page.wait_for_selector('#preset-select')
            page.locator('details[data-details="all-settings"]').evaluate('(element)=>element.open=true')
            assert page.locator('#field-INFINI_LLM_MAX_TOKENS').get_attribute('type') == 'text'
            assert page.locator('#field-INFINI_EXTENSION_SECRET').get_attribute('type') == 'password'
            assert page.locator('#field-INFINI_EXTENSION_CREDENTIAL').get_attribute('type') == 'password'
            page.locator('[data-ui="search"]').click()
            close = page.locator('#search-dialog [data-ui="close-dialog"]')
            close.focus()
            page.keyboard.press('Enter')
            assert not page.locator('#search-dialog').is_visible()
            assert page.url.endswith('#configure'), 'Enter on Close navigated to an unrelated result'
            page.locator('[data-route="operate"]').click()
            health = page.locator('[data-action="health"]')
            health.focus()
            snapshot['home'] = {'state': 'Сервер отвечает'}
            server.publish(snapshot)
            page.wait_for_function('() => document.querySelector("#generator-title").textContent === "Сервер отвечает"')
            assert health.evaluate('(element)=>element===document.activeElement'), 'Polling lost action focus'
            page.set_viewport_size({'width': 390, 'height': 844})
            menu = page.locator('.mobile-menu')
            menu.click()
            assert page.locator('.main-shell').evaluate('(element)=>element.inert')
            assert page.locator('.rail').get_attribute('aria-modal') == 'true'
            snapshot['home'] = {'state': 'Идёт генерация'}
            server.publish(snapshot)
            page.wait_for_function('() => document.querySelector("#generator-title").textContent === "Идёт генерация"')
            assert page.locator('.nav-link.active').evaluate('(element)=>element===document.activeElement'), 'Polling stole drawer focus'
            assert page.locator('.main-shell').evaluate('(element)=>element.inert')
            page.locator('.mobile-exit').focus()
            page.keyboard.press('Tab')
            assert page.locator('.drawer-close').evaluate('(element)=>element===document.activeElement')
            page.keyboard.press('Escape')
            assert not page.locator('.main-shell').evaluate('(element)=>element.inert')
            assert menu.evaluate('(element)=>element===document.activeElement')
            menu.click()
            page.locator('.nav-link.active').click()
            assert not page.locator('.main-shell').evaluate('(element)=>element.inert')
            assert page.locator('#workspace').evaluate('(element)=>element===document.activeElement')
            menu.click()
            page.set_viewport_size({'width': 1440, 'height': 1000})
            page.wait_for_function('() => !document.querySelector(".main-shell").inert')
            assert not page.locator('#navigation-backdrop').is_visible()
            assert not errors
        finally:
            if browser:
                browser.close()
            server.close()
