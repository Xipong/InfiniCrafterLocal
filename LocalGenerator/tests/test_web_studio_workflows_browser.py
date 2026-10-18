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


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 1000}, {'width': 390, 'height': 844}])
def test_draft_status_tracks_edits_save_receipt_and_lan_without_losing_focus(browser_studio, viewport):
    page, server, snapshot = browser_studio
    expect = pytest.importorskip('playwright.sync_api').expect
    page.set_viewport_size(viewport)
    page.goto(server.url + '#multiplayer')
    status = page.locator('[data-draft-status]')
    count = page.locator('[data-dirty-count]')
    tray = page.locator('#save-tray')
    port = page.locator('#field-INFINI_TERRARIA_PORT')
    expect(status).to_have_text('Локальная конфигурация')
    expect(count).to_have_text('Изменений нет')
    expect(tray).to_be_hidden()
    original_port = port.element_handle()
    original_status = status.element_handle()

    port.fill('7799')
    expect(status).to_have_text('Черновик / Не сохранён')
    expect(count).to_have_text('1 несохранённых изменений')
    expect(tray).to_be_visible()
    expect(port).to_be_focused()
    port.fill('7777')
    expect(status).to_have_text('Локальная конфигурация')
    expect(tray).to_be_hidden()
    port.fill('7799')
    page.keyboard.press('Control+s')
    command = server.commands.get(timeout=3)
    assert command['action'] == 'save'
    assert command['values']['INFINI_TERRARIA_PORT'] == '7799'
    assert command['extra'] == {'lanEnabled': False, 'savedRevision': 'disk-a'}
    expect(status).to_have_text('Черновик / Не сохранён')
    snapshot['values'] = dict(snapshot['values'], INFINI_TERRARIA_PORT='7799')
    snapshot['savedValues'] = dict(snapshot['values'])
    snapshot['savedRevision'] = 'disk-saved'
    snapshot['actionResults'] = [{'id': command['id'], 'action': 'save', 'ok': True,
                                  'status': 'succeeded', 'savedValues': snapshot['savedValues'],
                                  'savedRevision': 'disk-saved', 'savedLanEnabled': False}]
    server.publish(snapshot)
    expect(status).to_have_text('Локальная конфигурация')
    expect(count).to_have_text('Изменений нет')
    expect(tray).to_be_hidden()
    expect(port).to_be_focused()
    assert original_port.evaluate('(element) => element === document.querySelector("#field-INFINI_TERRARIA_PORT")')
    assert original_status.evaluate('(element) => element === document.querySelector("[data-draft-status]")')

    # LAN is independently dirty even when no configuration field was edited.
    lan = page.locator('#lan-enabled')
    lan.press('Space')
    expect(lan).to_be_checked()
    expect(status).to_have_text('Черновик / Не сохранён')
    expect(count).to_have_text('1 несохранённых изменений')
    expect(tray).to_be_visible()
    expect(port).to_have_value('7799')
    expect(lan).to_be_focused()
    page.locator('.network-mode .toggle-track').click()
    expect(lan).not_to_be_checked()
    expect(status).to_have_text('Локальная конфигурация')
    expect(tray).to_be_hidden()
    assert server.commands.empty(), 'Edits, reversion and LAN changes must not submit actions'


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


def test_route_motion_does_not_replay_for_drafts_polling_or_keyboard(browser_studio):
    page, server, snapshot = browser_studio
    page.add_init_script('''
        window.workspaceEntrances = 0;
        document.addEventListener('animationstart', event => {
            if (event.target.id === 'workspace') window.workspaceEntrances += 1;
        });
    ''')

    def entrance_count():
        # Observe browser animation events after paint, rather than CSS classes
        # or exact durations. This also catches animations started by a render.
        return page.evaluate('''() => new Promise(resolve => requestAnimationFrame(
            () => requestAnimationFrame(() => resolve(window.workspaceEntrances))))''')

    page.goto(server.url + '#configure')
    page.locator('#preset-select').wait_for(state='visible')
    assert entrance_count() == 0, 'Initial connection must not animate the workspace'
    page.locator('[data-route="multiplayer"]').click()
    port = page.locator('#field-INFINI_TERRARIA_PORT')
    port.wait_for(state='visible')
    page.wait_for_function('() => window.workspaceEntrances === 1')
    port.fill('779')
    port.press_sequentially('9')
    assert entrance_count() == 1, 'Editing a draft replayed the route entrance'

    # A changed catalog forces a presentation render, while an untouched port
    # proves the new snapshot arrived. The newer draft and its focus must survive.
    snapshot['fields'][1]['options'] = ['fixture-model', 'fixture-second']
    snapshot['savedValues']['INFINI_PORT'] = '18876'
    snapshot['savedRevision'] = 'disk-b'
    server.publish(snapshot)
    page.wait_for_function('() => document.querySelector("#field-INFINI_PORT").value === "18876"')
    assert port.input_value() == '7799'
    assert port.evaluate('(element) => element === document.activeElement')
    assert entrance_count() == 1, 'A polled snapshot replayed the route entrance'

    page.locator('[data-route="providers"]').press('Enter')
    page.locator('#field-INFINI_CODEX_LLM_MODEL').wait_for(state='visible')
    assert entrance_count() == 1, 'Keyboard navigation must keep the workspace still'
    page.keyboard.press('Control+k')
    page.locator('#global-search').fill('INFINI_TERRARIA_PORT')
    page.locator('[data-search-key="INFINI_TERRARIA_PORT"]').wait_for(state='visible')
    page.keyboard.press('Enter')
    port.wait_for(state='visible')
    assert port.evaluate('(element) => element === document.activeElement')
    assert port.input_value() == '7799'
    assert entrance_count() == 1, 'Search navigation animated a focused input'

    page.emulate_media(reduced_motion='reduce')
    page.locator('[data-route="providers"]').click()
    page.locator('#field-INFINI_CODEX_LLM_MODEL').wait_for(state='visible')
    assert entrance_count() == 1, 'Reduced-motion users still received a route entrance'
    assert server.commands.empty(), 'Navigation and draft edits must not submit actions'


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 1000}, {'width': 390, 'height': 844}])
def test_diagnostic_tabs_and_long_trace_remain_usable_without_page_overflow(browser_studio, viewport):
    page, server, snapshot = browser_studio
    expect = pytest.importorskip('playwright.sync_api').expect
    prompt = 'TRACE_' + 'unbroken_payload_' * 80
    snapshot['trace'] = {'summary': 'Готова локальная сводка.', 'events': 'Локальные события.', 'prompts': prompt,
                         'failure': 'Ошибка показана целиком.'}
    snapshot['status'] = 'Локальный путь: C:/models/' + 'long_directory_' * 30
    server.publish(snapshot)
    page.set_viewport_size(viewport)
    page.goto(server.url + '#diagnostics')
    panel = page.locator('#trace-view')
    expect(panel).to_have_text(snapshot['trace']['summary'])

    # End reaches the last tab even when the tab strip must scroll locally.
    # Returning with Home/ArrowRight proves every panel remains keyboard usable.
    page.locator('#tab-summary').press('End')
    last = page.locator('#tab-failure')
    expect(last).to_be_focused()
    expect(last).to_have_attribute('aria-selected', 'true')
    expect(last).to_be_in_viewport(ratio=1)
    expect(panel).to_have_text(snapshot['trace']['failure'])
    last.press('Home')
    page.locator('#tab-summary').press('ArrowRight')
    expect(page.locator('#tab-events')).to_be_focused()
    expect(panel).to_have_text(snapshot['trace']['events'])
    page.locator('#tab-events').press('ArrowRight')
    expect(page.locator('#tab-prompts')).to_be_focused()
    expect(page.locator('#tab-prompts')).to_have_attribute('aria-selected', 'true')
    expect(panel).to_have_text(prompt)

    dimensions = page.evaluate('''() => {
        const panel = document.querySelector('#trace-view');
        const tabs = document.querySelector('.trace-tabs');
        return {viewport: innerWidth, page: document.documentElement.scrollWidth,
                panel: panel.getBoundingClientRect().right, panelScroll: panel.scrollWidth,
                panelWidth: panel.clientWidth, tabs: tabs.getBoundingClientRect().right};
    }''')
    assert dimensions['page'] <= dimensions['viewport'] + 1, 'Diagnostics widened the document'
    assert dimensions['panel'] <= dimensions['viewport'] + 1, 'Trace panel extends off-screen'
    assert dimensions['tabs'] <= dimensions['viewport'] + 1, 'Tab strip extends off-screen'
    assert dimensions['panelScroll'] <= dimensions['panelWidth'], 'Long trace text became horizontally clipped'
    assert server.commands.empty(), 'Reading trace tabs must not submit actions'


def test_mobile_keyboard_navigation_keeps_focused_fields_above_dirty_save_tray(browser_studio):
    from infini_local.desktop.settings_fields import FIELDS
    from infini_local.desktop.settings_schema import DEFAULTS

    page, server, snapshot = browser_studio
    # Use the shipped form density and order to exercise native browser focus
    # scrolling. Keep the shared fixture small for the unrelated workflows.
    values = dict(DEFAULTS, INFINI_USE_LLM='0', INFINI_LLM_PROVIDER='local',
                  INFINI_IMAGE_BACKEND='off', INFINI_SDCPP_SERVER_AUTOSTART='0')
    for field in FIELDS:
        if field.get('secret'):
            values[field['key']] = ''
    snapshot.update(values=values, savedValues=values, defaults=dict(DEFAULTS), fields=copy.deepcopy(FIELDS))
    server.publish(snapshot)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(server.url + '#multiplayer')
    port = page.locator('#field-INFINI_TERRARIA_PORT')
    port.fill('7799')
    tray = page.locator('#save-tray')
    tray.wait_for(state='visible')
    for settled in (False, True):
        if settled:
            tray.evaluate('(element) => Promise.all(element.getAnimations().map(animation => animation.finished.catch(() => {})))')
        first_edit = port.evaluate('''field => ({
            focused: field === document.activeElement,
            bottom: field.getBoundingClientRect().bottom,
            trayTop: document.querySelector('#save-tray').getBoundingClientRect().top
        })''')
        assert first_edit['focused']
        assert first_edit['bottom'] <= first_edit['trayTop'] + 1, f'First edit is behind the new save tray: {first_edit}'
    page.locator('#page-search').focus()
    reached_terraria_port = False
    for _ in range(16):
        page.keyboard.press('Tab')
        focused = page.evaluate('''() => {
            const active = document.activeElement;
            const control = active.closest('.toggle-control') || active;
            const box = control.getBoundingClientRect();
            return {id: active.id, tag: active.tagName, top: box.top, bottom: box.bottom,
                    inForm: document.querySelector('#workspace').contains(active),
                    visible: box.width > 0 && box.height > 0,
                    trayTop: document.querySelector('#save-tray').getBoundingClientRect().top};
        }''')
        if focused['inForm'] and focused['visible'] and focused['tag'] in {'INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'A'}:
            assert focused['bottom'] <= focused['trayTop'] + 1, f'Focused control is behind the save tray: {focused}'
        reached_terraria_port |= focused['id'] == 'field-INFINI_TERRARIA_PORT'
    assert reached_terraria_port, 'Native Tab navigation never reached the Terraria port'
    assert port.input_value() == '7799'
    assert tray.is_visible()
    assert server.commands.empty(), 'Keyboard navigation must not save the draft'


@pytest.mark.parametrize('viewport', [
    {'width': 1440, 'height': 1000},
    {'width': 390, 'height': 844},
])
def test_light_theme_and_accent_follow_current_navigation(browser_studio, viewport):
    """The light workspace uses shared tokens and a travelling route highlight."""
    page, server, _snapshot = browser_studio
    page.set_viewport_size(viewport)
    page.goto(server.url + '#operate')
    page.locator('.station').wait_for(state='visible')
    if viewport['width'] <= 720:
        page.locator('.mobile-menu').click()

    expect = pytest.importorskip('playwright.sync_api').expect
    active = page.locator('.main-nav.active')
    expect(active).to_have_attribute('aria-current', 'page')
    marker = page.locator('.nav-active-marker')
    expect(marker).to_be_visible()

    def expect_route_highlight():
        # The active link is intentionally transparent: the separate accent
        # marker supplies its background, including after keyboard navigation.
        page.wait_for_function('''() => {
            const marker = document.querySelector('.nav-active-marker').getBoundingClientRect();
            const active = document.querySelector('.nav-link.active').getBoundingClientRect();
            return ['top', 'left', 'width', 'height'].every(key => Math.abs(marker[key] - active[key]) <= 1);
        }''')

    expect_route_highlight()
    colors = page.evaluate('''() => {
        const style = (selector, property) => getComputedStyle(document.querySelector(selector))[property];
        const token = name => {
            const probe = document.createElement('span');
            probe.style.color = `var(${name})`;
            document.body.append(probe);
            const color = getComputedStyle(probe).color;
            probe.remove();
            return color;
        };
        return {
            scheme: getComputedStyle(document.documentElement).colorScheme,
            canvas: style('body', 'backgroundColor'), canvasToken: token('--canvas'),
            ink: style('body', 'color'), inkToken: token('--text'),
            rail: style('.rail', 'backgroundColor'), railToken: token('--rail'),
            railInk: style('.rail', 'color'),
            activeHome: style('.main-nav.active', 'backgroundColor'),
            activeInk: style('.main-nav.active', 'color'), accentInk: token('--on-accent'),
            marker: style('.nav-active-marker', 'backgroundColor'), accent: token('--accent'),
            station: style('.station', 'backgroundColor'),
            primary: style('.station .button-primary', 'backgroundColor'),
            documentWidth: document.documentElement.scrollWidth,
            viewportWidth: innerWidth,
        };
    }''')
    assert colors['scheme'] == 'light'
    assert colors['canvas'] == colors['canvasToken']
    assert colors['ink'] == colors['railInk'] == colors['inkToken']
    assert colors['rail'] == colors['railToken']
    assert colors['activeHome'] == 'rgba(0, 0, 0, 0)'
    assert colors['activeInk'] == colors['accentInk']
    assert colors['marker'] == colors['primary'] == colors['accent']
    assert colors['station'] not in {colors['canvas'], 'rgba(0, 0, 0, 0)'}
    assert colors['documentWidth'] <= colors['viewportWidth'] + 1

    page.locator('[data-route="providers"]').press('Enter')
    expect(page.locator('[data-route="providers"]')).to_have_attribute('aria-current', 'page')
    expect(active).to_have_count(0)
    if viewport['width'] <= 720:
        page.locator('.mobile-menu').click()
    expect_route_highlight()
    assert server.commands.empty(), 'Reading the theme and navigating must not run actions'


@pytest.mark.parametrize('dismissal', ['later', 'escape', 'replace', 'reopen'])
def test_defaults_refresh_does_not_reopen_or_replace_dismissed_dialog(browser_studio, dismissal):
    page, server, snapshot = browser_studio
    expect = pytest.importorskip('playwright.sync_api').expect
    snapshot['defaultsUpdate'] = {'version': 'fixture', 'revision': 'offer-a', 'changes': [
        {'key': 'INFINI_LLM_MAX_TOKENS', 'current': '9000', 'recommended': '18000', 'reason': 'fixture'}]}
    server.publish(snapshot)
    page.goto(server.url + '#configure')
    page.locator('[data-ui="defaults-update"]').click()
    held = []
    page.route('**/api/state', lambda route: held.append(route))
    with page.expect_request('**/api/state'):
        page.locator('#defaults-refresh').click()
    page.wait_for_timeout(50)
    assert held, 'Refresh request must be in flight before dismissal'
    if dismissal == 'later':
        page.locator('#utility-dialog [data-ui="close-dialog"]').click()
    else:
        page.keyboard.press('Escape')
    if dismissal == 'replace':
        page.locator('[data-ui="notifications"]').click()
    elif dismissal == 'reopen':
        page.locator('[data-ui="defaults-update"]').click()
        page.locator('#defaults-refresh').focus()
    dialog = page.locator('#utility-dialog')
    before = page.locator('#utility-body').inner_html()
    for route in held:
        route.fulfill(json=snapshot)
    page.unroute('**/api/state')
    page.wait_for_timeout(150)
    if dismissal in ('later', 'escape'):
        expect(dialog).not_to_be_visible()
    else:
        expect(dialog).to_be_visible()
        assert page.locator('#utility-body').inner_html() == before
        if dismissal == 'reopen':
            expect(page.locator('#defaults-refresh')).to_be_focused()
    assert server.commands.empty(), 'Refreshing or dismissing must never apply recommendations'
