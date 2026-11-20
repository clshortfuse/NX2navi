"""Version checks for the standalone game asset tools; no game files needed."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
sys.path.insert(0, str(ROOT / 'tools'))
from mod_files import require_game_111  # noqa: E402


class AssetCliTest(unittest.TestCase):
    def test_exefs_identity_uses_full_build_id(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as work:
            exefs = Path(work)
            main = exefs / 'main'
            header = b'NSO0' + bytes(0x3c) + bytes.fromhex('e0f3ccfaf50065ae4ea01eb5aeb13b1a')
            main.write_bytes(header)
            require_game_111(exefs)
            main.write_bytes(header[:-1] + b'\xff')
            with self.assertRaisesRegex(ValueError, 'not game version 1.1.1'):
                require_game_111(exefs)
            main.write_bytes(header[:-1])
            with self.assertRaisesRegex(ValueError, 'not an NSO'):
                require_game_111(exefs)

    def test_alternate_builder_refuses_to_link_supplied_generated_code(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_game.py'), '--version', 'v111',
                                 '--gen', 'stale-generated-tree'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Use tools/make_game.py for v111 game builds', result.stderr)

    def test_game_builder_refuses_packed_romfs_as_unpacked_input(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as work:
            folder = Path(work)
            exefs = folder / 'exefs'
            romfs = folder / 'romfs'
            exefs.mkdir()
            romfs.mkdir()
            (romfs / 'romfs.bin').touch()
            (romfs / 'index.json').write_text('{}', encoding='utf-8')
            result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'make_game.py'), '--check',
                                     '--exefs', str(exefs), '--romfs', str(romfs)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('packed RomFS from a previous build', result.stderr)

    def test_portable_packager_copies_canonical_files_and_refuses_foreign_exefs(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as work:
            folder = Path(work)
            build, out = folder / 'game', folder / 'portable'
            exe = 'ocarina.exe' if sys.platform == 'win32' else 'ocarina'
            xlate = 'nx2navi_xlate.exe' if sys.platform == 'win32' else 'nx2navi_xlate'
            files = [exe, xlate, 'romfs-index.bin', 'libzstd.dll', 'exefs/main.npdm', 'exefs/sdk',
                     'exefs/subsdk0', 'exefs/rtld', 'romfs-patches-pc/manifest.tsv', 'shader-cache/cache.bin',
                     'romfs/romfs.bin']
            for name in files:
                path = build / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            main = build / 'exefs' / 'main'
            main.write_bytes(b'NSO0' + bytes(0x4c))
            cmd = [sys.executable, str(ROOT / 'tools' / 'package_build.py'), '--build', str(build), '--out', str(out)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertIn('not game version 1.1.1', result.stderr)
            self.assertFalse(out.exists())
            main.write_bytes(b'NSO0' + bytes(0x3c) + bytes.fromhex('e0f3ccfaf50065ae4ea01eb5aeb13b1a'))
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in files[:-1]:
                self.assertEqual((out / name).read_bytes(), (build / name).read_bytes())
            self.assertFalse((out / files[-1]).exists())

    def test_run_refuses_foreign_exefs_before_creating_logs(self):
        BUILD.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=BUILD) as work:
            folder = Path(work)
            (folder / 'ocarina.exe').touch()
            exefs = folder / 'override'
            exefs.mkdir()
            (exefs / 'main').write_bytes(b'NSO0' + bytes(0x4c))
            result = subprocess.run([sys.executable, str(ROOT / 'tools' / 'run_game.py'), work,
                                     '--seconds', '1', '--env', 'NX2NAVI_EXEFS=override'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn('not game version 1.1.1', result.stderr)
            self.assertFalse((folder / 'logs').exists())


if __name__ == '__main__':
    unittest.main()
