"""Explicit, bounded installation of official sd.cpp release packages (never executes them)."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import platform as host_platform
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

CATALOG_URL = 'https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest'
RELEASE_PREFIX = '/leejet/stable-diffusion.cpp/releases/download/'
MAX_DOWNLOAD = 4 * 1024**3
MAX_EXTRACTED = 8 * 1024**3
MAX_FILES = 20000
CHUNK = 256 * 1024
TIMEOUT = 20
DEADLINE = 30 * 60


class _Cancelled(Exception):
    pass


def _allowed_url(url: str, *, redirect: bool = False) -> bool:
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None, 443) or parts.fragment:
        return False
    if url == CATALOG_URL:
        return True
    if parts.hostname == 'github.com':
        return parts.path.startswith(RELEASE_PREFIX) and '..' not in unquote(parts.path).split('/')
    return redirect and parts.hostname in {'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


class _ReleaseRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _allowed_url(newurl, redirect=True):
            raise ValueError('Unsafe release download redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(url):
    if not _allowed_url(url):
        raise ValueError('Only official sd.cpp releases are supported')
    return build_opener(_ReleaseRedirect()).open(
        Request(url, headers={'User-Agent': 'InfiniCrafterLocal-Studio', 'Accept': 'application/octet-stream' if url != CATALOG_URL else 'application/vnd.github+json'}),
        timeout=TIMEOUT,
    )


def _identity(name):
    value = name.lower()
    platform = 'windows' if re.search(r'(?:^|[-_])win(?:dows)?(?:[-_]|$)', value) else 'linux' if 'linux' in value else None
    arch = 'arm64' if re.search(r'arm64|aarch64', value) else 'x64' if re.search(r'x64|x86_64|amd64', value) else None
    cuda = re.search(r'(?:cuda|cu)[-_]?(\d+)', value)
    backend = 'CUDA ' + cuda.group(1) if cuda else 'Vulkan' if 'vulkan' in value else 'CPU' if re.search(r'cpu|avx|openblas', value) else 'CPU' if platform == 'linux' and re.search(r'(?:x86_64|x64|amd64|arm64|aarch64)\.zip$', value) and not any(k in value for k in ('cuda', 'rocm', 'sycl', 'metal', 'opencl')) else None
    return platform, arch, backend


def _catalog(payload):
    release = payload.get('tag_name', '')
    if not isinstance(release, str) or not release:
        raise ValueError('Release metadata has no version')
    assets = []
    for item in payload.get('assets', []):
        name, url, size, asset_id = (item.get(k) for k in ('name', 'browser_download_url', 'size', 'id'))
        if not isinstance(name, str) or not name.lower().endswith('.zip'):
            continue
        if not isinstance(url, str) or not _allowed_url(url) or url == CATALOG_URL:
            continue
        if type(size) is not int or not 0 < size <= MAX_DOWNLOAD or type(asset_id) is not int or asset_id <= 0:
            continue
        digest = item.get('digest')
        if digest is not None and not re.fullmatch(r'sha256:[0-9a-fA-F]{64}', str(digest)):
            continue
        platform, arch, backend = _identity(name)
        if not platform or not arch or not backend:
            continue
        assets.append({'id': str(asset_id), 'name': name, 'url': url, 'size': size,
                       'digest': digest, 'platform': platform, 'arch': arch, 'backend': backend})
    builds = {}
    for asset in assets:
        if 'cudart' in asset['name'].lower():
            continue
        packages = [asset]
        if asset['backend'].startswith('CUDA'):
            companions = [p for p in assets if 'cudart' in p['name'].lower()
                          and all(p[k] == asset[k] for k in ('platform', 'arch', 'backend'))]
            if len(companions) > 1:
                continue  # Never guess which runtime package the release intended.
            packages += companions
        total = sum(p['size'] for p in packages)
        if total > MAX_DOWNLOAD:
            continue
        builds[asset['id']] = {**asset, 'packages': packages, 'size': total,
            'verified': all(bool(p['digest']) for p in packages),
            'platformCompatible': asset['platform'] == {'Windows': 'windows', 'Linux': 'linux'}.get(host_platform.system())
                and asset['arch'] == {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(host_platform.machine().lower()),
            'label': f"{asset['platform']} {asset['arch']} · {asset['backend']} · {asset['name']}"}
    return release, builds


def _safe_member(name):
    if not name or '\\' in name or name.startswith('/'):
        raise ValueError('Unsafe archive path')
    parts = PurePosixPath(name).parts
    reserved = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)
    if not parts or any(p in ('.', '..') or p.endswith((' ', '.')) or reserved.match(p)
                        or any(ord(c) < 32 or c in '<>:"|?*' for c in p) for p in parts):
        raise ValueError('Unsafe archive path')
    return Path(*parts)


def _extract(archive, destination, check, budget, names):
    """Copy regular members ourselves; never trust archive extraction path/link semantics."""
    def write(name, size, directory, source):
        check()
        relative = _safe_member(name)
        key = relative.as_posix().casefold()
        if key in names and not directory:
            raise ValueError('Duplicate archive path')
        names.add(key)
        budget[0] += 1
        budget[1] += size
        if size < 0 or budget[0] > MAX_FILES or budget[1] > MAX_EXTRACTED:
            raise ValueError('Archive exceeds extraction limits')
        target = destination / relative
        if directory:
            target.mkdir(parents=True, exist_ok=True)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        remaining = size
        with source() as incoming, target.open('xb') as outgoing:
            while remaining:
                check()
                data = incoming.read(min(CHUNK, remaining))
                if not data:
                    raise ValueError('Truncated archive member')
                remaining -= len(data)
                outgoing.write(data)
            if incoming.read(1):
                raise ValueError('Archive member exceeds declared size')
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for item in package.infolist():
                mode = item.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or item.flag_bits & 1:
                    raise ValueError('Links, devices and encrypted archive members are forbidden')
                if item.file_size > max(item.compress_size, 1) * 1000:
                    raise ValueError('Archive compression ratio exceeds limit')
                write(item.filename, item.file_size, item.is_dir(), lambda: package.open(item))
    else:
        raise ValueError('Only ZIP release packages are supported')


class SdcppInstaller:
    def __init__(self, config_path):
        self._root = Path(config_path).resolve().parent / 'sdcpp'
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._builds = {}
        self._state = {'status': 'idle', 'busy': False, 'builds': [], 'release': '', 'error': '',
                       'downloadedBytes': 0, 'totalBytes': 0, 'installedPath': '', 'selectedId': ''}

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def _update(self, **fields):
        with self._lock:
            self._state.update(fields)

    def _start(self, status, work, **fields):
        with self._lock:
            if self._state['busy']:
                raise ValueError('An sd.cpp operation is already in progress')
            self._cancel.clear()
            self._state.update(status=status, busy=True, error='', **fields)
            def run():
                try:
                    work()
                except _Cancelled:
                    self._update(status='cancelled', error='')
                except Exception as exc:
                    self._update(status='error', error=str(exc))
                finally:
                    self._update(busy=False)
            self._thread = threading.Thread(target=run, name='studio-sdcpp-installer', daemon=True)
            self._thread.start()
            return self.snapshot()

    def _check(self, started):
        if self._cancel.is_set():
            raise _Cancelled()
        if time.monotonic() - started > DEADLINE:
            raise ValueError('sd.cpp operation exceeded its time limit')

    def refresh_catalog(self):
        def work():
            started = time.monotonic()
            with _open_url(CATALOG_URL) as response:
                data = bytearray()
                while True:
                    self._check(started)
                    chunk = getattr(response, 'read1', response.read)(CHUNK)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > 2 * 1024**2:
                        raise ValueError('Release metadata is too large')
            release, builds = _catalog(json.loads(data))
            self._check(started)
            with self._lock:
                self._builds = builds
                self._state.update(release=release, builds=[{k: v for k, v in b.items() if k not in ('url', 'digest', 'packages')} for b in builds.values()], status='idle')
        return self._start('catalog', work)

    def install(self, build_id):
        with self._lock:
            if not isinstance(build_id, str) or build_id not in self._builds:
                raise ValueError('Choose a build from the official release catalog')
            build = copy.deepcopy(self._builds[build_id])
            if not build['platformCompatible']:
                raise ValueError('This build does not match this computer platform and architecture')
            return self._start('downloading', lambda: self._install(build), selectedId=build_id,
                               downloadedBytes=0, totalBytes=build['size'])

    def cancel(self):
        with self._lock:
            if self._state['busy']:
                self._cancel.set()
            return self.snapshot()

    def close(self):
        self.cancel()
        worker = self._thread
        if worker is not None:
            worker.join(timeout=1)

    def _install(self, build):
        started = time.monotonic()
        self._root.mkdir(parents=True, exist_ok=True)
        if self._root.is_symlink():
            raise ValueError('Installation directory must not be a symbolic link')
        # A unique directory makes repeat installs safe, without replacing a working build.
        with tempfile.TemporaryDirectory(prefix='.download-', dir=self._root) as temp:
            stage = Path(temp)
            unpacked = stage / 'files'
            unpacked.mkdir()
            downloaded = 0
            budget, names = [0, 0], set()
            runtimes = []
            for index, asset in enumerate(build['packages']):
                archive = stage / f'{index}.archive'
                digest = hashlib.sha256()
                received = 0
                self._update(status='downloading')
                with _open_url(asset['url']) as response, archive.open('xb') as target:
                    while True:
                        self._check(started)
                        chunk = getattr(response, 'read1', response.read)(CHUNK)
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > asset['size'] or received > MAX_DOWNLOAD:
                            raise ValueError('Download exceeds declared size')
                        target.write(chunk)
                        digest.update(chunk)
                        self._update(downloadedBytes=downloaded + received)
                if received != asset['size']:
                    raise ValueError('Incomplete release download')
                if asset['digest'] and digest.hexdigest() != asset['digest'].split(':')[1].lower():
                    raise ValueError('Release SHA256 digest mismatch')
                downloaded += received
                self._update(status='extracting')
                destination = unpacked if index == 0 else stage / f'runtime-{index}'
                destination.mkdir(exist_ok=True)
                _extract(archive, destination, lambda: self._check(started), budget, names if index == 0 else set())
                if index:
                    runtimes.append(destination)
            expected = 'sd-server.exe' if build['platform'] == 'windows' else 'sd-server'
            candidates = [p for p in unpacked.rglob(expected) if p.is_file()]
            if len(candidates) != 1:
                raise ValueError('Release must contain exactly one sd-server executable')
            executable = candidates[0]
            # Companion ZIPs can have their own top-level directory. Runtime libraries
            # must be adjacent to sd-server, not merely somewhere in its install tree.
            for runtime in runtimes:
                libraries = [p for p in runtime.rglob('*') if p.is_file() and
                             (p.suffix.lower() == '.dll' if build['platform'] == 'windows' else '.so' in p.name)]
                if not libraries:
                    raise ValueError('CUDA runtime package contains no shared libraries')
                for library in libraries:
                    self._check(started)
                    target = executable.parent / library.name
                    if any(p.name.casefold() == target.name.casefold() for p in executable.parent.iterdir()):
                        raise ValueError('CUDA runtime library conflicts with another package file')
                    library.rename(target)
                # Retain license/readme and other package contents without overwriting the build.
                runtime_destination = unpacked / ('_cuda-' + runtime.name)
                if runtime_destination.exists():
                    raise ValueError('CUDA runtime directory conflicts with the build')
                runtime.rename(runtime_destination)
            if build['platform'] == 'linux':
                executable.chmod(0o755)
                # Shared libraries need read permission only; no package code is executed.
            relative = executable.relative_to(unpacked)
            with self._lock:
                self._check(started)
                final = self._root / f"build-{build['id']}-{stage.name.removeprefix('.download-')}"
                os.rename(unpacked, final)
                self._state.update(status='installed', installedPath=str(final / relative))
