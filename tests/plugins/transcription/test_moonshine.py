"""Opt-in Moonshine adapter tests without the optional native SDK/model."""
from __future__ import annotations

import importlib.util
import importlib.machinery
import sys
import types
from pathlib import Path
from unittest.mock import patch


def _provider():
    path = Path(__file__).resolve().parents[3] / 'plugins/transcription/moonshine/__init__.py'
    spec = importlib.util.spec_from_file_location('moonshine_adapter_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.MoonshineTranscriptionProvider()


def test_missing_file():
    result = _provider().transcribe('/not/a/file.wav')
    assert result['success'] is False
    assert result['provider'] == 'moonshine'


def test_transcribes_with_documented_api(tmp_path):
    source = tmp_path / 'voice.ogg'
    source.write_bytes(b'dummy')
    fake = types.ModuleType('moonshine_voice')
    fake.__spec__ = importlib.machinery.ModuleSpec('moonshine_voice', loader=None)
    fake.load_wav_file = lambda _: ([0.1, -0.1], 16000)
    fake.get_model_for_language = lambda **_: ('cached-model', 'arch')
    seen = {}

    class FakeTranscriber:
        def __init__(self, *, model_path, model_arch):
            seen['model'] = model_path
            seen['arch'] = model_arch

        def transcribe_without_streaming(self, samples, sample_rate):
            seen['samples'] = samples
            seen['rate'] = sample_rate
            return types.SimpleNamespace(lines=[types.SimpleNamespace(text='Hello'), types.SimpleNamespace(text='world')])

        def close(self):
            seen['closed'] = True

    fake.Transcriber = FakeTranscriber
    with patch.dict(sys.modules, {'moonshine_voice': fake}), patch('subprocess.run'):
        result = _provider().transcribe(str(source))
    assert result == {'success': True, 'transcript': 'Hello world', 'provider': 'moonshine'}
    assert seen == {'model': 'cached-model', 'arch': 'arch', 'samples': [0.1, -0.1], 'rate': 16000, 'closed': True}
