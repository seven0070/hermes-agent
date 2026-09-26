# Moonshine Voice STT (optional)

On-device English transcription. Nothing is downloaded or imported until you enable this plugin and install `moonshine-voice`; its model downloads on first transcription and runs offline afterwards.

On Windows, install into Hermes' Python environment, not a global interpreter:

```powershell
& "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe" -m pip install moonshine-voice
hermes config set stt.provider moonshine
```

If Hermes uses `uv` and its venv has no pip, use `uv pip install --python <Hermes venv python path> moonshine-voice`. Restart Hermes. This plugin transcodes voice-message formats to mono WAV with ffmpeg, then calls Moonshine's `Transcriber`. The model/Windows runtime has not been validated here. Keep the existing `stt.provider` if you want to evaluate it first; restore the previous `stt.provider` in config.

Only English models are selected here. The code and English models are MIT according to the upstream license; legacy non-English models have separate terms. Sources: https://github.com/moonshine-ai/moonshine/blob/main/LICENSE ; https://moonshine-voice.readthedocs.io/en/latest/using/transcription/
