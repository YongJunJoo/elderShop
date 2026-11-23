"""1단계: 상품 정보 → (필요하면 리뷰 조사) → 쇼츠 대본 JSON."""
from __future__ import annotations

import json
from pathlib import Path

import anthropic

from .models import Bundle, Product, ShortScript

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5-5"
SYSTEM = (ROOT / "prompts" / "script_system.md").read_text(encoding="utf-8")
LEARNINGS = ROOT / "data" / "learnings.md"  # 분석 단계가 갱신하는 "잘 된 패턴" 메모


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def research_reviews(product: Product, client: anthropic.Anthropic | None = None) -> str:
    """웹 검색으로 공개 리뷰·블로그를 찾아 장점/불만을 요약한다. 크롤링은 하지 않는다."""
    client = client or _client()
    messages = [{
        "role": "user",
        "content": (
            f"'{product.name}' ({product.category}) 에 대해 한국어 공개 리뷰, 블로그, 커뮤니티 글을 찾아 "
            "실제 구매자들이 자주 말하는 장점 3가지와 불만 3가지를 정리해 주세요. "
            "각 항목에 출처 URL을 붙이고, 근거가 약하면 약하다고 적어 주세요. "
            "그리고 이 종류의 상품을 고를 때 어르신에게 중요한 기준 3가지도 적어 주세요."
        ),
    }]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}]
    for _ in range(4):  # pause_turn이면 이어서 진행
        resp = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("리뷰 조사 요청이 거절되었습니다.")
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    return "\n".join(b.text for b in resp.content if b.type == "text").strip()


def generate_script(item: Product | Bundle, client: anthropic.Anthropic | None = None,
                    fmt: str = "slides") -> ShortScript:
    """단품(Product) 또는 TOP3 묶음(Bundle)으로 대본을 만든다."""
    client = client or _client()
    products = item.products if isinstance(item, Bundle) else [item]

    system = SYSTEM
    if LEARNINGS.exists():
        system += "\n\n## 지난 영상 성과에서 배운 점\n" + LEARNINGS.read_text(encoding="utf-8")

    parts = []
    for i, p in enumerate(products):
        notes = p.review_notes or research_reviews(p, client)
        parts.append(
            f"### 상품 {i} (product_index={i})\n"
            f"{p.model_dump_json(indent=2, exclude={'review_notes', 'images'})}\n\n리뷰 조사 메모:\n{notes}"
        )
    kind = f"묶음(TOP{len(products)}) 영상, 주제: {item.theme}" if isinstance(item, Bundle) else "단품 영상"
    if fmt in ("ai", "aiimage"):
        kind += f", 형식 format=\"{fmt}\""
    user = f"아래 상품으로 {kind} 대본을 써 주세요.\n\n" + "\n\n".join(parts)

    resp = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "high"},
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=ShortScript,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("대본 생성 요청이 거절되었습니다.")
    script = resp.parsed_output
    script.approved = False
    script.format = fmt if fmt in ("ai", "aiimage") else "slides"
    return script


def save_script(script: ShortScript, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "script.json"
    path.write_text(json.dumps(script.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path
