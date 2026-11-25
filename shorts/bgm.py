"""배경음악(BGM): Flow Music 등에서 직접 만든 곡을 assets/bgm/ 에 넣어두면 내레이션 아래에 깔린다.

폴더 구조 (분위기 폴더는 선택):
  assets/bgm/bright/*.mp3   밝은 홈쇼핑 느낌 (기본)
  assets/bgm/calm/*.mp3     차분한 정보형 (리스트형 기본)
  assets/bgm/funny/*.mp3    상황극·반전
  assets/bgm/*.mp3          분위기 구분 없이
상품 JSON에 "bgm": "funny" (분위기 폴더) 또는 "bgm": "assets/bgm/xxx.mp3" (파일)로 지정할 수 있다.
"none"이면 BGM 없음. 같은 상품은 항상 같은 곡이 고정으로 골라진다.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BGM_DIR = ROOT / os.getenv("BGM_DIR", "assets/bgm")
EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
ANGLE_MOOD = {"상황극": "funny", "반전": "funny", "후회": "bright", "비교": "bright", "리스트": "calm"}


def _files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.suffix.lower() in EXT) if folder.exists() else []


def pick(slug: str, choice: str | None = None, angle: str | None = None, fmt: str | None = None) -> Path | None:
    if choice == "none" or os.getenv("BGM", "on") == "off":
        return None
    if choice and (ROOT / choice).is_file():
        return ROOT / choice
    mood = choice or ANGLE_MOOD.get(angle or "") or ("calm" if fmt == "list" else "bright")
    pool = _files(BGM_DIR / mood) or _files(BGM_DIR)
    if not pool:
        return None
    return pool[int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(pool)]


def mix(voice: Path, bgm: Path, total: float, out: Path) -> Path:
    """내레이션 아래에 BGM을 깔고, 말할 때는 BGM을 자동으로 줄인다(덕킹). 끝 0.8초 페이드아웃."""
    vol = float(os.getenv("BGM_VOLUME", "0.25"))
    fade = max(total - 0.8, 0)
    graph = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={vol},"
             f"atrim=0:{total:.3f},afade=t=in:d=0.3,afade=t=out:st={fade:.3f}:d=0.8[b];"
             "[0:a]asplit=2[v][sc];"
             "[b][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300[bd];"
             f"[v][bd]amix=inputs=2:duration=first:normalize=0[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-stream_loop", "-1", "-i", str(bgm),
                    "-filter_complex", graph, "-map", "[out]", "-t", f"{total:.3f}", "-ar", "44100", str(out)],
                   check=True)
    return out
