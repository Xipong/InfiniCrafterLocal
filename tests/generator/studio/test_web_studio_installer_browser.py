"""Installer clicks through the shipped browser UI and real local HTTP bridge."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from .test_web_studio_onboarding_browser import onboarding_browser, wait_progress


@pytest.mark.parametrize(('system', 'machine', 'platform'), [
    ('Windows', 'AMD64', 'win'), ('Linux', 'x86_64', 'linux'),
])
def test_build_catalog_click_retry_and_reopen(onboarding_browser, monkeypatch, system, machine, platform):
    from infini_local.desktop import studio_sdcpp_install as owner
    page, server, config, original, requests = onboarding_browser
    calls = []
    release = {'tag_name': 'test', 'assets': [
        {'id': index, 'name': f'sd-bin-{target}-x64-vulkan.zip', 'size': 1024,
         'browser_download_url': f'https://github.com/leejet/stable-diffusion.cpp/releases/download/test/sd-bin-{target}-x64-vulkan.zip'}
        for index, target in enumerate(('win', 'linux'), 1)
    ]}

    def download(url):
        calls.append(url)
        assert url == owner.CATALOG_URL, 'Catalog clicks must never download a binary'
        return io.BytesIO(json.dumps(release).encode())

    monkeypatch.setattr(owner, '_open_url', download)
    monkeypatch.setattr(owner, 'host_platform', SimpleNamespace(system=lambda: system, machine=lambda: machine))
    page.goto(server.url)
    page.locator('[data-onboarding-step="2"]').click()
    wait_progress(page, step=2)
    assert not calls, 'Opening the guide must not contact GitHub'
    # Two synchronous clicks must not dispatch duplicate commands.
    page.locator('#onboarding-catalog').evaluate('(button) => {button.click(); button.click();}')
    page.locator('#onboarding-build').wait_for()
    page.locator('#onboarding-catalog:not(:disabled)').wait_for()
    assert calls == [owner.CATALOG_URL]
    selected = page.locator('#onboarding-build option:checked')
    assert f'sd-bin-{platform}-x64-vulkan.zip' in selected.inner_text()
    assert page.locator('#onboarding-build option:disabled').count() == 1
    assert page.locator('#onboarding-feedback').inner_text() == ''
    assert page.locator('#onboarding-download').is_enabled()
    page.keyboard.press('Escape')
    page.locator('#onboarding-launcher').click()
    page.locator('#onboarding-build').wait_for()
    page.locator('[data-onboarding-next]').click()
    page.locator('#onboarding-build').wait_for()
    page.locator('[data-onboarding-back]').click()
    page.locator('#onboarding-catalog:not(:disabled)').click()
    page.locator('#onboarding-catalog:not(:disabled)').wait_for()
    assert calls == [owner.CATALOG_URL, owner.CATALOG_URL]
    installer_requests = [request for request in requests if request['action'].startswith('sd')]
    assert installer_requests == [{'action': 'sdCatalog', 'values': {}, 'extra': {}}] * 2


@pytest.mark.parametrize('failure', ['old_server', 'closed_server', 'expired_session'])
def test_build_catalog_reports_local_rejection_and_allows_retry(onboarding_browser, monkeypatch, failure):
    from infini_local.desktop import web_studio
    page, server, config, original, requests = onboarding_browser
    page.goto(server.url)
    page.locator('[data-onboarding-step="2"]').click()
    wait_progress(page, step=2)
    if failure == 'old_server':
        monkeypatch.setattr(web_studio, 'ACTIONS', web_studio.ACTIONS - {'sdCatalog'})
        expected = 'Полностью закрой Studio'
    elif failure == 'closed_server':
        server.accepting_actions = False
        expected = 'Студия уже закрыта'
    else:
        server.token = 'new-session-for-fixture'
        expected = 'Сессия недоступна'
    page.locator('#onboarding-catalog').click()
    page.wait_for_function('(message) => document.querySelector("#onboarding-feedback").textContent.includes(message)', arg=expected)
    assert page.locator('#onboarding-catalog').is_enabled()
    assert page.locator('#onboarding-build').count() == 0
    assert config.read_bytes() == original



@pytest.mark.parametrize('viewport', [(1440, 1000), (390, 844)])
def test_progress_and_installer_recovery_keep_separate_feedback(onboarding_browser, monkeypatch, viewport):
    """Integrated help errors survive independently and remain usable on mobile."""
    from infini_local.desktop import studio_sdcpp_install, web_studio
    page, server, config, original, requests = onboarding_browser
    page.set_viewport_size({'width': viewport[0], 'height': viewport[1]})
    allowed = web_studio.ACTIONS
    monkeypatch.setattr(web_studio, 'ACTIONS', allowed - {'onboardingProgress', 'sdCatalog'})
    page.goto(server.url)
    page.locator('[data-onboarding-step="2"]').click()
    page.wait_for_function("() => document.querySelector('#onboarding-progress-feedback').textContent.includes('не подтверждено')")
    page.locator('#onboarding-catalog').click()
    page.wait_for_function("() => document.querySelector('#onboarding-feedback').textContent.includes('HTTP 400')")
    installer_error = page.locator('#onboarding-feedback').inner_text()
    assert page.locator('#onboarding-dialog').evaluate('(e) => e.scrollWidth <= e.clientWidth')
    page.locator('[data-onboarding-next]').scroll_into_view_if_needed()
    assert page.locator('[data-onboarding-next]').evaluate('(e) => {const r=e.getBoundingClientRect(); return r.top>=0 && r.bottom<=innerHeight;}')
    monkeypatch.setattr(web_studio, 'ACTIONS', allowed)
    page.locator('[data-onboarding-next]').click()
    wait_progress(page, step=3)
    page.wait_for_function("() => document.querySelector('#onboarding-progress-feedback').textContent === ''")
    assert page.locator('#onboarding-feedback').inner_text() == installer_error
    release = {'tag_name': 'test', 'assets': [
        {'id': 1, 'name': 'sd-bin-linux-x64-vulkan.zip', 'size': 1024,
         'browser_download_url': 'https://github.com/leejet/stable-diffusion.cpp/releases/download/test/sd-bin-linux-x64-vulkan.zip'}
    ]}
    monkeypatch.setattr(studio_sdcpp_install, '_open_url', lambda url: io.BytesIO(json.dumps(release).encode()))
    monkeypatch.setattr(studio_sdcpp_install, 'host_platform', SimpleNamespace(system=lambda: 'Linux', machine=lambda: 'x86_64'))
    page.locator('#onboarding-catalog').click()
    page.locator('#onboarding-build').wait_for()
    assert page.locator('#onboarding-feedback').inner_text() == ''
    assert page.locator('#onboarding-progress-feedback').inner_text() == ''
    assert config.read_bytes() == original
