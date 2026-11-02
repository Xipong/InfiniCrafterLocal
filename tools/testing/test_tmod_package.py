"""Small in-memory format fixtures for the read-only package inspector."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import zipfile

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.build.verify_tmod_package import read_info, read_package, verify
from tools.build.build_studio_bundle import (
    ENTRY_POINT, PLATFORM, PYTHON_TAG, RESOURCE_ARCHIVE, RESOURCE_MANIFEST,
    SOURCE_DIRS, SOURCE_FILES, copy_sources, verify_resources, write_bundle,
)


def studio_fixture(*, omit=(), extra=None):
    """Container-level fixture only: these Python/PE bytes are not executable."""
    files = {
        'python/python.exe': b'MZfixture-interpreter',
        f'python/python{PYTHON_TAG}.dll': b'MZfixture-python-dll',
        f'python/python{PYTHON_TAG}.zip': b'fixture-stdlib',
        f'python/python{PYTHON_TAG}._pth': b'fixture-search-path',
        'python/LICENSE.txt': b'Python license fixture',
        'python/Lib/site-packages/PIL/__init__.py': b'Pillow fixture',
        'python/Lib/site-packages/PIL/_imaging.cp314-win_amd64.pyd': b'MZfixture-native-pillow',
        'python/Lib/site-packages/pydantic/__init__.py': b'Pydantic fixture',
        'python/Lib/site-packages/pydantic_core/__init__.py': b'Pydantic Core fixture',
        'python/Lib/site-packages/pydantic_core/_pydantic_core.cp314-win_amd64.pyd': b'MZfixture-native-pydantic',
        ENTRY_POINT: b'fixture managed entrypoint',
        'LocalGenerator/server.py': b'fixture generator entrypoint',
        'LocalGenerator/config.example.env': b'fixture configuration template',
        'LocalGenerator/infini_local/desktop/web_studio.py': b'fixture web bridge',
        'LocalGenerator/infini_local/desktop/webui/index.html': b'fixture frontend',
        'LocalGenerator/infini_local/desktop/webui/studio.js': b'fixture script',
        'LocalGenerator/infini_local/desktop/webui/studio.css': b'fixture styles',
        'START_HERE.html': b'fixture handbook',
        'LICENSE': b'fixture IFC license',
    }
    files.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, content in files.items():
            if name not in omit:
                archive.writestr(name, content)
    payload = stream.getvalue()
    manifest = {'schemaVersion': 1, 'platforms': {PLATFORM: {
        'archive': RESOURCE_ARCHIVE, 'sha256': hashlib.sha256(payload).hexdigest(),
        'python': 'python/python.exe', 'entryPoint': ENTRY_POINT,
    }}}
    return {RESOURCE_MANIFEST: json.dumps(manifest).encode(), RESOURCE_ARCHIVE: payload}


def string(value):
    data = value.encode()
    size = len(data)
    prefix = bytearray()
    while size >= 128:
        prefix.append((size & 127) | 128)
        size >>= 7
    prefix.append(size)
    return bytes(prefix) + data


def fixture(files=None, *, name='fixture', version='0.5.1', compress=False):
    # In-memory format fixtures only, not distributable/game mods.
    files = {'Info': b'\0'} if files is None else files
    data = string(name) + string(version) + struct.pack('<i', len(files))
    payloads = []
    for path, content in files.items():
        stored = content
        if compress:
            compressor = zlib.compressobj(wbits=-15)
            stored = compressor.compress(content) + compressor.flush()
        data += string(path) + struct.pack('<ii', len(content), len(stored))
        payloads.append(stored)
    data += b''.join(payloads)
    return b'TMOD' + string('2026.8.3.0') + hashlib.sha1(data).digest() + bytes(256) + struct.pack('<i', len(data)) + data


class PackageTests(unittest.TestCase):
    def test_container(self):
        tml, name, version, files = read_package(fixture())
        self.assertEqual((tml, name, version), ('2026.8.3.0', 'fixture', '0.5.1'))
        self.assertEqual(files, {'Info': b'\0'})

    def test_raw_deflate_payload(self):
        content = b'repeated raw-deflate content ' * 200
        files = {'long-payload.txt': content}
        packed = fixture(files, compress=True)
        self.assertLess(len(packed), len(content))
        self.assertEqual(read_package(packed)[3], files)

    def test_reject_corruption(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            read_package(fixture()[:-1] + b'x')

    def test_reject_dll_renamed_tmod(self):
        with self.assertRaisesRegex(ValueError, 'Not a TMOD'):
            read_package(b'MZfakeDLL')

    def test_reject_truncation(self):
        with self.assertRaises(ValueError):
            read_package(fixture()[:30])

    def test_info(self):
        info = string('version') + string('0.5.1')
        info += string('modReferences') + string('ParticleLibrary@3.2.1.0') + string('Luminance') + b'\0\0'
        self.assertEqual(read_info(info), {'version': '0.5.1', 'modReferences': ['ParticleLibrary@3.2.1.0', 'Luminance']})

    def test_unknown_info(self):
        with self.assertRaisesRegex(ValueError, 'Unknown Info'):
            read_info(string('unknown') + b'\0')


class FullVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'fixture'
        self.source.mkdir()
        (self.source / 'build.txt').write_text(
            'version = 0.5.1\nmodReferences = ParticleLibrary@3.2.1.0, Luminance\n',
            encoding='utf-8',
        )
        localization = self.source / 'Localization' / 'en-US.hjson'
        localization.parent.mkdir()
        localization.write_bytes(b'{Fixture: "test localization"}\n')
        # Texture presence is part of verify(); image decoding is not exercised here.
        texture = self.source / 'Assets' / 'fixture.png'
        texture.parent.mkdir()
        texture.write_bytes(b'fixture texture bytes')
        self.assembly = self.root / 'fixture.dll'
        self.assembly.write_bytes(b'MZformat-test-assembly')
        info = string('version') + string('0.5.1')
        info += string('modReferences') + string('ParticleLibrary@3.2.1.0') + string('Luminance') + b'\0\0'
        self.files = {
            'Info': info,
            'fixture.dll': self.assembly.read_bytes(),
            'Localization/en-US.hjson': localization.read_bytes(),
            'Assets/fixture.png': texture.read_bytes(),
        }
        self.files.update(studio_fixture())
        # Avoid .tmod suffix: these fixtures are deliberately not playable mods.
        self.package = self.root / 'container.fixture'

    def check(self, *, version='0.5.1'):
        self.package.write_bytes(fixture(self.files, version=version))
        return verify(self.package, self.source, self.assembly, '2026.8.3.0')

    def test_full_verification(self):
        report = self.check()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['version'], '0.5.1')
        self.assertEqual(report['fileCount'], 6)
        self.assertEqual(report['sha256'], hashlib.sha256(self.package.read_bytes()).hexdigest())
        self.assertEqual(report['files'], sorted(self.files))

    def test_wrong_package_version_rejected(self):
        with self.assertRaisesRegex(ValueError, 'version differs'):
            self.check(version='0.5.2')

    def test_wrong_dll_rejected(self):
        self.files['fixture.dll'] = b'MZdifferent-assembly'
        with self.assertRaisesRegex(ValueError, 'assembly differs'):
            self.check()

    def test_missing_localization_rejected(self):
        del self.files['Localization/en-US.hjson']
        with self.assertRaisesRegex(ValueError, 'Localization missing or changed'):
            self.check()

    def test_missing_texture_rejected(self):
        del self.files['Assets/fixture.png']
        with self.assertRaisesRegex(ValueError, 'Texture missing'):
            self.check()

    def test_missing_studio_is_not_a_playable_release(self):
        del self.files[RESOURCE_MANIFEST]
        with self.assertRaisesRegex(ValueError, 'Studio manifest missing'):
            self.check()

    def test_changed_nested_runtime_is_rejected(self):
        self.files[RESOURCE_ARCHIVE] += b'changed bytes'
        with self.assertRaisesRegex(ValueError, 'runtime hash mismatch'):
            self.check()


class StudioBundleTests(unittest.TestCase):
    def test_missing_native_dependency_and_operator_state_are_rejected(self):
        native = 'python/Lib/site-packages/pydantic_core/_pydantic_core.cp314-win_amd64.pyd'
        for resources, error in (
            (studio_fixture(omit=(native,)), 'native dependency missing'),
            (studio_fixture(extra={'LocalGenerator/config.env': b'private provider settings'}), 'Operator state'),
            (studio_fixture(extra={'../outside.txt': b'escape'}), 'Unsafe Studio archive path'),
        ):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                verify_resources(resources.__getitem__)

    def test_required_app_and_runtime_resources_survive_the_container(self):
        resources = studio_fixture()
        report = verify_resources(resources.__getitem__)
        with zipfile.ZipFile(io.BytesIO(resources[RESOURCE_ARCHIVE])) as archive:
            self.assertEqual(archive.read(ENTRY_POINT), b'fixture managed entrypoint')
            self.assertEqual(archive.read('python/LICENSE.txt'), b'Python license fixture')
        self.assertEqual(report[PLATFORM]['sha256'], hashlib.sha256(resources[RESOURCE_ARCHIVE]).hexdigest())

    def test_source_selection_preserves_bytes_and_excludes_local_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'source'
            staged = Path(temporary) / 'staged'
            for directory in SOURCE_DIRS:
                (root / directory).mkdir(parents=True, exist_ok=True)
            for name in SOURCE_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(('source: ' + name).encode())
            selected = root / 'LocalGenerator/infini_local/desktop/webui/icon.png'
            selected.parent.mkdir(parents=True, exist_ok=True)
            selected.write_bytes(b'PNG bytes preserved without tML conversion')
            excluded = (
                'LocalGenerator/config.env', 'LocalGenerator/cache/private.json',
                'LocalGenerator/tests/fixture.py', 'LocalGenerator/.venv/python.exe',
                'LocalGenerator/infini_local/__pycache__/module.pyc',
                'LocalGenerator/infini_local/.env',
            )
            for name in excluded:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'private or development bytes')
            copy_sources(root, staged)
            self.assertEqual((staged / selected.relative_to(root)).read_bytes(), selected.read_bytes())
            self.assertEqual((staged / ENTRY_POINT).read_bytes(), (root / ENTRY_POINT).read_bytes())
            self.assertTrue(all(not (staged / name).exists() for name in excluded))
            resources = studio_fixture(extra={path.relative_to(staged).as_posix(): path.read_bytes()
                                              for path in staged.rglob('*') if path.is_file()})
            verify_resources(resources.__getitem__, source_root=root)
            (root / ENTRY_POINT).write_bytes(b'new application code')
            with self.assertRaisesRegex(ValueError, 'Studio source missing or changed'):
                verify_resources(resources.__getitem__, source_root=root)

    def test_identical_payload_has_stable_archive_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / 'staged'
            staged.mkdir()
            (staged / 'payload.txt').write_bytes(b'same runtime bytes')
            first = write_bundle(staged, root / 'first')
            second = write_bundle(staged, root / 'second')
            self.assertEqual(first, second)
            self.assertEqual((root / 'first' / Path(RESOURCE_ARCHIVE).name).read_bytes(),
                             (root / 'second' / Path(RESOURCE_ARCHIVE).name).read_bytes())


if __name__ == '__main__':
    unittest.main()
