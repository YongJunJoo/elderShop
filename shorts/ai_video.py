"""AI 생활 장면 영상 생성 (구글 Veo, Gemini API).

실제 상품 사진을 '참고 이미지'로 넣어 상품 모양을 최대한 그대로 유지한 채,
어르신이 그 상품을 쓰는 일상 장면 8초를 만든다. 결과: out/<slug>/ai_clip.mp4

필요: GEMINI_API_KEY (Google AI Studio에서 발급, 결제 연결 필요)
비용: Veo Fast 기준 8초 한 번에 대략 1~3달러 (모델·요금은 바뀔 수 있음)
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from .models import Product, ShortScript

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.getenv("VEO_MODEL", "veo-3.1-fast-generate-preview")

NEGATIVE = (
    "text, subtitles, watermark, logo, brand names, distorted product, extra limbs, "
    "medical setting, injury, blood, children"
)


def _image(path: str):
    from google.genai import types

    p = Path(path) if Path(path).is_absolute() else ROOT / path
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return types.Image(image_bytes=p.read_bytes(), mime_type=mime)


def generate_clip(script: ShortScript, product: Product, out_dir: Path, seconds: int = 8) -> Path:
    if not script.approved:
        raise PermissionError("승인된 대본만 AI 영상을 만듭니다 (비용이 들어서요).")
    if not script.ai_prompt:
        raise ValueError("대본에 ai_prompt가 없습니다. --format ai 로 대본을 다시 만들어 주세요.")
    if not product.images:
        raise ValueError("상품 사진이 없습니다. 먼저 `python -m shorts images` 를 실행해 주세요.")

    from google import genai
    from google.genai import types

    client = genai.Client()  # GEMINI_API_KEY 환경변수 사용
    refs = [types.VideoGenerationReferenceImage(image=_image(p), reference_type="ASSET")
            for p in product.images[:3]]
    prompt = (
        f"{script.ai_prompt}\n\nThe product must look exactly like the reference images "
        "(same shape, color, and pattern). Vertical 9:16, natural daylight, realistic Korean home, "
        "calm everyday mood. No on-screen text."
    )
    cfg = dict(aspect_ratio="9:16", duration_seconds=seconds, negative_prompt=NEGATIVE,
               person_generation="allow_adult", number_of_videos=1)
    try:
        op = client.models.generate_videos(
            model=MODEL, prompt=prompt, config=types.GenerateVideosConfig(reference_images=refs, **cfg))
    except Exception as e:  # 참고 이미지를 지원하지 않는 모델이면 첫 장면 이미지 방식으로
        print(f"[ai] 참고 이미지 방식 실패({e}); 상품 사진을 첫 장면으로 사용합니다.")
        op = client.models.generate_videos(
            model=MODEL, prompt=prompt, image=_image(product.images[0]), config=types.GenerateVideosConfig(**cfg))

    print(f"[ai] {MODEL} 생성 중... (보통 1~3분)")
    while not op.done:
        time.sleep(10)
        op = client.operations.get(op)
    if op.error:
        raise RuntimeError(f"AI 영상 생성 실패: {op.error}")
    vids = (op.response.generated_videos if op.response else None) or []
    if not vids:
        raise RuntimeError("AI 영상이 만들어지지 않았습니다 (안전 필터에 걸렸을 수 있어요). ai_prompt를 바꿔 보세요.")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ai_clip.mp4"
    client.files.download(file=vids[0].video)
    vids[0].video.save(str(path))
    print(f"[ai] {path}")
    return path
