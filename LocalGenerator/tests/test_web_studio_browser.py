"""Optional real-browser regression: delayed POST acknowledgements versus draft state.

Requires Tk/display and Playwright Chromium; ordinary headless pytest skips this
integration while HTTP/controller coverage remains in test_web_studio.py.
"""
from __future__ import annotations

import os
import threading
import time
import traceback

import pytest


def test_delayed_save_and_transform_ack_never_hide_unsaved_draft(tmp_path, monkeypatch):
    from infini_local.desktop.tk_compat import TKINTER_AVAILABLE, tk
    if not TKINTER_AVAILABLE:
        pytest.skip('Browser integration needs native Tk and a display')
    browser_api = pytest.importorskip('playwright.sync_api')
    browser_executable = os.environ.get('INFINI_TEST_BROWSER_EXECUTABLE')
    with browser_api.sync_playwright() as browser_probe:
        from pathlib import Path
        if not Path(browser_executable or browser_probe.chromium.executable_path).exists():
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


def test_real_studio_defaults_consent_dismissal_and_delayed_accept(tmp_path, monkeypatch):
    from pathlib import Path
    from infini_local.desktop.tk_compat import TKINTER_AVAILABLE, tk
    if not TKINTER_AVAILABLE:
        pytest.skip('Defaults integration needs native Tk')
    browser_api = pytest.importorskip('playwright.sync_api')
    with browser_api.sync_playwright() as probe_browser:
        executable = os.environ.get('INFINI_TEST_BROWSER_EXECUTABLE') or probe_browser.chromium.executable_path
        if not Path(executable).exists():
            candidates = sorted((Path.home() / '.cache/ms-playwright').glob('chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell'))
            if not candidates:
                pytest.skip('Defaults integration needs installed Chromium')
            executable = str(candidates[-1])
    try:
        probe = tk.Tk()
        probe.destroy()
    except tk.TclError:
        pytest.skip('Defaults integration needs a display')
    from infini_local.desktop import settings_gui, settings_gui_trace_state, settings_gui_server_controls
    from infini_local.desktop.settings_schema import DEFAULTS
    from infini_local.desktop.settings_env import parse_env
    from infini_local.desktop.web_studio import StudioServer, StudioController
    monkeypatch.setitem(DEFAULTS, 'INFINI_LLM_MAX_TOKENS', '18000')
    config = tmp_path / 'config.env'
    original = (b'# consent browser proof\r\nINFINI_LLM_MAX_TOKENS=9000\r\n'
                b'INFINI_USE_LLM=0\r\nINFINI_IMAGE_BACKEND=off\r\nINFINI_SDCPP_SERVER_AUTOSTART=0\r\n'
                b'INFINI_LLM_PROVIDER=local\r\nINFINI_PRIVATE_UNKNOWN=retained\r\n'
                b'INFINI_OPENAI_COMPAT_API_KEY=opaque-test-key\r\nINFINI_SDCPP_MODEL=C:\\Models\\keep.gguf\r\n'
                b'INFINI_HOST=127.0.0.1\r\nINFINI_CACHE_DIR=' + str(tmp_path / 'cache').encode() + b'\r\n')
    config.write_bytes(original)
    for owner in (settings_gui, settings_gui_trace_state, settings_gui_server_controls):
        monkeypatch.setattr(owner, 'CONFIG_PATH', config)
    app = settings_gui.SettingsGui()
    app.withdraw()
    def forbidden(*_args, **_kwargs):
        raise AssertionError('Defaults consent must never call generic save/collect')
    monkeypatch.setattr(app, 'save', forbidden)
    monkeypatch.setattr(app, 'collect', forbidden)
    server = StudioServer(Path(settings_gui.__file__).with_name('webui'))
    controller = StudioController(app, server)
    expected_offer = controller.snapshot()['defaultsUpdate']
    server.publish(controller.snapshot())
    server.start()
    done, errors = threading.Event(), []

    def browser_work():
        try:
            with browser_api.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, executable_path=executable)
                try:
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page_errors, decisions = [], []
                    page.on('pageerror', lambda error: page_errors.append(str(error)))
                    page.on('request', lambda request: decisions.append(request.post_data_json) if request.method == 'POST' else None)
                    page.goto(server.url + '#configure')
                    page.wait_for_selector('#defaults-changes', timeout=8000)
                    row = page.locator('[data-defaults-key="INFINI_LLM_MAX_TOKENS"]')
                    assert row.count() == 1
                    for text in ('INFINI_LLM_MAX_TOKENS', '9000', '18000', expected_offer['changes'][0]['reason']):
                        assert text in row.inner_text()
                    assert config.read_bytes() == original
                    page.set_viewport_size({'width': 390, 'height': 844})
                    assert page.locator('#utility-dialog').evaluate('(e)=>e.scrollWidth <= e.clientWidth'), 'Consent modal overflows a narrow screen'
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    page.keyboard.press('Escape')
                    page.locator('details[data-details="all-settings"]').evaluate('(e)=>e.open=true')
                    page.locator('#field-INFINI_PRIVATE_UNKNOWN').fill('unsaved-before-decline')
                    page.locator('[data-ui="defaults-update"]').click()
                    page.locator('#defaults-decline').click()
                    page.locator('#utility-dialog').wait_for(state='hidden', timeout=8000)
                    assert config.read_bytes() == original
                    assert page.locator('#field-INFINI_PRIVATE_UNKNOWN').input_value() == 'unsaved-before-decline'
                    assert decisions[-1]['values'] == {}
                    assert decisions[-1]['extra'] == {'revision': expected_offer['revision']}
                    # A new tab obeys the persisted dismissal; manual reopening still works.
                    page.close(run_before_unload=False)
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.on('pageerror', lambda error: page_errors.append(str(error)))
                    page.on('request', lambda request: decisions.append(request.post_data_json) if request.method == 'POST' else None)
                    page.goto(server.url + '#configure')
                    page.wait_for_selector('[data-ui="defaults-update"]')
                    assert not page.locator('#utility-dialog').is_visible()
                    page.locator('details[data-details="all-settings"]').evaluate('(e)=>e.open=true')
                    page.locator('#field-INFINI_PRIVATE_UNKNOWN').fill('unsaved-other-key')
                    page.locator('#field-INFINI_LLM_MAX_TOKENS').fill('15000')
                    page.locator('[data-ui="defaults-update"]').click()
                    assert page.locator('#defaults-changes').is_visible()
                    # Change disk after preview: old consent must fail and stay open.
                    config.write_bytes(original + b'# external edit\r\n')
                    page.locator('#defaults-accept').click()
                    page.wait_for_function('() => document.querySelector("#defaults-error")?.textContent.length > 0')
                    assert page.locator('#utility-dialog').is_visible()
                    assert parse_env(config)['INFINI_LLM_MAX_TOKENS'] == '9000'
                    page.locator('#defaults-refresh').click()
                    page.wait_for_function('() => document.querySelector("#defaults-error")?.hidden === true')
                    page.locator('#defaults-accept').wait_for(state='visible')
                    def delayed_accept(route):
                        response = route.fetch()
                        page.wait_for_timeout(2200)
                        route.fulfill(response=response)
                    page.route('**/api/action', delayed_accept)
                    page.evaluate('''()=>{
                        setTimeout(()=>{
                            for (const [key,value] of [['INFINI_LLM_MAX_TOKENS','19000'],['INFINI_PRIVATE_UNKNOWN','newer-other-key']]) {
                                const input=document.querySelector('#field-'+key);input.value=value;
                                input.dispatchEvent(new Event('input',{bubbles:true}));
                            }
                        },250);
                        document.querySelector('#defaults-accept').click();
                    }''')
                    # A submitted decision stays visible until its acknowledgement.
                    page.keyboard.press('Escape')
                    assert page.locator('#utility-dialog').is_visible(), 'Queued consent closed before acknowledgement'
                    page.locator('#utility-dialog').wait_for(state='hidden', timeout=10000)
                    assert decisions[-1]['action'] == 'acceptDefaults'
                    assert decisions[-1]['values'] == {}
                    assert set(decisions[-1]['extra']) == {'revision'}
                    page.wait_for_timeout(1600)
                    assert page.locator('#field-INFINI_LLM_MAX_TOKENS').input_value() == '19000'
                    assert page.locator('#field-INFINI_PRIVATE_UNKNOWN').input_value() == 'newer-other-key'
                    assert page.locator('#save-tray').is_visible()
                    assert config.read_bytes() == original.replace(b'9000', b'18000') + b'# external edit\r\n'
                    assert not page_errors
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
    assert done.is_set(), 'Defaults integration exceeded deadline'
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
