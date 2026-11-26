"""4단계: 영상별 성과 수집 → CSV → Claude가 다음 대본에 쓸 교훈(learnings.md) 갱신."""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import anthropic

from .youtube_auth import youtube, youtube_analytics

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,shares,subscribersGained"


def fetch(days: int = 28) -> Path:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    report = youtube_analytics().reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics=METRICS, dimensions="video", sort="-views", maxResults=200,
    ).execute()
    headers = [h["name"] for h in report.get("columnHeaders", [])]
    rows = report.get("rows", [])

    ids = [r[0] for r in rows]
    titles: dict[str, str] = {}
    for i in range(0, len(ids), 50):
        res = youtube().videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
        titles.update({v["id"]: v["snippet"]["title"] for v in res.get("items", [])})

    # 형식(A/B): 우리가 올린 영상은 out/*/upload.json 에 형식이 기록돼 있다
    formats: dict[str, str] = {}
    for up in (ROOT / "out").glob("*/upload.json"):
        info = json.loads(up.read_text(encoding="utf-8"))
        formats[info.get("id", "")] = info.get("_format", "")

    DATA.mkdir(exist_ok=True)
    path = DATA / f"analytics_{end.isoformat()}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["title", "format", *headers])
        for r in rows:
            w.writerow([titles.get(r[0], ""), formats.get(r[0], ""), *r])
    print(f"[analytics] {len(rows)}개 영상 → {path}")
    return path


def update_learnings(csv_path: Path) -> Path:
    """성과 표를 보고 '잘 된 후킹·카테고리·길이' 교훈을 10줄 이내로 정리. 대본 생성 때 자동 반영된다."""
    client = anthropic.Anthropic()
    prev = (DATA / "learnings.md").read_text(encoding="utf-8") if (DATA / "learnings.md").exists() else "(없음)"
    resp = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": (
            "어르신 대상 생활용품 쇼츠 채널의 영상별 성과 표입니다. 평균 시청 비율(averageViewPercentage)과 "
            "구독 증가를 가장 중요하게 보고, format 열(aiimage=AI 이미지형, ai-flow/ai-veo=AI 영상형, slides=25~30초 사진형)별 차이도 비교해서, 다음 대본 작성에 반영할 교훈을 한국어 bullet 10줄 이내로 써 주세요. "
            "근거가 되는 영상 제목을 괄호로 붙이고, 표본이 적으면 '가설'이라고 표시하세요.\n\n"
            f"기존 교훈:\n{prev}\n\n성과 표(CSV):\n{csv_path.read_text(encoding='utf-8-sig')}"
        )}],
    )
    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    out = DATA / "learnings.md"
    out.write_text(text + "\n", encoding="utf-8")
    print(f"[analytics] 교훈 갱신 → {out}")
    return out
