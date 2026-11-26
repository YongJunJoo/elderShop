"""사용법:
  python -m shorts ideas [--n 10] [--theme "겨울"]            # 상품 선정 + 상품별 아이디어 → data/ideas_날짜.md
  python -m shorts links                                     # 쿠팡 파트너스 링크 반자동: 검색어 CSV → 붙여넣기 → --import
  python -m shorts images  products/bath-safety-mat.json     # 상품 사진 자동 수집 (쿠팡 파트너스 / 네이버 쇼핑 API)
  python -m shorts script  products/bath-safety-mat.json --format slides  # 25~30초 사진 전환형
  python -m shorts script  products/bath-safety-mat.json --format ai   # AI 장면형 대본
  python -m shorts script  products/bath-safety-mat.json     # 형식은 FORMAT_MIX 비율대로 자동 (기본 이미지형 2 : 영상형 1)
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
            p.add_argument("--format", default=None, choices=["slides", "aiimage", "ai", "list"],
                           help="생략하면 FORMAT_MIX 비율대로 자동 선택. aiimage: 9~12초 AI 이미지, ai: AI 영상, slides: 25~30초")
        if name == "render":
            p.add_argument("--force", action="store_true", help="승인 없이 미리보기 렌더")
        if name == "upload":
            p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
            p.add_argument("--publish-at")
    i = sub.add_parser("ideas")
    i.add_argument("--n", type=int, default=10)
    i.add_argument("--theme", default="")
    lk = sub.add_parser("links", help="쿠팡 파트너스 링크 반자동 연결 (CSV 내보내기/가져오기)")
    lk.add_argument("--import", dest="do_import", action="store_true")
    l1 = sub.add_parser("link", help="상품 한 개에 쿠팡 파트너스 링크 붙이기")
    l1.add_argument("product")
    l1.add_argument("url")
    a = sub.add_parser("analyze")
    a.add_argument("--days", type=int, default=28)
    args = ap.parse_args()

    if args.cmd == "ideas":
        from .ideas import generate_ideas, save_ideas
        save_ideas(generate_ideas(args.n, args.theme))
        return
    if args.cmd in ("links", "link"):
        from .links import export_todo, import_todo, set_link
        if args.cmd == "link":
            set_link(Path(args.product), args.url)
        else:
            import_todo() if args.do_import else export_todo()
        return
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
        from .mix import pick_format
        idea_fmt = (product.idea or {}).get("format") if isinstance(product, Product) else None
        if isinstance(product, Bundle) and not args.format:
            idea_fmt = "list" if len(product.products) >= 5 else None
        if isinstance(product, Product) and product.status == "candidate":
            print("[script] 주의: 아직 검토 전(candidate) 상품입니다. 괜찮으면 JSON의 status를 approved로 바꿔 주세요.")
        fmt = args.format or idea_fmt or pick_format()
        print(f"[script] 형식: {fmt}")
        path = save_script(generate_script(product, fmt=fmt), out)
        print(f"[script] {path} 저장. 검수 후 \"approved\": true 로 바꿔 주세요.")
    elif args.cmd == "aiimage" and os.getenv("IMAGE_SOURCE", "gemini" if os.getenv("GEMINI_API_KEY") else "manual") == "manual":
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        script = _script(out)
        if not script.ai_image_prompts:
            raise SystemExit("대본에 ai_image_prompts가 없습니다. --format aiimage 또는 list 로 대본을 만들어 주세요.")
        folder = out / "ai_images"
        folder.mkdir(parents=True, exist_ok=True)
        tail = (" Vertical 9:16 photorealistic photo of a real Korean home, natural daylight, warm and calm."
                " The product must look exactly like the attached reference photo. No text, no logos."
                " No falls, injuries, hospitals or medical devices.")
        blocks = [f"[{i:02d}.png]\n{pr}{tail}" for i, pr in enumerate(script.ai_image_prompts, 1)]
        (folder / "prompts.txt").write_text("\n\n".join(blocks), encoding="utf-8")
        print("=== 무료로 만들기: Flow(이미지 만들기) 또는 Gemini 앱에 아래를 하나씩 붙여넣기 ===\n")
        print("\n\n".join(blocks))
        if product.images:
            print("\n참고 사진(같이 올리기): " + str(ROOT / product.images[0]))
        print(f"\n받은 이미지를 {folder} 에 01.png, 02.png 이름으로 저장한 뒤 render 를 실행하세요.")
        print("(유료 자동 생성은 .env 에 IMAGE_SOURCE=gemini)")
    elif args.cmd == "aiimage":
        from .ai_images import generate_images
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        generate_images(_script(out), product, out)
    elif args.cmd == "flowprompt":
        item, out = _load(args.product)
        product = item.products[0] if isinstance(item, Bundle) else item
        script = _script(out)
        (out / "flow").mkdir(parents=True, exist_ok=True)
        if script.ai_shots:
            blocks = [f"[{i:02d}.mp4]\n{sh}" for i, sh in enumerate(script.ai_shots, 1)]
            (out / "flow" / "prompts.txt").write_text("\n\n".join(blocks), encoding="utf-8")
            print("=== Flow 스토리 컷 (Veo 3.1 Lite, 9:16, 컷마다 하나씩) ===\n" + "\n\n".join(blocks))
            print(f"\n받은 영상을 {out / 'flow'} 에 01.mp4, 02.mp4 ... 순서 이름으로 넣고 render 하세요.")
            return
        if not script.ai_prompt:
            raise SystemExit("대본에 ai_prompt/ai_shots가 없습니다. --format ai 로 대본을 만들어 주세요.")
        text = (script.ai_prompt + " The product must look exactly like the attached reference image. "
                "Vertical 9:16, natural daylight, realistic Korean home, no on-screen text.")
        (out / "flow" / "prompt.txt").write_text(text, encoding="utf-8")
        print("=== Flow에 붙여넣을 프롬프트 ===\n" + text)
        print("\n참고 이미지(Ingredients/Frames에 올리기): " + ", ".join(str(ROOT / p) for p in product.images[:3]))
        print(f"\n만든 영상(mp4)을 {out / 'flow'} 폴더에 넣고 render 를 실행하세요.")
    elif args.cmd == "aivideo" and __import__("shorts.mix", fromlist=["x"]).video_source() == "flow":
        raise SystemExit("VIDEO_SOURCE=flow 입니다. `python -m shorts flowprompt` 로 프롬프트를 받아 Flow에서 만들어 주세요.\n"
                         "유료 자동 생성을 쓰려면 .env에 VIDEO_SOURCE=veo 를 넣으세요.")
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
