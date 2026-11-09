"""Official downloads are explicit, bounded, cancellable and never executed."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
import threading
from urllib.request import Request
import zipfile

import pytest

from infini_local.desktop import studio_sdcpp_install as owner


def archive(entries=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as package:
        for name, data in (entries or [('bin/sd-server', b'not executed')]):
            package.writestr(name, data)
    return buffer.getvalue()


def asset(data, name='sd-bin-linux-x64-vulkan.zip', asset_id=42):
    return {'id': asset_id, 'name': name, 'size': len(data),
            'browser_download_url': f'https://github.com/leejet/stable-diffusion.cpp/releases/download/master/{name}',
            'digest': 'sha256:' + hashlib.sha256(data).hexdigest()}


def finish(installer):
    installer._thread.join(5)
    assert not installer._thread.is_alive(), 'worker failed to finish'
    return installer.snapshot()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(owner.host_platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(owner.host_platform, 'machine', lambda: 'x86_64')
    config = tmp_path / 'settings.env'
    config.write_bytes(b'PRIVATE=untouched\n')
    installer = owner.SdcppInstaller(config)
    yield installer, config
    installer.close()
    assert config.read_bytes() == b'PRIVATE=untouched\n'


def serve(monkeypatch, data, metadata=None):
    item = metadata or asset(data)
    calls = []
    def open_url(url):
        calls.append(url)
        return io.BytesIO(json.dumps({'tag_name': 'master-test', 'assets': [item]}).encode() if url == owner.CATALOG_URL else data)
    monkeypatch.setattr(owner, '_open_url', open_url)
    return calls


def test_explicit_install_repeat_refresh_and_missing_digest(setup, monkeypatch):
    installer, config = setup
    data = archive()
    calls = serve(monkeypatch, data)
    assert calls == [] and installer.snapshot()['builds'] == []
    with pytest.raises(ValueError):
        installer.install('https://evil.example/download')
    installer.refresh_catalog()
    state = finish(installer)
    assert len(calls) == 1 and state['builds'][0]['verified'] is True
    installer.install('42')
    state = finish(installer)
    first = Path(state['installedPath'])
    assert state['status'] == 'installed' and first.read_bytes() == b'not executed'
    assert first.stat().st_mode & stat.S_IXUSR
    item = asset(data)
    item.pop('digest')
    serve(monkeypatch, data, item)
    installer.refresh_catalog()
    state = finish(installer)
    assert state['installedPath'] == str(first) and not state['builds'][0]['verified']
    installer.install('42')
    second = Path(finish(installer)['installedPath'])
    assert second != first and first.exists() and second.exists()
    assert not list(config.parent.glob('sdcpp/.download-*'))


def test_cancel_cleans_partial_download_rejects_parallel_work(setup, monkeypatch):
    installer, config = setup
    data = archive()
    serve(monkeypatch, data)
    installer.refresh_catalog()
    finish(installer)
    entered, release = threading.Event(), threading.Event()
    class Slow(io.BytesIO):
        def read(self, size=-1):
            entered.set()
            assert release.wait(5)
            return super().read(size)
        read1 = read
    monkeypatch.setattr(owner, '_open_url', lambda url: Slow(data))
    try:
        installer.install('42')
        assert entered.wait(5)
        with pytest.raises(ValueError):
            installer.install('42')
        with pytest.raises(ValueError):
            installer.refresh_catalog()
        installer.cancel()
    finally:
        release.set()
        state = finish(installer)
    assert state['status'] == 'cancelled' and state['installedPath'] == ''
    assert list((config.parent / 'sdcpp').iterdir()) == []


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/escape', 'folder\\escape', 'NUL.txt', 'x./sd-server', 'x /sd-server'])
def test_archive_paths_fail_without_escape(setup, monkeypatch, name):
    installer, config = setup
    serve(monkeypatch, archive([(name, b'bad'), ('sd-server', b'good')]))
    installer.refresh_catalog()
    finish(installer)
    installer.install('42')
    assert finish(installer)['status'] == 'error'
    assert sorted(p.name for p in config.parent.iterdir()) == ['sdcpp', 'settings.env']
    assert list((config.parent / 'sdcpp').iterdir()) == []


@pytest.mark.parametrize('kind', ['zip_link', 'tar_link', 'tar_hardlink', 'tar_device', 'duplicate', 'digest', 'oversize', 'missing_executable', 'bomb'])
def test_malformed_package_refused(setup, monkeypatch, kind):
    installer, config = setup
    data = archive()
    if kind == 'zip_link':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as package:
            item = zipfile.ZipInfo('sd-server')
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            package.writestr(item, '/tmp/bad')
        data = buffer.getvalue()
    elif kind.startswith('tar_'):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as package:
            item = tarfile.TarInfo('sd-server')
            item.type = {'tar_link': tarfile.SYMTYPE, 'tar_hardlink': tarfile.LNKTYPE, 'tar_device': tarfile.CHRTYPE}[kind]
            item.linkname = '../escape'
            package.addfile(item)
        data = buffer.getvalue()
    elif kind == 'duplicate':
        data = archive([('sd-server', b'a'), ('SD-SERVER', b'b')])
    elif kind == 'missing_executable':
        data = archive([('README', b'hi')])
    elif kind == 'bomb':
        monkeypatch.setattr(owner, 'MAX_EXTRACTED', 1)
    item = asset(data)
    if kind == 'digest':
        item['digest'] = 'sha256:' + '0' * 64
    elif kind == 'oversize':
        item['size'] -= 1
    serve(monkeypatch, data, item)
    installer.refresh_catalog()
    finish(installer)
    installer.install('42')
    assert finish(installer)['status'] == 'error'
    assert list((config.parent / 'sdcpp').iterdir()) == []


@pytest.mark.parametrize('url', ['http://github.com/leejet/stable-diffusion.cpp/releases/download/a/b',
    'https://evil.example/a', 'https://github.com.evil.example/a', 'https://github.com/other/repo/releases/download/a/b',
    'https://user:password@release-assets.githubusercontent.com/a', 'https://release-assets.githubusercontent.com:444/a'])
def test_redirect_allowlist(url):
    with pytest.raises(ValueError):
        owner._ReleaseRedirect().redirect_request(Request(owner.CATALOG_URL), None, 302, '', {}, url)


def test_official_redirect_and_exact_cuda_pairing(monkeypatch):
    url = 'https://release-assets.githubusercontent.com/github-production-release-asset/x?signature=abc'
    assert owner._ReleaseRedirect().redirect_request(Request(owner.CATALOG_URL), None, 302, '', {}, url).full_url == url
    data = archive()
    names = ['sd-master-fc350be-bin-win-cuda12-x64.zip', 'cudart-sd-bin-win-cu12-x64.zip',
             'cudart-sd-bin-win-cu13-x64.zip', 'cudart-sd-bin-win-cu12-arm64.zip',
             'sd-master-Linux-Ubuntu-26.04-x86_64.zip', 'sd-master-Linux-Ubuntu-26.04-x86_64-vulkan.zip']
    _, builds = owner._catalog({'tag_name': 'master', 'assets': [asset(data, name, index + 1) for index, name in enumerate(names)]})
    assert list(builds) == ['1', '5', '6']
    assert [p['name'] for p in builds['1']['packages']] == names[:2]
    assert builds['1']['size'] == len(data) * 2
    assert builds['5']['backend'] == 'CPU'


def test_wrong_platform_rejected(setup, monkeypatch):
    installer, _ = setup
    serve(monkeypatch, archive(), asset(archive(), 'sd-bin-win-vulkan-x64.zip'))
    installer.refresh_catalog()
    assert finish(installer)['builds'][0]['platformCompatible'] is False
    with pytest.raises(ValueError, match='platform'):
        installer.install('42')


@pytest.mark.parametrize('prefix', ['', 'nested/runtime/'])
def test_cuda_downloads_only_matching_runtime_and_returns_server(setup, monkeypatch, prefix):
    installer, _ = setup
    monkeypatch.setattr(owner.host_platform, 'system', lambda: 'Windows')
    main = archive([('sd-server.exe', b'executable')])
    runtime = archive([(prefix + 'cudart64_12.dll', b'runtime'), (prefix + 'LICENSE', b'license')])
    items = [asset(main, 'sd-bin-win-cuda12-x64.zip', 1), asset(runtime, 'cudart-sd-bin-win-cu12-x64.zip', 2),
             asset(runtime, 'cudart-sd-bin-win-cu13-x64.zip', 3)]
    calls = []
    def open_url(url):
        calls.append(url)
        if url == owner.CATALOG_URL:
            return io.BytesIO(json.dumps({'tag_name': 'master', 'assets': items}).encode())
        return io.BytesIO(main if url == items[0]['browser_download_url'] else runtime)
    monkeypatch.setattr(owner, '_open_url', open_url)
    installer.refresh_catalog()
    finish(installer)
    installer.install('1')
    state = finish(installer)
    server = Path(state['installedPath'])
    assert state['status'] == 'installed'
    assert server.read_bytes() == b'executable'
    assert (server.parent / 'cudart64_12.dll').read_bytes() == b'runtime'
    assert calls == [owner.CATALOG_URL, items[0]['browser_download_url'], items[1]['browser_download_url']]


def test_failed_retry_preserves_previous_install(setup, monkeypatch):
    installer, _ = setup
    good = archive()
    serve(monkeypatch, good)
    installer.refresh_catalog()
    finish(installer)
    installer.install('42')
    first = finish(installer)['installedPath']
    monkeypatch.setattr(owner, '_open_url', lambda url: io.BytesIO(b'broken'))
    installer.install('42')
    state = finish(installer)
    assert state['status'] == 'error' and state['installedPath'] == first
    assert Path(first).read_bytes() == b'not executed'


def test_catalog_ignores_unsupported_archives_and_unknown_gpu_backends():
    names = ['sd-Linux-Ubuntu-26.04-x86_64-opencl.zip',
             'sd-Linux-Ubuntu-26.04-x86_64-sycl.zip',
             'sd-bin-linux-x64-vulkan.tar.gz']
    _, builds = owner._catalog({'tag_name': 'master', 'assets': [asset(archive(), name, i + 1) for i, name in enumerate(names)]})
    assert builds == {}
