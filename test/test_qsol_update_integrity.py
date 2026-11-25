import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from yt_dlp.update import UpdateInfo, Updater


class TestUpdateIntegrity(unittest.TestCase):
    def test_verify_before_installing(self):
        old, new = b'old fixture', b'new fixture'
        valid = hashlib.sha256(new).hexdigest()
        for checksum, expected in ((None, False), ('bad', False), ('0' * 64, False), (valid, True)):
            with self.subTest(checksum=checksum), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'fixture'
                path.write_bytes(old)
                updater = Updater(Mock(), 'stable')
                updater.filename = str(path)
                with patch('yt_dlp.update.is_non_updateable', return_value=None), patch(
                        'yt_dlp.update.detect_variant', return_value='zip'), patch.object(
                        updater, '_download_asset', return_value=new) as download:
                    self.assertIs(updater.update(UpdateInfo('fixture', checksum=checksum)), expected)
                    self.assertEqual(path.read_bytes(), new if expected else old)
                    if checksum in (None, 'bad'):
                        download.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_interrupted_zip_replacement_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture'
            path.write_bytes(b'old')
            updater = Updater(Mock(), 'stable')
            updater.filename = str(path)
            with patch('yt_dlp.update.is_non_updateable', return_value=None), patch(
                    'yt_dlp.update.detect_variant', return_value='zip'), patch.object(
                    updater, '_download_asset', return_value=b'new'), patch(
                    'yt_dlp.update.os.replace', side_effect=OSError('synthetic')):
                self.assertFalse(updater.update(UpdateInfo('fixture', checksum=hashlib.sha256(b'new').hexdigest())))
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(list(Path(tmp).iterdir()), [path])
