"""Small in-memory format fixtures for the read-only package inspector."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.build.verify_tmod_package import read_info, read_package, verify


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
        # Avoid .tmod suffix: these fixtures are deliberately not playable mods.
        self.package = self.root / 'container.fixture'

    def check(self, *, version='0.5.1'):
        self.package.write_bytes(fixture(self.files, version=version))
        return verify(self.package, self.source, self.assembly, '2026.8.3.0')

    def test_full_verification(self):
        report = self.check()
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['version'], '0.5.1')
        self.assertEqual(report['fileCount'], 4)
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


if __name__ == '__main__':
    unittest.main()
