"""2단계: 대본 + 상세 이미지 여러 장 + TTS → 1080x1920 세로 영상.

화면 구성
- 상단: 영상 내내 고정되는 2줄 제목 + 광고 고지 (네이비 띠)
- 아래 전체: 상품 이미지가 1.5~2초마다 바뀌며 줌·패닝 (꽉 찬 화면, 뒤는 같은 이미지 흐림)
- 자막: 말에 맞춰 짧게 끊어 나오는 큰 자막
"""
from __future__ import annotations

import io
import os
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .models import Bundle, Product, ShortScript
from .tts import synthesize

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
FONT_B = str(FONTS / "NanumSquareB.ttf")
FONT_R = str(FONTS / "NanumSquareR.ttf")

W, H, FPS = 1080, 1920, 30
BAND_H = 430                      # 상단 제목 띠 높이
CUT_SEC = float(os.getenv("CUT_SEC", "1.7"))   # 이미지 전환 간격
ZOOM = 1.12                       # 컷마다 최대 확대
CAPTION_Y = 1330                  # 자막 중심 (하단 쇼츠 UI 위)
DISCLOSURE = "광고 · 쿠팡 파트너스 활동으로 수수료를 받을 수 있어요"
MAX_TOTAL_SEC = 59.0


@dataclass(frozen=True)
class Theme:
    band: tuple
    title1: tuple
    title2: tuple
    sub: tuple
    cap_box: tuple   # RGBA
    cap_ink: tuple


THEMES = {
    "navy": Theme(band=(13, 33, 61), title1=(255, 255, 255), title2=(255, 205, 41), sub=(160, 178, 204),
                  cap_box=(13, 33, 61, 215), cap_ink=(255, 255, 255)),
}


def current_theme() -> Theme:
    return THEMES.get(os.getenv("VIDEO_THEME", "navy"), THEMES["navy"])


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
    except Exception as e:  # 이미지 하나가 없어도 영상은 만든다
        print(f"[render] 이미지 불러오기 실패 {src}: {e}")
        return None


# ---------- 정지 레이어 ----------

def draw_band(top_title: str, t: Theme) -> Image.Image:
    band = Image.new("RGB", (W, BAND_H), t.band)
    d = ImageDraw.Draw(band)
    lines = (top_title.split("\n") + [""])[:2]
    size = 88
    while size > 60 and max(d.textlength(l, font=_font(FONT_B, size)) for l in lines) > W - 120:
        size -= 4
    f = _font(FONT_B, size)
    d.text((W // 2, 195), lines[0], font=f, fill=t.title1, anchor="mm", stroke_width=2, stroke_fill=t.title1)
    d.text((W // 2, 195 + int(size * 1.2)), lines[1], font=f, fill=t.title2, anchor="mm",
           stroke_width=2, stroke_fill=t.title2)
    d.text((W // 2, BAND_H - 28), DISCLOSURE, font=_font(FONT_R, 28), fill=t.sub, anchor="mm")
    return band


def _edge_color(img: Image.Image) -> tuple[tuple, float]:
    """테두리 픽셀의 평균색과 얼마나 고른지(표준편차). 흰 배경 상품 사진 판별용."""
    from PIL import ImageStat
    w, h = img.size
    strips = [img.crop((0, 0, w, 8)), img.crop((0, h - 8, w, h)), img.crop((0, 0, 8, h)), img.crop((w - 8, 0, w, h))]
    mean = [0.0, 0.0, 0.0]
    std = 0.0
    for st in (ImageStat.Stat(x) for x in strips):
        mean = [m + v / 4 for m, v in zip(mean, st.mean)]
        std = max(std, max(st.stddev))
    return tuple(int(v) for v in mean), std


def image_canvas(img: Image.Image) -> Image.Image:
    """띠 아래 영역(1080x1490)을 꽉 채우는 이미지.
    흰(단색) 배경 상품 사진은 그 색으로 이어 붙이고, 생활 사진은 흐린 확대본을 뒤에 깐다."""
    cw, ch = W, H - BAND_H
    color, std = _edge_color(img)
    if std < 12:
        bg = Image.new("RGB", (cw, ch), color)
    else:
        bg = ImageOps.fit(img, (cw, ch), Image.LANCZOS)
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(40))).enhance(0.6)
    fg = ImageOps.contain(img, (cw, int(ch * 0.8)), Image.LANCZOS)
    bg.paste(fg, ((cw - fg.width) // 2, max(0, (ch - fg.height) // 2 - 140)))
    return bg


def caption_layer(text: str, t: Theme) -> Image.Image:
    layer = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = 92
    while size > 60 and d.textlength(text, font=_font(FONT_B, size)) > W - 140:
        size -= 4
    f = _font(FONT_B, size)
    tw = d.textlength(text, font=f)
    pad_x, pad_y = 40, 28
    box = (W / 2 - tw / 2 - pad_x, 150 - size / 2 - pad_y, W / 2 + tw / 2 + pad_x, 150 + size / 2 + pad_y)
    d.rounded_rectangle(box, radius=28, fill=t.cap_box)
    d.text((W // 2, 150), text, font=f, fill=t.cap_ink, anchor="mm", stroke_width=2, stroke_fill=t.cap_ink)
    return layer


def kenburns(canvas: Image.Image, k: int, p: float) -> Image.Image:
    """컷 번호 k, 컷 안 진행도 p(0~1). 짝수 컷은 확대, 홀수 컷은 축소 + 좌우 패닝."""
    e = p * p * (3 - 2 * p)  # ease in-out
    z = 1 + (ZOOM - 1) * (e if k % 2 == 0 else 1 - e)
    cw, ch = canvas.size
    vw, vh = cw / z, ch / z
    pan = (e - 0.5) * (cw - vw) * (1 if k % 4 < 2 else -1)
    x0 = (cw - vw) / 2 + pan
    y0 = (ch - vh) / 2
    return canvas.resize((cw, ch), Image.BILINEAR, box=(x0, y0, x0 + vw, y0 + vh))


# ---------- 타임라인 ----------

def _caption_times(captions: list[str], start: float, dur: float) -> list[tuple[float, float, str]]:
    weights = [max(1, len(c.replace(" ", ""))) for c in captions] or [1]
    total = sum(weights)
    out, t = [], start
    for c, w in zip(captions or [""], weights):
        d = dur * w / total
        out.append((t, t + d, c))
        t += d
    return out


def _ffmpeg(args: list[str], **kw) -> subprocess.CompletedProcess | subprocess.Popen:
    return subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True, **kw)


def render(script: ShortScript, item: Product | Bundle, out_dir: Path, require_approval: bool = True) -> Path:
    if require_approval and not script.approved:
        raise PermissionError("script.json의 approved가 false입니다. 검수 후 true로 바꾸거나 --force를 쓰세요.")
    t = current_theme()
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    products = item.products if isinstance(item, Bundle) else [item]

    # 상품별 이미지 캔버스 (미리 한 번만 만든다)
    canvases: list[list[Image.Image]] = []
    for p in products:
        imgs = [im for im in (_load_image(s) for s in p.images) if im is not None]
        if not imgs:
            imgs = [Image.new("RGB", (1080, 1080), (230, 233, 238))]
        canvases.append([image_canvas(im) for im in imgs])

    # 음성 + 장면/자막 시간표
    wavs, scenes_t, caps = [], [], []
    clock = 0.0
    for i, sc in enumerate(script.scenes):
        audio, dur = synthesize(sc.narration, work / f"scene{i:02d}.mp3")
        wav = work / f"scene{i:02d}.wav"
        src = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        _ffmpeg([*src, "-af", f"apad=whole_dur={dur:.3f}", "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "2", str(wav)])
        wavs.append(wav)
        scenes_t.append((clock, clock + dur, min(sc.product_index, len(products) - 1)))
        caps += _caption_times(sc.captions or [sc.narration], clock, dur)
        clock += dur
    total = clock
    if total > MAX_TOTAL_SEC:
        print(f"[render] 경고: 총 {total:.1f}초로 쇼츠 길이를 넘습니다. 대본을 줄여 주세요.")

    concat = work / "audio.txt"
    concat.write_text("".join(f"file '{w.name}'\n" for w in wavs), encoding="utf-8")
    audio_all = work / "audio.wav"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(audio_all)])

    band = draw_band(script.top_title, t)
    cap_cache: dict[str, Image.Image] = {}

    final = out_dir / "video.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", str(audio_all), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(final)],
        stdin=subprocess.PIPE,
    )
    n_frames = int(total * FPS) + 1
    si = ci = 0
    for f in range(n_frames):
        now = f / FPS
        while si < len(scenes_t) - 1 and now >= scenes_t[si][1]:
            si += 1
        while ci < len(caps) - 1 and now >= caps[ci][1]:
            ci += 1
        pidx = scenes_t[si][2]
        k = int(now // CUT_SEC)
        p = (now % CUT_SEC) / CUT_SEC
        imgs = canvases[pidx]
        frame = Image.new("RGB", (W, H))
        frame.paste(kenburns(imgs[k % len(imgs)], k, p), (0, BAND_H))
        frame.paste(band, (0, 0))
        text = caps[ci][2]
        if text:
            if text not in cap_cache:
                cap_cache[text] = caption_layer(text, t)
            frame.paste(cap_cache[text], (0, CAPTION_Y - 150), cap_cache[text])
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg 인코딩 실패")
    print(f"[render] {final} ({total:.1f}초)")
    return final


def preview_frame(script: ShortScript, item: Product | Bundle, at_sec: float = 2.0) -> Image.Image:
    """디자인 확인용 정지 화면 한 장 (음성 없이 글자 수로 시간 계산)."""
    t = current_theme()
    products = item.products if isinstance(item, Bundle) else [item]
    imgs = [im for im in (_load_image(s) for s in products[0].images) if im is not None] or \
        [Image.new("RGB", (1080, 1080), (230, 233, 238))]
    k = int(at_sec // CUT_SEC)
    frame = Image.new("RGB", (W, H))
    frame.paste(kenburns(image_canvas(imgs[k % len(imgs)]), k, (at_sec % CUT_SEC) / CUT_SEC), (0, BAND_H))
    frame.paste(draw_band(script.top_title, t), (0, 0))
    cap = script.scenes[0].captions[0] if script.scenes and script.scenes[0].captions else ""
    if cap:
        layer = caption_layer(cap, t)
        frame.paste(layer, (0, CAPTION_Y - 150), layer)
    return frame
