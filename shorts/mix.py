"""형식 섞기: 영상형(ai)과 이미지형(aiimage) 등을 정해진 비율로 번갈아 만든다.

.env 예: FORMAT_MIX=aiimage:2,ai:1   → 3편 중 2편 이미지형, 1편 영상형
지금까지 만든 대본(out/*/script.json)의 형식 비율을 보고, 목표보다 가장 모자란 형식을 고른다.
영상형 소스: VIDEO_SOURCE=flow (무료, Flow에서 직접 받아 폴더에 넣기) | veo (유료 자동)
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALID = ("aiimage", "ai", "slides")


def target_mix() -> dict[str, float]:
    raw = os.getenv("FORMAT_MIX", "aiimage:2,ai:1")
    mix = {}
    for part in raw.split(","):
        name, _, w = part.strip().partition(":")
        if name in VALID:
            mix[name] = float(w or 1)
    return mix or {"aiimage": 1.0}


def made_so_far() -> Counter:
    c: Counter = Counter()
    for p in (ROOT / "out").glob("*/script.json"):
        try:
            c[json.loads(p.read_text(encoding="utf-8")).get("format", "slides")] += 1
        except Exception:
            pass
    return c


def pick_format() -> str:
    mix, done = target_mix(), made_so_far()
    total_w, n = sum(mix.values()), sum(done[f] for f in mix) + 1
    # 다음 편을 넣었을 때 목표 비율에서 가장 모자란 형식
    return max(mix, key=lambda f: mix[f] / total_w * n - done[f])


def video_source() -> str:
    return os.getenv("VIDEO_SOURCE", "flow")
