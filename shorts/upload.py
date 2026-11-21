"""3단계: 완성 영상을 YouTube에 업로드 (예약 공개 가능).

주의: 구글 API 프로젝트가 YouTube API 감사(audit)를 통과하기 전에는
API로 올린 영상이 '비공개'로 고정됩니다. 그동안은 비공개로 올리고 스튜디오에서 공개로 바꾸세요.
"""
from __future__ import annotations

import json
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from .models import ShortScript
from .youtube_auth import youtube

CATEGORY_HOWTO_STYLE = "26"


def upload(script: ShortScript, video: Path, out_dir: Path,
           privacy: str = "private", publish_at: str | None = None) -> str:
    tags = [t.lstrip("#") for t in script.hashtags]
    description = script.description + "\n\n" + " ".join(f"#{t}" for t in tags + ["shorts"])
    status = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,  # AI 음성·AI 대본 사용 고지
    }
    if publish_at:  # 예: 2026-11-22T19:00:00+09:00
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": f"{script.title} #shorts"[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": CATEGORY_HOWTO_STYLE,
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": status,
    }
    req = youtube().videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True),
    )
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    video_id = resp["id"]
    (out_dir / "upload.json").write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[upload] https://youtube.com/shorts/{video_id}")
    print("[upload] 스튜디오에서 '유료 프로모션 포함' 표시를 켜 주세요 (API로 설정 불가).")
    return video_id
