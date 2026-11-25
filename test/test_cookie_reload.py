import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_combined_sources_do_not_mask_incomplete_browser_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cookies.txt'
            header = '# Netscape HTTP Cookie File\n'
            entry = '.example.invalid\tTRUE\t/\tFALSE\t0\tfixture\t{}\n'
            for browser_state in ('empty', 'partial', 'exception', 'complete'):
                with self.subTest(browser_state=browser_state):
                    path.write_text(header + entry.format('new'), encoding='utf-8')
                    ydl = YoutubeDL({'cookie_reload': True, 'cookiefile': str(path),
                                     'cookiesfrombrowser': ('firefox',)}, auto_init=False)
                    jar = YoutubeDLCookieJar(io.StringIO(header + entry.format('old')))
                    jar.load()
                    ydl.cookiejar = jar
                    browser = YoutubeDLCookieJar(io.StringIO(
                        header if browser_state == 'empty' else header + entry.format('browser')))
                    browser.load()
                    browser.extraction_complete = browser_state != 'partial'
                    with patch('yt_dlp.cookies.extract_cookies_from_browser', return_value=browser,
                               side_effect=OSError('synthetic') if browser_state == 'exception' else None):
                        expected = browser_state == 'complete'
                        self.assertIs(ydl.reload_cookies(), expected)
                    self.assertIs(ydl.cookiejar, jar)
                    self.assertEqual([cookie.value for cookie in jar], ['new' if expected else 'old'])
                    self.assertIs(ydl._cookie_reload_trial, expected)
