"""상품 사진 자동 수집.

출처 우선순위 (약관상 안전한 공식 API만 사용, 쇼핑몰 페이지 크롤링은 하지 않음)
1. 쿠팡 파트너스 Open API 상품 검색: 대표 이미지 + 파트너스 링크  (COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY)
2. 네이버 쇼핑 검색 API: 대표 이미지                                  (NAVER_CLIENT_ID / NAVER_CLIENT_SECRET)

API는 상품당 대표 이미지 1장만 주므로, 그 사진에서 확대 컷 3~5장을 잘라 4~6장으로 만든다.
결과: assets/products/<slug>/01.jpg ... 와 상품 JSON의 images / affiliate_url 갱신.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from .models import Product

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "elderShop/1.0"}


def _get(url: str, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


# ---------- 출처 ----------

def coupang_search(keyword: str, limit: int = 5) -> list[dict]:
    ak, sk = os.getenv("COUPANG_ACCESS_KEY"), os.getenv("COUPANG_SECRET_KEY")
    if not (ak and sk):
        return []
    path = "/v2/providers/affiliate_open_api/apis/openapi/v1/products/search"
    query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
    signed = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    sig = hmac.new(sk.encode(), f"{signed}GET{path}{query}".encode(), hashlib.sha256).hexdigest()
    auth = f"CEA algorithm=HmacSHA256, access-key={ak}, signed-date={signed}, signature={sig}"
    data = json.loads(_get(f"https://api-gateway.coupang.com{path}?{query}", {"Authorization": auth}))
    items = (data.get("data") or {}).get("productData") or []
    return [{"source": "coupang", "name": i.get("productName"), "image": i.get("productImage"),
             "url": i.get("productUrl"), "price": i.get("productPrice")} for i in items]


def naver_search(keyword: str, limit: int = 5) -> list[dict]:
    cid, cs = os.getenv("NAVER_CLIENT_ID"), os.getenv("NAVER_CLIENT_SECRET")
    if not (cid and cs):
        return []
    q = urllib.parse.urlencode({"query": keyword, "display": limit, "sort": "sim"})
    data = json.loads(_get(f"https://openapi.naver.com/v1/search/shop.json?{q}",
                           {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": cs}))
    strip = lambda s: (s or "").replace("<b>", "").replace("</b>", "")
    return [{"source": "naver", "name": strip(i.get("title")), "image": i.get("image"),
             "url": i.get("link"), "price": i.get("lprice")} for i in data.get("items", [])]


# ---------- 확대 컷 ----------

def _content_box(img: Image.Image) -> tuple[int, int, int, int]:
    """흰/단색 배경을 뺀 상품 영역."""
    bg = Image.new("RGB", img.size, img.getpixel((2, 2)))
    diff = ImageChops.difference(img, bg).convert("L").point(lambda v: 255 if v > 18 else 0)
    return diff.getbbox() or (0, 0, *img.size)


def detail_crops(img: Image.Image, n: int = 4) -> list[Image.Image]:
    """상품 영역 안에서 서로 다른 부분을 확대한 컷 n장 (정사각형)."""
    x0, y0, x1, y1 = _content_box(img)
    bw, bh = x1 - x0, y1 - y0
    side = int(min(bw, bh) * 0.6) or min(img.size)
    spots = [(0.5, 0.5), (0.25, 0.3), (0.75, 0.7), (0.7, 0.3), (0.3, 0.72)]
    out = []
    for fx, fy in spots[:n]:
        cx, cy = x0 + bw * fx, y0 + bh * fy
        l = int(min(max(cx - side / 2, 0), img.width - side))
        t = int(min(max(cy - side / 2, 0), img.height - side))
        out.append(img.crop((l, t, l + side, t + side)).resize((1080, 1080), Image.LANCZOS))
    return out


# ---------- 실행 ----------

def fetch_images(product: Product, product_path: Path, n_total: int = 5) -> list[dict]:
    """사진을 받아 저장하고 상품 JSON을 갱신한다. 후보 목록을 돌려준다(검수용)."""
    keyword = product.name
    candidates = coupang_search(keyword) or naver_search(keyword)
    if not candidates:
        raise RuntimeError("사진 출처 API 키가 없습니다. .env에 쿠팡 파트너스 또는 네이버 쇼핑 API 키를 넣어 주세요.")

    pick = candidates[0]  # 링크로 걸 상품과 같은 상품의 사진만 쓴다
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(_get(pick["image"])))).convert("RGB")
    if min(img.size) < 600:  # API 썸네일이 작으면 키워서 컷 품질을 맞춘다
        img = img.resize((img.width * 1080 // min(img.size), img.height * 1080 // min(img.size)), Image.LANCZOS)

    out_dir = ROOT / "assets" / "products" / product.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = [img] + detail_crops(img, n_total - 1)
    rels = []
    for i, im in enumerate(shots, 1):
        path = out_dir / f"{i:02d}.jpg"
        im.save(path, quality=92)
        rels.append(path.relative_to(ROOT).as_posix())

    data = json.loads(product_path.read_text(encoding="utf-8"))
    data["images"] = rels
    data["image_source"] = {"source": pick["source"], "name": pick["name"], "url": pick["url"]}
    if pick["source"] == "coupang" and not data.get("affiliate_url"):
        data["affiliate_url"] = pick["url"]  # 파트너스 API의 productUrl은 이미 추적 링크
    product_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[images] {pick['source']} '{pick['name']}' → {len(rels)}장 저장 ({out_dir})")
    return candidates
