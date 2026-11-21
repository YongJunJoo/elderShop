"""2단계: 대본 + 상품 이미지 + TTS → 1080x1920 세로 영상 (템플릿 합성)."""
from __future__ import annotations

import io
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .models import Product, ShortScript
from .tts import synthesize

ROOT = Path(__file__).resolve().parent.parent
FONT_B = str(ROOT / "assets" / "fonts" / "NanumSquareRoundB.ttf")
FONT_R = str(ROOT / "assets" / "fonts" / "NanumSquareRoundR.ttf")

W, H = 1080, 1920
BG = (255, 248, 238)
INK = (25, 25, 25)
HIGHLIGHT = (255, 221, 87)
KIND_STYLE = {
    "hook": ("잠깐!", (214, 40, 40)),
    "criteria": ("고르는 기준", (29, 78, 137)),
    "pros": ("구매자들이 꼽은 장점", (42, 140, 120)),
    "cons": ("구매자들이 꼽은 불만", (220, 100, 60)),
    "avoid": ("이런 분은 피하세요", (110, 50, 170)),
    "cta": ("상품 정보", (214, 40, 40)),
}
DISCLOSURE = "광고 · 쿠팡 파트너스 활동으로 수수료를 받을 수 있어요"
MAX_TOTAL_SEC = 59.0


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _load_image(src: str) -> Image.Image | None:
    try:
        if src.startswith("http"):
            with urllib.request.urlopen(src, timeout=20) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGB")
        p = Path(src)
        if not p.is_absolute():
            p = ROOT / p
        return Image.open(p).convert("RGB")
    except Exception as e:  # 이미지가 없어도 영상은 만든다
        print(f"[render] 이미지 불러오기 실패 {src}: {e}")
        return None


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def draw_frame(scene_kind: str, caption: str, idx: int, total: int,
               product_img: Image.Image | None, product_name: str, criteria_no: int | None) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 광고 고지 (상단, 쇼츠 UI에 가리지 않는 위치)
    d.text((W // 2, 170), DISCLOSURE, font=_font(FONT_R, 34), fill=(120, 110, 100), anchor="mm")

    # 장면 라벨
    label, color = KIND_STYLE[scene_kind]
    if criteria_no:
        label = f"{label} {criteria_no}"
    lf = _font(FONT_B, 54)
    lw = d.textlength(label, font=lf)
    d.rounded_rectangle((W / 2 - lw / 2 - 36, 230, W / 2 + lw / 2 + 36, 320), radius=45, fill=color)
    d.text((W // 2, 275), label, font=lf, fill="white", anchor="mm")

    # 상품 이미지 카드
    card = (90, 370, W - 90, 1010)
    d.rounded_rectangle(card, radius=36, fill="white", outline=(230, 222, 210), width=4)
    if product_img is not None:
        fitted = ImageOps.contain(product_img, (card[2] - card[0] - 60, card[3] - card[1] - 60))
        x = card[0] + (card[2] - card[0] - fitted.width) // 2
        y = card[1] + (card[3] - card[1] - fitted.height) // 2
        img.paste(fitted, (x, y))
    else:
        d.text(((card[0] + card[2]) // 2, (card[1] + card[3]) // 2), product_name,
               font=_font(FONT_B, 56), fill=(150, 140, 130), anchor="mm")

    # 큰 자막 (최대 2~3줄, 노란 형광펜 배경)
    size = 104
    while True:
        cf = _font(FONT_B, size)
        lines = _wrap(d, caption, cf, W - 160)
        if len(lines) <= 3 or size <= 70:
            break
        size -= 6
    line_h = int(size * 1.35)
    y0 = 1250 - (len(lines) * line_h) // 2
    for i, line in enumerate(lines):
        cy = y0 + i * line_h + line_h // 2
        tw = d.textlength(line, font=cf)
        d.rectangle((W / 2 - tw / 2 - 18, cy - size * 0.55, W / 2 + tw / 2 + 18, cy + size * 0.6), fill=HIGHLIGHT)
        d.text((W // 2, cy), line, font=cf, fill=INK, anchor="mm")

    return img


def _ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def render(script: ShortScript, product: Product, out_dir: Path, require_approval: bool = True) -> Path:
    if require_approval and not script.approved:
        raise PermissionError("script.json의 approved가 false입니다. 검수 후 true로 바꾸거나 --force를 쓰세요.")
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    images = [im for im in (_load_image(s) for s in product.images) if im is not None]

    segments: list[Path] = []
    total_sec = 0.0
    crit_no = 0
    for i, scene in enumerate(script.scenes):
        if scene.kind == "criteria":
            crit_no += 1
        pimg = images[i % len(images)] if images else None
        frame = draw_frame(scene.kind, scene.caption, i, len(script.scenes), pimg,
                           script.product_name, crit_no if scene.kind == "criteria" else None)
        png = work / f"scene{i:02d}.png"
        frame.save(png)

        audio, dur = synthesize(scene.narration, work / f"scene{i:02d}.mp3")
        total_sec += dur
        seg = work / f"scene{i:02d}.mp4"
        audio_in = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        _ffmpeg([
            "-loop", "1", "-framerate", "30", "-i", str(png), *audio_in,
            "-t", f"{dur:.2f}",
            "-vf", "fade=t=in:st=0:d=0.2,format=yuv420p",
            "-af", "apad", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(seg),
        ])
        segments.append(seg)

    if total_sec > MAX_TOTAL_SEC:
        print(f"[render] 경고: 총 {total_sec:.1f}초로 쇼츠 권장 길이를 넘습니다. 대본을 줄여 주세요.")

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{s.name}'\n" for s in segments), encoding="utf-8")
    final = out_dir / "video.mp4"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy",
             "-movflags", "+faststart", str(final)])
    print(f"[render] {final} ({total_sec:.1f}초)")
    return final
