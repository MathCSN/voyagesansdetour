"""Two fixed French voice samples. No social publication or inference service."""
import argparse
import array
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import wave

HERE = Path(__file__).resolve().parent
STOP = dt.datetime(2027, 9, 14, 21, 59, 59, tzinfo=dt.timezone.utc)
TEXT = ('Vous préparez un voyage au Portugal ? Retrouvez nos guides et leurs sources '
        'sur Voyage Sans Détour. Enregistrez vos idées pour les comparer tranquillement. '
        'Cette narration utilise une voix de synthèse.')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def download(entry, directory):
    # Only immutable public model weights: no API key, account or inference API.
    path = directory / entry['name']
    if path.name != entry['name'] or not entry['url'].startswith(
            'https://huggingface.co/rhasspy/piper-voices/resolve/c10ece1aade47bb51c153c893d14e5bf8e5b7117/'):
        raise ValueError('unexpected_model_source')
    if not 0 < entry['bytes'] <= 80_000_000:
        raise ValueError('model_size_bound')
    with urllib.request.urlopen(entry['url'], timeout=60) as response:
        if response.status != 200 or not response.url.startswith('https://'):
            raise ValueError('model_download_failed')
        raw = response.read(entry['bytes'] + 1)
    if len(raw) != entry['bytes'] or sha(raw) != entry['sha256']:
        raise ValueError('model_fingerprint_changed')
    path.write_bytes(raw)
    return path


def inspect_wav(path):
    if path.stat().st_size > 4_000_000:
        raise ValueError('wav_too_large')
    with wave.open(str(path), 'rb') as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        if (rate, channels, width) != (22050, 1, 2):
            raise ValueError('unexpected_audio_format')
        duration = wav.getnframes() / rate
        samples = array.array('h', wav.readframes(wav.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    if not samples or not 3 <= duration <= 45:
        raise ValueError('audio_duration_outside_bounds')
    rms = math.sqrt(sum(x*x for x in samples) / len(samples))
    clipped = sum(abs(x) >= 32760 for x in samples) / len(samples)
    if rms < 32 or clipped > 0.01:
        raise ValueError('silent_or_clipped_audio')
    return {'durationSeconds': duration, 'sampleRate': rate, 'channels': channels,
            'rms': rms, 'clippedFraction': clipped, 'sha256': sha(path.read_bytes())}


def run(output, now):
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    if now >= STOP:
        return {'status': 'period_ended', 'generated': 0}
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('existing_output_preserved')
    config = json.loads((HERE/'models.json').read_text())
    if config['piperVersion'] != importlib.metadata.version('piper-tts'):
        raise ValueError('piper_version_changed')
    if len(config['voices']) != 2:
        raise ValueError('exactly_two_qualified_models_required')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.voice-pilot-', dir=output.parent) as temp:
        temp = Path(temp)
        result = temp/'result'
        result.mkdir()
        (result/'narration.txt').write_text(TEXT+'\n')
        samples = []
        for voice in config['voices']:
            model_dir = temp/voice['id']
            model_dir.mkdir()
            for entry in voice['files']:
                download(entry, model_dir)
            wav = result/(voice['id']+'.wav')
            subprocess.run([sys.executable, '-m', 'piper', '-m', str(model_dir/(voice['id']+'.onnx')),
                            '-c', str(model_dir/(voice['id']+'.onnx.json')), '-s', str(voice['speaker']),
                            '-f', str(wav), '--length-scale', '1.0', '--sentence-silence', '0.2'],
                           input=TEXT, text=True, check=True, timeout=120,
                           env={**os.environ, 'OMP_NUM_THREADS': '2'})
            samples.append({'voice': voice['id'], 'speaker': voice['speaker'],
                            'datasetLicense': voice['datasetLicense'], **inspect_wav(wav)})
            (result/(voice['id']+'-MODEL_CARD.txt')).write_bytes((model_dir/'MODEL_CARD').read_bytes())
        (result/'CREDITS.md').write_bytes((HERE/'CREDITS.md').read_bytes())
        receipt = {'schemaVersion': 1, 'status': 'audio_samples_not_published',
                   'generatedAt': now.isoformat(), 'generated': len(samples),
                   'textSha256': sha(TEXT.encode()), 'modelsManifestSha256': sha((HERE/'models.json').read_bytes()),
                   'piperVersion': config['piperVersion'],
                   'onnxRuntimeVersion': importlib.metadata.version('onnxruntime'),
                   'modelsRevision': config['revision'], 'samples': samples,
                   'paidInferenceCalls': 0, 'publicationAttempted': False,
                   'listeningReviewComplete': False, 'automaticReelIntegration': False}
        (result/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
        result.rename(output)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output, dt.datetime.now(dt.timezone.utc))))
