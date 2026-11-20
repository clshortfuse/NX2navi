"""Compatibility checks for the retired installer commands and the retained INI helper."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from installer import ini  # noqa: E402


class IniTest(unittest.TestCase):
    EXAMPLE = '[display]\n# vk_present = mailbox\n\n[language]\n# locale = en-US\n# lang = en-US\n# x = 1\n'

    def test_example_line_is_activated(self):
        out = ini.set_language(self.EXAMPLE, 'ru')
        self.assertIn('\nlang = ru\n', out)
        self.assertNotIn('# lang', out)
        self.assertIn('# locale = en-US', out)

    def test_active_line_is_rewritten_and_the_rest_kept(self):
        text = '[display]\nvk_present = fifo\n[language]\n  LANG =  ja  \nfps60 = 0\n'
        out = ini.set_language(text, 'de')
        self.assertEqual(out, '[display]\nvk_present = fifo\n[language]\n  lang =  de\nfps60 = 0\n')
        self.assertEqual(ini.get_language(out), 'de')

    def test_missing_section_is_added(self):
        self.assertEqual(ini.set_language('fps60 = 0\n', 'fr'), 'fps60 = 0\n\n[language]\nlang = fr\n')
        self.assertEqual(ini.set_language('[language]\nlocale = de-DE\n', 'fr'),
                         '[language]\nlang = fr\nlocale = de-DE\n')

    def test_old_chinese_codes_are_written_as_the_canonical_ones(self):
        self.assertEqual(ini.canonical_language('zh-CN'), 'zh-Hans')
        self.assertEqual(ini.canonical_language('zh-TW'), 'zh-Hant')
        self.assertEqual(ini.canonical_language('ja'), 'ja')
        self.assertNotIn('zh-CN', ini.LANGUAGES)
        self.assertNotIn('zh-TW', ini.LANGUAGES)
        out = ini.set_language(self.EXAMPLE, 'zh-CN')
        self.assertEqual(ini.get_language(out), 'zh-Hans')
        self.assertEqual(ini.get_language(ini.set_language(out, 'zh-TW')), 'zh-Hant')

    def test_write_keeps_user_lines(self):
        scratch = ROOT / 'build'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as d:
            d = Path(d)
            example = d / 'nx2navi.ini.example'
            example.write_text(self.EXAMPLE)
            path = ini.write(d / '', 'en-GB', example)
            self.assertEqual(ini.get_language(path.read_text()), 'en-GB')
            path.write_text(path.read_text().replace('# vk_present = mailbox', 'vk_present = fifo'))
            ini.write(d, 'ja', example)
            text = path.read_text()
            self.assertIn('vk_present = fifo', text)
            self.assertEqual(ini.get_language(text), 'ja')


class RetiredInstallerTest(unittest.TestCase):
    def test_old_entrypoints_fail_with_replacement_guidance(self):
        for module in ('installer', 'installer.gui', 'installer.cli'):
            with self.subTest(module=module):
                result = subprocess.run([sys.executable, '-m', module, '--rebuild', 'legacy-install'], cwd=ROOT,
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('NX2navi-Setup', result.stderr)
                self.assertIn('tools\\make_game.py', result.stderr)
                self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
