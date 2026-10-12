import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave
import pilot


class Guards(unittest.TestCase):
    def test_annual_stop_precedes_all_io(self):
        with patch('pilot.Path.read_text', side_effect=AssertionError('read')), patch('pilot.download', side_effect=AssertionError('network')):
            self.assertEqual(pilot.run(Path('/does-not-exist'), pilot.STOP)['generated'], 0)

    def test_existing_output_preserved_before_download(self):
        with tempfile.TemporaryDirectory() as folder, patch('pilot.download', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError, 'existing_output'):
                pilot.run(Path(folder), dt.datetime(2026,10,12,tzinfo=dt.timezone.utc))

    def test_unknown_profile_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as folder, patch('pilot.download',side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError,'unqualified_synthesis_profile'):
                pilot.run(Path(folder)/'new',dt.datetime(2026,10,12,tzinfo=dt.timezone.utc),synthesis_profile='arbitrary')

    def test_silence_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'empty.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setparams((1,2,22050,0,'NONE','not compressed'))
                wav.writeframes(bytes(22050*2*4))
            with self.assertRaisesRegex(ValueError, 'silent_or_clipped'):
                pilot.inspect_wav(path)

    def test_changed_model_rejected_before_write(self):
        from io import BytesIO
        response=BytesIO(b'bad'); response.status=200; response.url='https://huggingface.co/example'
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen',return_value=response):
            entry={'name':'model.onnx','url':'https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/model.onnx','bytes':3,'sha256':'0'*64}
            with self.assertRaisesRegex(ValueError,'model_fingerprint'):
                pilot.download(entry,Path(folder))
            self.assertEqual(list(Path(folder).iterdir()),[])

if __name__=='__main__':unittest.main()
