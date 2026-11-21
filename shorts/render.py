"""2단계: 대본 + 상품 이미지 + TTS → 1080x1920 세로 영상 (템플릿 합성)."""
from __future__ import annotations

import io
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .models import Product, ShortScript
from .tts import synthesize

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
FONT_B = str(FONTS / "NanumSquareB.ttf")
FONT_R = str(FONTS / "NanumSquareR.ttf")

W, H = 1080, 1920
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "어르신 살림 가이드")
DISCLOSURE = "광고 · 쿠팡 파트너스 활동으로 수수료를 받을 수 있어요"
MAX_TOTAL_SEC = 59.0

LABELS = {
    "hook": "잠깐 확인하세요",
    "criteria": "고르는 기준",
    "pros": "구매자들이 꼽은 장점",
    "cons": "구매자들이 꼽은 불만",
    "avoid": "이런 분은 피하세요",
    "cta": "상품 정보",
}


@dataclass(frozen=True)
class Theme:
    bg: tuple
    ink: tuple            # 큰 자막 색
    sub: tuple            # 채널명·고지 색
    accent: tuple         # 라벨·강조 색
    accent_ink: tuple     # 라벨 글자색
    card: tuple           # 상품 사진 카드 배경 (상품 사진은 대부분 흰 배경)
    cons_accent: tuple    # 불만·피하세요 라벨 색
    mark: tuple | None    # 자막 형광펜 색 (None이면 없음)
    label_style: str      # "pill" | "tab"


THEMES = {
    # A. 네이비 홈쇼핑: 진한 남색 배경 + 흰 자막 + 노란 강조. 방송 느낌, 대비 최고
    "navy": Theme(bg=(13, 33, 61), ink=(255, 255, 255), sub=(160, 178, 204), accent=(255, 205, 41),
                  accent_ink=(13, 33, 61), card=(255, 255, 255), cons_accent=(255, 107, 87),
                  mark=None, label_style="pill"),
    # B. 클린 화이트: 흰 배경 + 검정 자막 + 초록 포인트. 정보 채널·신뢰감
    "clean": Theme(bg=(255, 255, 255), ink=(17, 24, 39), sub=(120, 128, 140), accent=(4, 120, 87),
                   accent_ink=(255, 255, 255), card=(255, 255, 255), cons_accent=(194, 65, 12),
                   mark=None, label_style="tab"),
    # C. 따뜻한 크림: 크림 배경 + 진갈색 자막 + 주황 형광펜. 생활·살림 느낌
    "warm": Theme(bg=(250, 244, 235), ink=(43, 33, 24), sub=(150, 130, 110), accent=(217, 72, 15),
                  accent_ink=(255, 255, 255), card=(255, 255, 255), cons_accent=(140, 60, 160),
                  mark=(255, 214, 165), label_style="pill"),
}


def current_theme() -> Theme:
    return THEMES[os.getenv("VIDEO_THEME", "clean")]


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


def _rounded_paste(base: Image.Image, im: Image.Image, xy: tuple[int, int], radius: int) -> None:
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, im.width, im.height), radius=radius, fill=255)
    base.paste(im, xy, mask)


def draw_frame(scene_kind: str, caption: str, idx: int, total: int,
               product_img: Image.Image | None, product_name: str, criteria_no: int | None,
               theme: Theme | None = None) -> Image.Image:
    t = theme or current_theme()
    img = Image.new("RGB", (W, H), t.bg)
    d = ImageDraw.Draw(img)
    M = 72  # 좌우 여백

    # ① 상단: 채널명 + 광고 고지 (쇼츠 상단 UI 아래)
    d.text((M, 150), CHANNEL_NAME, font=_font(FONT_B, 40), fill=t.sub)
    d.text((M, 205), DISCLOSURE, font=_font(FONT_R, 30), fill=t.sub)

    # ② 상품 사진 카드 (그림자 + 둥근 모서리)
    cx0, cy0, cx1, cy1 = M, 280, W - M, 1000
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((cx0, cy0 + 14, cx1, cy1 + 14), radius=40, fill=(0, 0, 0, 60))
    img.paste(shadow.filter(ImageFilter.GaussianBlur(18)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(18)))
    border = (226, 230, 236) if t.bg == t.card else None
    d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=40, fill=t.card, outline=border, width=3)
    if product_img is not None:
        fitted = ImageOps.contain(product_img, (cx1 - cx0 - 80, cy1 - cy0 - 80))
        _rounded_paste(img, fitted, (cx0 + (cx1 - cx0 - fitted.width) // 2,
                                     cy0 + (cy1 - cy0 - fitted.height) // 2), 24)
    else:
        d.text(((cx0 + cx1) // 2, (cy0 + cy1) // 2), product_name,
               font=_font(FONT_B, 56), fill=t.sub, anchor="mm")

    # ③ 장면 라벨
    label = LABELS[scene_kind] + (f" {criteria_no}" if criteria_no else "")
    color = t.cons_accent if scene_kind in ("cons", "avoid") else t.accent
    lf = _font(FONT_B, 54)
    ly = 1070
    if t.label_style == "pill":
        lw = d.textlength(label, font=lf)
        d.rounded_rectangle((M, ly, M + lw + 64, ly + 90), radius=45, fill=color)
        d.text((M + 32, ly + 45), label, font=lf, fill=t.accent_ink if color == t.accent else (255, 255, 255),
               anchor="lm")
    else:  # tab: 왼쪽 굵은 막대 + 색 글자
        d.rectangle((M, ly + 8, M + 12, ly + 82), fill=color)
        d.text((M + 36, ly + 45), label, font=lf, fill=color, anchor="lm")

    # ④ 큰 자막 (왼쪽 정렬, 최대 3줄)
    size = 112
    while True:
        cf = _font(FONT_B, size)
        lines = _wrap(d, caption, cf, W - 2 * M)
        if len(lines) <= 3 or size <= 76:
            break
        size -= 6
    line_h = int(size * 1.32)
    y = 1200
    for line in lines:
        if t.mark:
            tw = d.textlength(line, font=cf)
            d.rectangle((M - 6, y + size * 0.55, M + tw + 6, y + size * 1.02), fill=t.mark)
        d.text((M, y), line, font=cf, fill=t.ink, stroke_width=2, stroke_fill=t.ink)
        y += line_h
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
