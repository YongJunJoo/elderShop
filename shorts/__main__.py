"""사용법:
  python -m shorts images  products/bath-safety-mat.json     # 상품 사진 자동 수집 (쿠팡 파트너스 / 네이버 쇼핑 API)
  python -m shorts script  products/bath-safety-mat.json     # 대본 생성 → out/<slug>/script.json
  python -m shorts script  products/bath-safety-mat.json --format ai   # AI 장면형 대본
  python -m shorts script  products/bath-safety-mat.json --format aiimage  # AI 장면 이미지형 대본 (저렴)
  python -m shorts aiimage products/bath-safety-mat.json     # AI 장면 이미지 3~4장 (편당 약 200원)
  python -m shorts flowprompt products/bath-safety-mat.json  # Flow(무료)에 붙여넣을 프롬프트 → 받은 mp4를 out/<slug>/flow/ 에
  python -m shorts aivideo products/bath-safety-mat.json     # 승인된 AI 대본으로 8초 장면 생성 (Veo API, 유료)
  python -m shorts render  products/bath-safety-mat.json     # 승인된 대본으로 영상 → out/<slug>/video.mp4
  python -m shorts upload  products/bath-safety-mat.json [--publish-at 2026-11-22T19:00:00+09:00]
  python -m shorts analyze [--days 28]                        # 성과 수집 + 교훈 갱신
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .models import Bundle, Product, ShortScript

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """.env를 읽어 환경변수로 넣는다 (윈도우에는 `source`가 없으므로). 이미 있는 값은 덮지 않는다."""
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.split(" #", 1)[0].strip().strip('"').strip("'")
            if value:
                os.environ.setdefault(key.strip(), value)
    # TTS 키 파일이 없으면 변수를 지워 gcloud 로그인(ADC) 인증을 쓰게 한다
    cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if cred:
        p = Path(cred) if Path(cred).is_absolute() else ROOT / cred
        if p.exists():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(p)  # 어느 폴더에서 실행해도 찾게
        else:
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS")


def _load(product_path: str) -> tuple[Product | Bundle, Path]:
    """products/*.json: 단품이면 Product, "products" 목록이 있으면 TOP3 묶음(Bundle)."""
    data = json.loads(Path(product_path).read_text(encoding="utf-8"))
    item = Bundle.model_validate(data) if "products" in data else Product.model_validate(data)
    return item, ROOT / "out" / item.slug


def _script(out_dir: Path) -> ShortScript:
    return ShortScript.model_validate(json.loads((out_dir / "script.json").read_text(encoding="utf-8")))


def main() -> None:
    _load_dotenv()
    ap = argparse.ArgumentParser(prog="shorts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("images", "script", "aiimage", "aivideo", "flowprompt", "render", "upload"):
        p = sub.add_parser(name)
        p.add_argument("product")
        if name == "script":
            p.add_argument("--format", default="slides", choices=["slides", "aiimage", "ai"],
                           help="slides: 사진 전환형(기본), aiimage: AI 장면 이미지(저렴), ai: AI 영상 장면")
        if name == "render":
            p.add_argument("--force", action="store_true", help="승인 없이 미리보기 렌더")
        if name == "upload":
            p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
            p.add_argument("--publish-at")
    a = sub.add_parser("analyze")
    a.add_argument("--days", type=int, default=28)
    args = ap.parse_args()

    if args.cmd == "images":
        from .images import fetch_images
        item, _ = _load(args.product)
        if isinstance(item, Bundle):
            raise SystemExit("묶음은 상품별 JSON에서 images를 먼저 실행한 뒤 묶음 파일에 붙여 주세요.")
        for c in fetch_images(item, Path(args.product)):
            print(f"  후보: [{c['source']}] {c['name']} ({c['price']}원)")
    elif args.cmd == "script":
        from .script_gen import generate_script, save_script
        product, out = _load(args.product)
        path = save_script(generate_script(product, fmt=args.format), out)
        print(f"[script] {path} 저장. 검수 후 \"approved\": true 로 바꿔 주세요.")
    elif args.cmd == "aiimage":
        from .ai_images import generate_images
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        generate_images(_script(out), product, out)
    elif args.cmd == "flowprompt":
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        script = _script(out)
        if not script.ai_prompt:
            raise SystemExit("대본에 ai_prompt가 없습니다. --format ai 로 대본을 만들어 주세요.")
        (out / "flow").mkdir(parents=True, exist_ok=True)
        text = (script.ai_prompt + " The product must look exactly like the attached reference image. "
                "Vertical 9:16, natural daylight, realistic Korean home, no on-screen text.")
        (out / "flow" / "prompt.txt").write_text(text, encoding="utf-8")
        print("=== Flow에 붙여넣을 프롬프트 ===\n" + text)
        print("\n참고 이미지(Ingredients/Frames에 올리기): " + ", ".join(str(ROOT / p) for p in product.images[:3]))
        print(f"\n만든 영상(mp4)을 {out / 'flow'} 폴더에 넣고 render 를 실행하세요.")
    elif args.cmd == "aivideo":
        from .ai_video import generate_clip
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        generate_clip(_script(out), product, out)
    elif args.cmd == "render":
        from .render import render
        product, out = _load(args.product)
        render(_script(out), product, out, require_approval=not args.force)
    elif args.cmd == "upload":
        from .upload import upload
        product, out = _load(args.product)
        script = _script(out)
        if not script.approved:
            raise SystemExit("승인되지 않은 대본은 업로드하지 않습니다.")
        upload(script, out / "video.mp4", out, privacy=args.privacy, publish_at=args.publish_at)
    elif args.cmd == "analyze":
        from .analytics import fetch, update_learnings
        update_learnings(fetch(args.days))


if __name__ == "__main__":
    main()
