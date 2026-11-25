import io
import tempfile
from pathlib import Path
import unittest

from yt_dlp import YoutubeDL, parse_options
from yt_dlp.cookies import YoutubeDLCookieJar


class TestCookieReloadOptions(unittest.TestCase):
    def test_cli_configuration(self):
        for flags, expected in [
            ([], False),
            (['--cookie-reload'], True),
            (['--cookie-reload', '--no-cookie-reload'], False),
        ]:
            with self.subTest(flags=flags):
                parsed = parse_options(['--ignore-config', *flags, 'https://example.invalid/video'])
                self.assertIs(parsed.ydl_opts['cookie_reload'], expected)

    def test_failed_reload_preserves_existing_jar(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cookies.txt'
            for content in (None, '# Netscape HTTP Cookie File\nmalformed\n'):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_text(content, encoding='utf-8')
                    ydl = YoutubeDL({'cookie_reload': True, 'cookiefile': str(path)}, auto_init=False)
                    jar = YoutubeDLCookieJar(io.StringIO(
                        '# Netscape HTTP Cookie File\n.example.invalid\tTRUE\t/\tFALSE\t0\tfixture\told\n'))
                    jar.load()
                    ydl.cookiejar = jar
                    self.assertFalse(ydl.reload_cookies())
                    self.assertIs(ydl.cookiejar, jar)
                    self.assertEqual([cookie.value for cookie in jar], ['old'])
                    self.assertFalse(ydl._cookie_reload_trial)

    def test_valid_empty_file_is_distinct_from_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cookies.txt'
            path.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')
            ydl = YoutubeDL({'cookie_reload': True, 'cookiefile': str(path)}, auto_init=False)
            jar = YoutubeDLCookieJar(io.StringIO(
                '# Netscape HTTP Cookie File\n.example.invalid\tTRUE\t/\tFALSE\t0\tfixture\told\n'))
            jar.load()
            ydl.cookiejar = jar
            self.assertTrue(ydl.reload_cookies())
            self.assertIs(ydl.cookiejar, jar)
            self.assertEqual(list(jar), [])
