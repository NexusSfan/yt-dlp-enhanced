import hashlib
import os
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

    @unittest.skipIf(os.name == 'nt', 'requires POSIX symlinks')
    def test_nonzip_update_does_not_follow_predictable_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, victim = Path(tmp) / 'fixture', Path(tmp) / 'victim'
            path.write_bytes(b'old')
            path.chmod(0o755)
            victim.write_bytes(b'untouched')
            stage = path.with_suffix('.new')
            stage.symlink_to(victim)
            updater = Updater(Mock(), 'stable')
            updater.filename = str(path)
            with patch('yt_dlp.update.is_non_updateable', return_value=None), patch(
                    'yt_dlp.update.detect_variant', return_value='linux_exe'), patch.object(
                    updater, '_download_asset', return_value=b'new'):
                self.assertTrue(updater.update(UpdateInfo('fixture', checksum=hashlib.sha256(b'new').hexdigest())))
            self.assertEqual(victim.read_bytes(), b'untouched')
            self.assertTrue(stage.is_symlink())
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.read_bytes(), b'new')
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)
            self.assertEqual(set(Path(tmp).iterdir()), {path, victim, stage})

    def test_windows_failed_replacement_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'fixture.exe'
            path.write_bytes(b'old')
            updater = Updater(Mock(), 'stable')
            updater.filename = str(path)
            with patch('yt_dlp.update.is_non_updateable', return_value=None), patch(
                    'yt_dlp.update.detect_variant', return_value='win_exe'), patch.object(
                    updater, '_download_asset', return_value=b'new'), patch(
                    'yt_dlp.update.os.replace', side_effect=OSError('synthetic')):
                self.assertFalse(updater.update(UpdateInfo('fixture', checksum=hashlib.sha256(b'new').hexdigest())))
            self.assertEqual(path.read_bytes(), b'old')
            self.assertEqual(list(Path(tmp).iterdir()), [path])
