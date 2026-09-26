"""Opt-in local Moonshine Voice STT provider for Hermes."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agent.transcription_provider import TranscriptionProvider

logger = logging.getLogger(__name__)


class MoonshineTranscriptionProvider(TranscriptionProvider):
    @property
    def name(self) -> str:
        return "moonshine"

    @property
    def display_name(self) -> str:
        return "Moonshine (offline, English)"

    def is_available(self) -> bool:
        return importlib.util.find_spec("moonshine_voice") is not None

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Moonshine (offline, English)",
            "badge": "Local",
            "tag": "optional",
            "env_vars": [],
        }

    def transcribe(
        self,
        file_path: str,
        *,
        model: Optional[str] = None,
        language: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Transcribe an existing WAV; Hermes may supply other containers.

        Decode with ffmpeg to 16-kHz mono WAV, feed Moonshine's documented
        Transcriber in one non-streaming call. Model assets are loaded lazily
        by Moonshine; no dependency or model download occurs when disabled.
        """
        import subprocess
        import tempfile

        audio = Path(file_path)
        if not audio.is_file():
            return {"success": False, "transcript": "", "provider": self.name, "error": "Audio file not found"}
        if language and language.lower() not in {"en", "en-us", "en-gb"}:
            return {"success": False, "transcript": "", "provider": self.name, "error": "This optional Moonshine provider supports English only"}
        if not self.is_available():
            return {"success": False, "transcript": "", "provider": self.name, "error": "Install moonshine-voice in the Hermes Python environment"}
        try:
            from moonshine_voice import Transcriber, get_model_for_language, load_wav_file
            with tempfile.TemporaryDirectory(prefix="hermes-moonshine-") as temp:
                wav = Path(temp) / "speech.wav"
                subprocess.run(
                    ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio), "-ac", "1", "-ar", "16000", str(wav)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120,
                )
                samples, sample_rate = load_wav_file(str(wav))
                model_path, model_arch = get_model_for_language(wanted_language="en", wanted_model_arch=None)
                transcriber = Transcriber(model_path=model_path, model_arch=model_arch)
                try:
                    result = transcriber.transcribe_without_streaming(samples, sample_rate)
                    # The transcript object exposes lines in the documented API.
                    lines = getattr(result, "lines", [])
                    transcript = " ".join(str(line.text).strip() for line in lines if getattr(line, "text", "")).strip()
                finally:
                    transcriber.close()
            return {"success": bool(transcript), "transcript": transcript, "provider": self.name, **({} if transcript else {"error": "No speech detected"})}
        except Exception as exc:
            logger.warning("Moonshine transcription failed: %s", type(exc).__name__)
            return {"success": False, "transcript": "", "provider": self.name, "error": f"Moonshine transcription failed ({type(exc).__name__})"}


def register(ctx) -> None:
    ctx.register_transcription_provider(MoonshineTranscriptionProvider())
