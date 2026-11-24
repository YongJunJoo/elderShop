"""쿠팡 파트너스 링크 반자동 연결.

1) `python -m shorts links` → data/links_todo.csv (번호·상품·검색어·빈 링크 칸)
2) Jun이 https://partners.coupang.com/#affiliate/ws/link 에서 검색어로 찾아 '링크 생성' → 단축 링크를 CSV '링크' 칸에 붙여넣기
   (상품 사진도 쓰고 싶으면 그 화면의 상품 이미지를 assets/products/<slug>/ 폴더에 저장)
3) `python -m shorts links --import` → products/*.json 의 affiliate_url·images 채움, 이후 단계는 자동
한 개만: `python -m shorts link products/x.json https://link.coupang.com/a/...`
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TODO = ROOT / "data" / "links_todo.csv"
HEADER = ["번호", "slug", "상품", "검색어", "링크"]
OK_URL = re.compile(r"^https://(link\.coupang\.com/|(www\.)?coupang\.com/)")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _products():
    for p in sorted((ROOT / "products").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if "products" not in d:
            yield p, d


def keyword(d: dict) -> str:
    return (d.get("idea") or {}).get("coupang_keyword") or d.get("name", "")


def export_todo() -> Path:
    TODO.parent.mkdir(exist_ok=True)
    rows = [[d.get("link_no") or "", d["slug"], d["name"], keyword(d), ""]
            for _, d in _products() if not d.get("affiliate_url")]
    rows.sort(key=lambda r: (r[0] == "", r[0]))
    with TODO.open("w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글 안 깨지게
        csv.writer(f).writerows([HEADER] + rows)
    print(f"[links] 링크가 필요한 상품 {len(rows)}개 → {TODO}")
    for r in rows:
        print(f"  {r[0]}. {r[2]}  (검색어: {r[3]})")
    print("쿠팡 파트너스 링크 생성 화면에서 검색 → 링크 생성 → '링크' 칸에 붙여넣고 `python -m shorts links --import`")
    return TODO


def set_link(product_path: Path, url: str) -> None:
    url = url.strip()
    if not OK_URL.match(url):
        raise SystemExit(f"쿠팡 링크가 아니에요: {url[:60]}")
    d = json.loads(product_path.read_text(encoding="utf-8"))
    d["affiliate_url"] = url
    folder = ROOT / "assets" / "products" / d["slug"]
    if not d.get("images") and folder.exists():
        d["images"] = [str(p.relative_to(ROOT)) for p in sorted(folder.iterdir()) if p.suffix.lower() in IMG_EXT]
    product_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[links] {d.get('link_no')}. {d['name']} ← 링크 연결" + (f", 사진 {len(d['images'])}장" if d.get("images") else ""))


def import_todo(path: Path = TODO) -> int:
    by_slug = {d["slug"]: p for p, d in _products()}
    n = 0
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            url, slug = (row.get("링크") or "").strip(), row.get("slug")
            if url and slug in by_slug:
                set_link(by_slug[slug], url)
                n += 1
    print(f"[links] {n}개 연결 완료")
    write_profile_list()
    return n


def write_profile_list() -> Path:
    """프로필 링크 페이지(링크트리 등)에 옮길 '번호. 상품명 링크' 목록."""
    items = sorted(((d.get("link_no") or 999, d["name"], d["affiliate_url"]) for _, d in _products()
                    if d.get("affiliate_url")))
    out = ROOT / "data" / "profile_links.md"
    out.write_text("\n".join(f"{no}. {name}  {url}" for no, name, url in items) + "\n", encoding="utf-8")
    print(f"[links] 프로필 링크 목록 → {out}")
    return out
