"""장면별 내레이션 음성 만들기.

TTS_PROVIDER=google  : Google Cloud Text-to-Speech (기본, 월 수십만 자 무료 범위)
TTS_PROVIDER=none    : 음성 없이 글자 수로 길이만 계산 (미리보기용)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SILENT_CHARS_PER_SEC = 7.0  # 1.2배 말투 기준 초당 글자 수(공백 제외)
GAP = 0.15  # 장면 사이 쉼(초)


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _google(text: str, path: Path) -> None:
    from google.cloud import texttospeech as tts

    client = tts.TextToSpeechClient()
    resp = client.synthesize_speech(
        input=tts.SynthesisInput(text=text),
        voice=tts.VoiceSelectionParams(
            language_code="ko-KR", name=os.getenv("TTS_VOICE", "ko-KR-Neural2-A")
        ),
        audio_config=tts.AudioConfig(
            audio_encoding=tts.AudioEncoding.MP3,
            speaking_rate=float(os.getenv("TTS_RATE", "1.2")),  # 쇼츠 템포에 맞춰 약간 빠르게
        ),
    )
    path.write_bytes(resp.audio_content)


def synthesize(text: str, path: Path) -> tuple[Path | None, float]:
    """(오디오 경로 또는 None, 길이 초)를 돌려준다. 장면 사이 쉼 포함."""
    provider = os.getenv("TTS_PROVIDER", "google")
    if provider == "none":
        chars = len(text.replace(" ", ""))
        return None, max(1.5, chars / SILENT_CHARS_PER_SEC) + GAP
    if provider == "google":
        _google(text, path)
        return path, audio_duration(path) + GAP
    raise ValueError(f"알 수 없는 TTS_PROVIDER: {provider}")
