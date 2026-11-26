"""0단계: 상품 선정 + 상품별 아이디어(각도·훅·장면·형식).

Claude가 웹 검색으로 요즘 잘 팔리는 어르신 생활용품을 찾고, 상품마다 쇼츠 아이디어를 붙인다.
결과: data/ideas_<날짜>.md (사람이 검토) + products/<slug>.json 초안 (승인한 것만 다음 단계로)
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import anthropic

from .models import IdeaBatch

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-opus-5-5"
SYSTEM = (ROOT / "prompts" / "ideas_system.md").read_text(encoding="utf-8")


def _existing() -> list[str]:
    return sorted(json.loads(p.read_text(encoding="utf-8")).get("name", "") for p in (ROOT / "products").glob("*.json"))


def generate_ideas(n: int = 10, theme: str = "", client: anthropic.Anthropic | None = None) -> IdeaBatch:
    client = client or anthropic.Anthropic()
    learn = ROOT / "data" / "learnings.md"
    ask = (
        f"어르신 생활용품 쇼츠로 만들 상품 {n}개와 상품별 아이디어를 골라 주세요."
        + (f" 이번 주제: {theme}." if theme else "")
        + " 반드시 쿠팡에서 팔고 쿠팡 파트너스 링크를 만들 수 있는 상품만 고르세요. 쿠팡 인기 상품·리뷰, 최근 쇼츠 사례를 웹에서 찾아 근거를 붙여 주세요."
        + f" 이미 다룬 상품은 빼 주세요: {', '.join(_existing()) or '없음'}."
        + (f"\n\n지난 성과에서 배운 점:\n{learn.read_text(encoding='utf-8')}" if learn.exists() else "")
    )
    messages = [{"role": "user", "content": ask}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}]
    for _ in range(5):
        resp = client.messages.create(model=MODEL, max_tokens=32000, output_config={"effort": "high"},
                                      system=SYSTEM, tools=tools, messages=messages)
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})
    research = "\n".join(b.text for b in resp.content if b.type == "text")
    parsed = client.messages.parse(
        model=MODEL, max_tokens=16000, output_config={"effort": "medium"}, system=SYSTEM,
        messages=[{"role": "user", "content": f"아래 조사 결과를 상품 {n}개 아이디어 목록으로 정리해 주세요.\n\n{research}"}],
        output_format=IdeaBatch,
    )
    if parsed.stop_reason == "refusal":
        raise RuntimeError("아이디어 생성 요청이 거절되었습니다.")
    return parsed.parsed_output


def save_ideas(batch: IdeaBatch) -> Path:
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    today = dt.date.today().isoformat()
    lines = [f"# 상품·아이디어 후보 ({today})", "", "괜찮은 번호를 골라 주세요. 고른 것만 products/ 에 남기고 대본을 만듭니다.", ""]
    taken = {p.stem for p in (ROOT / "products").glob("*.json")}
    next_no = 1 + max([json.loads(p.read_text(encoding="utf-8")).get("link_no") or 0
                       for p in (ROOT / "products").glob("*.json")] or [0])
    from .images import coupang_search
    for i, idea in enumerate(batch.ideas, 1):
        try:
            hits = coupang_search(idea.product_name, 3)
        except Exception as e:  # 키 오류·한도 초과 등
            print(f"[ideas] 쿠팡 검색 실패({idea.product_name}): {type(e).__name__}")
            hits = None
        if hits:
            cp = f"쿠팡 파트너스 검색 OK: {hits[0]['name']} ({hits[0]['price']}원)"
        elif hits == [] and os.getenv("COUPANG_ACCESS_KEY"):
            cp = "쿠팡 파트너스 검색 결과 없음 → 제외 권장"
        else:
            cp = "쿠팡 파트너스 확인 필요 (링크 생성 화면에서 검색)"
        lines += [f"## {i}. {idea.product_name} ({idea.price_range}) · {idea.angle} · {idea.format}",
                  f"- 상단 제목: {idea.top_title.replace(chr(10), ' / ')}",
                  f"- 훅: {idea.hook}", f"- 장면: {idea.scene}", f"- 왜 팔릴까: {idea.why_sells}",
                  f"- 근거: {idea.evidence}", f"- 주의: {idea.risk_notes}", f"- {cp}", ""]
        if idea.slug not in taken:
            prod = {"slug": idea.slug, "name": idea.product_name, "category": idea.category,
                    "link_no": next_no, "images": [], "review_notes": "",
                    "idea": idea.model_dump(), "status": "candidate",
                    "affiliate_url": (hits[0]["url"] if hits else None)}
            (ROOT / "products" / f"{idea.slug}.json").write_text(json.dumps(prod, ensure_ascii=False, indent=2),
                                                                 encoding="utf-8")
            next_no += 1
    path = data / f"ideas_{today}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[ideas] {path} (+ products/*.json 초안, status=candidate)")
    return path
