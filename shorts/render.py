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
from .tts import synthesize_synced

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

def draw_band(top_title: str, t: Theme, ai: bool = False) -> Image.Image:
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
    if os.getenv("SCREEN_DISCLOSURE", "off") == "on":  # 기본: 화면엔 안 넣고 제목·설명·고정댓글에 표시
        note = DISCLOSURE + (" · AI로 만든 장면" if ai else "")
        d.text((W // 2, BAND_H - 28), note, font=_font(FONT_R, 26 if ai else 28), fill=t.sub, anchor="mm")
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


def bubble_layer(text: str, t: Theme) -> Image.Image:
    """AI 장면용 말풍선 자막 (흰 풍선 + 진한 글자 + 아래 꼬리)."""
    layer = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = 84
    while size > 56 and d.textlength(text, font=_font(FONT_B, size)) > W - 180:
        size -= 4
    f = _font(FONT_B, size)
    tw = d.textlength(text, font=f)
    box = (W / 2 - tw / 2 - 48, 140 - size / 2 - 34, W / 2 + tw / 2 + 48, 140 + size / 2 + 34)
    d.rounded_rectangle(box, radius=50, fill=(255, 255, 255, 245), outline=t.band, width=5)
    tail_x = W / 2 + tw / 4
    d.polygon([(tail_x - 26, box[3] - 3), (tail_x + 22, box[3] - 3), (tail_x + 34, box[3] + 46)], fill=(255, 255, 255, 245))
    d.line([(tail_x - 26, box[3]), (tail_x + 34, box[3] + 46), (tail_x + 22, box[3])], fill=t.band, width=5)
    d.text((W // 2, 140), text, font=f, fill=t.band, anchor="mm", stroke_width=1, stroke_fill=t.band)
    return layer


def subtitle_layer(text: str, t: Theme) -> Image.Image:
    """영상형용 얇은 자막: 상자 없이 흰 글자 + 검은 테두리, 한 줄. 장면을 덜 가린다."""
    layer = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = int(os.getenv("SUBTITLE_SIZE", "62"))
    while size > 44 and d.textlength(text, font=_font(FONT_B, size)) > W - 140:
        size -= 2
    d.text((W // 2, 150), text, font=_font(FONT_B, size), fill=(255, 255, 255), anchor="mm",
           stroke_width=6, stroke_fill=(20, 20, 20))
    return layer


def list_layer(items: list[str], t: Theme) -> Image.Image:
    """리스트형: 번호 목록 패널 (번호는 노랑, 글자는 흰색)."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    n = max(len(items), 1)
    size = 60 if n <= 8 else 54
    line_h = int(size * 1.32)
    top = 1560 - n * line_h - 50
    d.rounded_rectangle((50, top, W - 50, 1580), radius=36, fill=(*t.band, 225))
    f = _font(FONT_B, size)
    y = top + 30
    for it in items:
        no, _, text = it.partition(".")
        if not text:
            no, text = "", it
        x = 100
        if no:
            d.text((x, y), f"{no.strip()}.", font=f, fill=t.title2, stroke_width=1, stroke_fill=t.title2)
            x += int(d.textlength("00.", font=f)) + 14
        d.text((x, y), text.strip(), font=f, fill=(255, 255, 255), stroke_width=1, stroke_fill=(255, 255, 255))
        y += line_h
    return layer


def _clip_reader(path: Path):
    """AI 클립을 띠 아래 영역(1080x1490)에 '잘리지 않게' 넣어 한 프레임씩 읽는다.
    Flow 워터마크 등 화면 가장자리가 잘리거나 가려지지 않도록 전체를 담고, 남는 양옆은 흐린 확대본으로 채운다."""
    ch = H - BAND_H
    vf = (f"split[a][b];[a]scale={W}:{ch}:force_original_aspect_ratio=increase,crop={W}:{ch},"
          f"boxblur=30:2,eq=brightness=-0.12[bg];[b]scale={W}:{ch}:force_original_aspect_ratio=decrease[fg];"
          f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS}")
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-filter_complex", vf,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = W * ch * 3
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield Image.frombytes("RGB", (W, ch), buf)
    finally:
        proc.kill()
        proc.wait()


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def kenburns(canvas: Image.Image, k: int, p: float) -> Image.Image:
    """컷 번호 k, 컷 안 진행도 p(0~1). 짝수 컷은 확대, 홀수 컷은 축소 + 좌우 패닝. MOTION=static(기본)이면 정지."""
    if os.getenv("MOTION", "static") == "static":
        return canvas
    e = p * p * (3 - 2 * p)  # ease in-out
    z = 1 + (ZOOM - 1) * (e if k % 2 == 0 else 1 - e)
    cw, ch = canvas.size
    vw, vh = cw / z, ch / z
    pan = (e - 0.5) * (cw - vw) * (1 if k % 4 < 2 else -1)
    x0 = (cw - vw) / 2 + pan
    y0 = (ch - vh) / 2
    return canvas.resize((cw, ch), Image.BILINEAR, box=(x0, y0, x0 + vw, y0 + vh))


def _concat_clips(clips: list[Path], segs: list[tuple[int, float]], out: Path) -> Path:
    """Flow 스토리 컷을 장면 순서대로 이어 붙인다. segs = [(컷 번호, 보여줄 초)]. 컷이 짧으면 마지막 프레임 유지."""
    ins, parts = [], []
    for c in clips:
        ins += ["-i", str(c)]
    for i, (k, d) in enumerate(segs):
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps={FPS},"
                     f"scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                     f"tpad=stop_mode=clone:stop_duration={d:.3f},trim=0:{d:.3f},setpts=PTS-STARTPTS[v{i}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[o]"
    _ffmpeg([*ins, "-filter_complex", graph, "-map", "[o]", "-an", "-c:v", "libx264", "-crf", "16", str(out)])
    return out


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
        audio, dur, starts = synthesize_synced(sc.narration, sc.captions, work / f"scene{i:02d}.mp3")
        wav = work / f"scene{i:02d}.wav"
        src = ["-i", str(audio)] if audio else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        _ffmpeg([*src, "-af", f"apad=whole_dur={dur:.3f}", "-t", f"{dur:.3f}", "-ar", "44100", "-ac", "2", str(wav)])
        wavs.append(wav)
        scenes_t.append((clock, clock + dur, min(sc.product_index, len(products) - 1)))
        if starts:  # TTS가 알려준 실제 발화 시각으로 자막을 맞춘다
            ends = starts[1:] + [dur]
            caps += [(clock + (0 if j == 0 else a), clock + b, c)
                     for j, (a, b, c) in enumerate(zip(starts, ends, sc.captions))]
        else:
            caps += _caption_times(sc.captions or [sc.narration], clock, dur)
        clock += dur
    total = clock
    if total > MAX_TOTAL_SEC:
        print(f"[render] 경고: 총 {total:.1f}초로 쇼츠 길이를 넘습니다. 대본을 줄여 주세요.")

    concat = work / "audio.txt"
    concat.write_text("".join(f"file '{w.name}'\n" for w in wavs), encoding="utf-8")
    audio_all = work / "audio.wav"
    _ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(audio_all)])
    from . import bgm as _bgm
    first = products[0]
    track = _bgm.pick(item.slug, getattr(item, "bgm", None) or getattr(first, "bgm", None),
                      (first.idea or {}).get("angle"), script.format)
    if track:
        audio_all = _bgm.mix(audio_all, track, total, work / "audio_bgm.wav")
        print(f"[render] BGM: {track.name}")

    # AI 소스: Veo API 결과(ai_clip.mp4), Flow 등에서 직접 받은 영상(flow/*.mp4), AI 장면 이미지(ai_images/*)
    flow = sorted((out_dir / "flow").glob("*.mp4")) if (out_dir / "flow").exists() else []
    multi = len(flow) > 1
    ai_clip = flow[0] if flow else out_dir / "ai_clip.mp4"
    use_clip = script.format == "ai" and ai_clip.exists()
    ai_imgs = sorted(p for p in (out_dir / "ai_images").glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")) \
        if (out_dir / "ai_images").exists() else []
    use_aiimg = script.format in ("aiimage", "list") and bool(ai_imgs)
    is_list = script.format == "list" and bool(script.list_items)
    list_overlay = list_layer(script.list_items, t) if is_list else None
    if script.format in ("ai", "aiimage", "list") and not (use_clip or use_aiimg):
        print("[render] AI 장면 파일이 없어 상품 사진 전환 화면으로 만듭니다.")
    use_ai = use_clip or use_aiimg
    ai_canvases = [ImageOps.fit(Image.open(p).convert("RGB"), (W, H - BAND_H), Image.LANCZOS) for p in ai_imgs] \
        if use_aiimg else []
    # 같은 AI 이미지의 가까운 컷 (가운데 약간 아래를 1.35배 확대) → 추가 비용 없이 컷 수를 늘린다
    ai_close = [c.resize(c.size, Image.LANCZOS, box=(c.width * 0.13, c.height * 0.2, c.width * 0.87, c.height * 0.94))
                for c in ai_canvases]
    # AI 장면은 후기·단점·CTA 전까지만, 그 뒤는 실제 상품 사진 (클립이 짧으면 마지막 프레임 유지)
    clip_end = next((st for (st, _, _), sc in zip(scenes_t, script.scenes)
                     if sc.kind in (("cta",) if (use_aiimg or multi) else ("review", "downside", "cta"))), total) \
        if use_ai else 0.0
    if use_clip and multi:  # 스토리 컷: 대본 장면마다 맞는 컷을 그 장면 길이만큼 보여준다
        body = [(st, sc) for (st, _, _), sc in zip(scenes_t, script.scenes) if st < clip_end]
        m, n = len(body), len(flow)
        shot_of = [(sc.shot - 1 if sc.shot else round(j * (n - 1) / max(m - 1, 1))) for j, (_, sc) in enumerate(body)]
        shot_of = [min(max(k, 0), n - 1) for k in shot_of]
        segs = []  # (컷 번호, 길이)
        for j, (st, _) in enumerate(body):
            end = body[j + 1][0] if j + 1 < m else clip_end
            if segs and segs[-1][0] == shot_of[j]:
                segs[-1] = (shot_of[j], segs[-1][1] + end - st)
            else:
                segs.append((shot_of[j], end - st))
        ai_clip = _concat_clips(flow, segs, work / "flow_concat.mp4")
    clip_frames = _clip_reader(ai_clip) if use_clip else None
    last_clip = None
    band = draw_band(script.top_title, t, ai=use_ai)
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
        if is_list:  # 리스트형: 이미지 한 장을 천천히 확대, 목록은 고정
            bg = ai_canvases[0] if ai_canvases else imgs[0]
            frame.paste(kenburns(bg, 0, now / max(total, 0.1)), (0, BAND_H))
        elif use_clip and now < clip_end:
            last_clip = next(clip_frames, last_clip)
            frame.paste(last_clip, (0, BAND_H))
        elif use_aiimg and now < clip_end:  # 1.7초마다 컷: AI 장면 이미지를 차례로, 같은 이미지는 넓게→가깝게
            seg = max(clip_end / len(ai_canvases), 0.5)
            ak = min(int(now // seg), len(ai_canvases) - 1)
            ck = int(now // CUT_SEC)
            canvas = ai_canvases[ak] if (ck - int(ak * seg // CUT_SEC)) % 2 == 0 else ai_close[ak]
            frame.paste(kenburns(canvas, ck, (now % CUT_SEC) / CUT_SEC), (0, BAND_H))
        else:
            frame.paste(kenburns(imgs[k % len(imgs)], k, p), (0, BAND_H))
        frame.paste(band, (0, 0))
        if list_overlay is not None:
            frame.paste(list_overlay, (0, 0), list_overlay)
        text = "" if is_list else caps[ci][2]
        if text:
            if text not in cap_cache:
                cap_cache[text] = subtitle_layer(text, t) if use_clip else \
                    bubble_layer(text, t) if use_ai else caption_layer(text, t)
            cy = int(os.getenv("SUBTITLE_Y", "1600")) if use_clip else CAPTION_Y
            frame.paste(cap_cache[text], (0, cy - 150), cap_cache[text])
        proc.stdin.write(frame.tobytes())
    if clip_frames is not None:
        clip_frames.close()
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
