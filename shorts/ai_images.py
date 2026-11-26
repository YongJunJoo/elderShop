"""AI 생활 장면 '정지 이미지' 생성 (저렴한 기본 AI 방식).

실제 상품 사진을 함께 넣어, 어르신이 그 상품을 쓰는 장면 이미지를 2장(넓은 컷·가까운 컷) 만든다.
렌더 단계에서 줌·패닝으로 움직임을 준다. 결과: out/<slug>/ai_images/01.png ...

필요: GEMINI_API_KEY
비용: 이미지 1장 약 0.04달러(약 50원) → 영상 1편 2장 약 100원 (요금은 바뀔 수 있음)
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image

from .models import Product, ShortScript

ROOT = Path(__file__).resolve().parent.parent
MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")

STYLE = (
    "Photorealistic vertical 9:16 photo of a real Korean home, natural daylight, warm and calm. "
    "The product in the attached photo must appear exactly as shown (same shape, color, pattern). "
    "No text, no logos, no watermark. No falls, injuries, hospitals or medical devices."
)


def generate_images(script: ShortScript, product: Product, out_dir: Path) -> list[Path]:
    if not script.approved:
        raise PermissionError("승인된 대본만 AI 이미지를 만듭니다 (비용이 들어서요).")
    if not script.ai_image_prompts:
        raise ValueError("대본에 ai_image_prompts가 없습니다. --format aiimage 로 대본을 다시 만들어 주세요.")
    list_mode = script.format == "list"
    if not product.images and not list_mode:
        raise ValueError("상품 사진이 없습니다. assets/products/<slug>/ 에 사진을 넣고 links --import 를 해 주세요.")

    from google import genai
    from google.genai import types

    ref = None
    if product.images and not list_mode:  # 리스트형은 주제 장면이라 상품 사진을 넣지 않는다
        ref_path = Path(product.images[0])
        ref = Image.open(ref_path if ref_path.is_absolute() else ROOT / ref_path).convert("RGB")
    style = STYLE if ref is not None else STYLE.replace(
        "The product in the attached photo must appear exactly as shown (same shape, color, pattern). ", "")
    client = genai.Client()
    folder = out_dir / "ai_images"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, scene in enumerate(script.ai_image_prompts, 1):
        resp = client.models.generate_content(
            model=MODEL,
            contents=[f"{scene}\n\n{style}"] + ([ref] if ref is not None else []),
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="9:16")),
        )
        data = next((p.inline_data.data for c in (resp.candidates or []) for p in (c.content.parts or [])
                     if getattr(p, "inline_data", None)), None)
        if not data:
            print(f"[aiimage] {i}번 장면이 만들어지지 않았어요 (안전 필터일 수 있음). 건너뜁니다.")
            continue
        path = folder / f"{i:02d}.png"
        Image.open(io.BytesIO(data)).convert("RGB").save(path)
        paths.append(path)
        print(f"[aiimage] {path}")
    if not paths:
        raise RuntimeError("AI 이미지를 하나도 만들지 못했습니다. ai_image_prompts를 바꿔 보세요.")
    return paths
