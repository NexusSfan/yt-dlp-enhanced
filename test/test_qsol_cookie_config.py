import unittest

from yt_dlp import parse_options


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
