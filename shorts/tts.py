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


def _mark_positions(narration: str, captions: list[str]) -> list[int] | None:
    """각 자막 조각이 내레이션의 어디서 시작하는지 찾는다 (자막은 내레이션을 줄인 것일 수 있음)."""
    pos, out = 0, []
    for cap in captions:
        key = cap.replace(" ", "")[:2]
        found = -1
        for i in range(pos, len(narration)):
            if narration[i:].replace(" ", "").startswith(key):
                found = i
                break
        if found < 0:
            return None
        out.append(found)
        pos = found + 1
    return out


def _google_synced(narration: str, captions: list[str], path: Path) -> list[float] | None:
    """SSML mark로 자막 조각마다 실제 발화 시작 시각(초)을 받는다. 실패하면 None."""
    from html import escape

    from google.cloud import texttospeech_v1beta1 as tts

    marks = _mark_positions(narration, captions)
    if not marks:
        return None
    ssml, last = "<speak>", 0
    for i, m in enumerate(marks):
        ssml += escape(narration[last:m]) + f'<mark name="c{i}"/>'
        last = m
    ssml += escape(narration[last:]) + "</speak>"
    resp = tts.TextToSpeechClient().synthesize_speech(request=tts.SynthesizeSpeechRequest(
        input=tts.SynthesisInput(ssml=ssml),
        voice=tts.VoiceSelectionParams(language_code="ko-KR", name=os.getenv("TTS_VOICE", "ko-KR-Neural2-A")),
        audio_config=tts.AudioConfig(audio_encoding=tts.AudioEncoding.MP3,
                                     speaking_rate=float(os.getenv("TTS_RATE", "1.2"))),
        enable_time_pointing=[tts.SynthesizeSpeechRequest.TimepointType.SSML_MARK],
    ))
    times = {tp.mark_name: tp.time_seconds for tp in resp.timepoints}
    if len(times) != len(captions):
        return None
    path.write_bytes(resp.audio_content)
    return [times[f"c{i}"] for i in range(len(captions))]


def synthesize_synced(narration: str, captions: list[str], path: Path) -> tuple[Path | None, float, list[float] | None]:
    """음성 + 자막 조각별 시작 시각. 시각을 못 얻으면 None (글자 수 비례로 나눔)."""
    if os.getenv("TTS_PROVIDER", "google") == "google" and captions:
        try:
            starts = _google_synced(narration, captions, path)
            if starts is not None:
                return path, audio_duration(path) + GAP, starts
        except Exception as e:
            print(f"[tts] 자막 싱크 실패, 비례 분할로 대신합니다: {e}")
    audio, dur = synthesize(narration, path)
    return audio, dur, None


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
