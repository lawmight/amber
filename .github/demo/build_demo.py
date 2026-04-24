#!/usr/bin/env python3
"""Generate the amber-vs-olive feature demo video.

Output: .github/demo/amber_features_demo.mp4

Workflow:
1. Render still PNG scene cards (title, feature blurbs, section dividers, outro).
2. Produce Ken-Burns style clips from each card via ffmpeg zoompan.
3. Produce zoom/pan clips over the Amber screenshot to highlight specific UI regions.
4. Concatenate everything with xfade transitions between sections and hard cuts inside a section.
"""

import os
import subprocess
import shlex
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Script lives at .github/demo/build_demo.py; repo root is two levels up.
ROOT = Path(__file__).resolve().parent.parent.parent
CARDS = Path("/tmp/demo/cards")
CLIPS = Path("/tmp/demo/clips")
CARDS.mkdir(parents=True, exist_ok=True)
CLIPS.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
FPS = 30

FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

AMBER = (232, 160, 32)          # main amber gold
AMBER_LIGHT = (255, 216, 122)
AMBER_DARK = (160, 96, 16)
BG_DARK = (16, 14, 20)
BG_PANEL = (28, 24, 32)
WHITE = (245, 245, 245)
MUTED = (170, 170, 180)
ACCENT = (122, 195, 255)        # cool blue for 2.0 section


def font(size, bold=False, mono=False):
    if mono:
        return ImageFont.truetype(FONT_MONO, size)
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


def radial_bg(base=BG_DARK, glow=(40, 28, 18), strength=1.0):
    img = Image.new("RGB", (W, H), base)
    # cheap radial glow: big soft ellipse
    overlay = Image.new("RGB", (W, H), base)
    draw = ImageDraw.Draw(overlay)
    cx, cy = int(W * 0.35), int(H * 0.35)
    r = int(max(W, H) * 0.65)
    for i in range(8):
        alpha = int(20 * strength)
        color = tuple(
            max(0, min(255, int(base[c] + (glow[c] - base[c]) * (1 - i / 8))))
            for c in range(3)
        )
        draw.ellipse((cx - r + i * 60, cy - r + i * 60, cx + r - i * 60, cy + r - i * 60), fill=color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=140))
    return Image.blend(img, overlay, 0.7)


def draw_text_center(draw, xy, text, fnt, fill):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((xy[0] - w / 2, xy[1] - h / 2), text, font=fnt, fill=fill)


def draw_text_left(draw, xy, text, fnt, fill):
    draw.text(xy, text, font=fnt, fill=fill)


def draw_corner_brackets(draw, color=AMBER_DARK, thickness=4, inset=80, length=60):
    # four-corner brackets, framing the composition
    x0, y0 = inset, inset
    x1, y1 = W - inset, H - inset
    for (x, y, dx, dy) in (
        (x0, y0, 1, 1), (x1, y0, -1, 1),
        (x0, y1, 1, -1), (x1, y1, -1, -1),
    ):
        draw.line((x, y, x + dx * length, y), fill=color, width=thickness)
        draw.line((x, y, x, y + dy * length), fill=color, width=thickness)


def draw_tag(draw, xy, text, fnt, fg=AMBER, bg=(40, 30, 16), pad_x=18, pad_y=8):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x, y = xy
    rect = (x, y, x + w + pad_x * 2, y + h + pad_y * 2)
    draw.rounded_rectangle(rect, radius=8, fill=bg, outline=fg, width=2)
    draw.text((x + pad_x, y + pad_y - 2), text, font=fnt, fill=fg)
    return rect


# ---------- Scene renderers ----------

def make_title_card():
    img = radial_bg(BG_DARK, (56, 36, 16))
    draw = ImageDraw.Draw(img)
    draw_corner_brackets(draw, color=AMBER_DARK, thickness=3, inset=90, length=70)

    # Logo circle (simple amber gem)
    cx, cy, r = W // 2, int(H * 0.36), 110
    for i in range(r, 0, -1):
        t = i / r
        c = tuple(int(AMBER_LIGHT[k] * (1 - t * 0.6) + AMBER_DARK[k] * t * 0.6) for k in range(3))
        draw.ellipse((cx - i, cy - i, cx + i, cy + i), fill=c)
    # inner highlight
    for i in range(40, 0, -1):
        t = i / 40
        c = tuple(int(255 * (1 - t) + AMBER_LIGHT[k] * t) for k in range(3))
        draw.ellipse((cx - 30 - i, cy - 30 - i, cx - 30 + i, cy - 30 + i), fill=c)

    draw_text_center(draw, (W // 2, int(H * 0.60)), "AMBER", font(180, bold=True), AMBER_LIGHT)
    draw_text_center(draw, (W // 2, int(H * 0.72)), "VIDEO EDITOR", font(48), WHITE)
    draw_text_center(draw, (W // 2, int(H * 0.80)), "a revival of Olive 0.1 — rebuilt on Qt 6 & RHI",
                     font(30), MUTED)
    img.save(CARDS / "01_title.png")


def make_origin_card():
    img = radial_bg(BG_DARK, (32, 22, 14))
    draw = ImageDraw.Draw(img)
    draw_text_center(draw, (W // 2, int(H * 0.32)), "picks up where Olive 0.1 stopped", font(62, bold=True), WHITE)
    draw_text_center(draw, (W // 2, int(H * 0.46)), "2019", font(180, bold=True), AMBER)
    draw_text_center(draw, (W // 2, int(H * 0.66)), "hand-written architecture by MattKC & the Olive team", font(30), MUTED)
    draw_text_center(draw, (W // 2, int(H * 0.72)), "frozen for five years — Amber brings it back", font(30), MUTED)
    img.save(CARDS / "02_origin.png")


def make_section_divider(filename, label, color=AMBER, subtitle=None):
    img = radial_bg(BG_DARK, (color[0] // 4, color[1] // 5, color[2] // 5))
    draw = ImageDraw.Draw(img)
    # Horizontal rule
    draw.line((int(W * 0.15), H // 2 - 100, int(W * 0.85), H // 2 - 100), fill=color, width=2)
    draw.line((int(W * 0.15), H // 2 + 140, int(W * 0.85), H // 2 + 140), fill=color, width=2)
    draw_text_center(draw, (W // 2, H // 2 + 20), label, font(110, bold=True), color)
    if subtitle:
        draw_text_center(draw, (W // 2, H // 2 + 210), subtitle, font(34), MUTED)
    img.save(CARDS / filename)


def make_feature_card(filename, tag, title, bullets, tag_color=AMBER):
    img = radial_bg(BG_DARK, (32, 22, 14) if tag_color == AMBER else (14, 22, 32))
    draw = ImageDraw.Draw(img)
    draw_corner_brackets(draw, color=(tag_color[0] // 2, tag_color[1] // 2, tag_color[2] // 2),
                          thickness=2, inset=80, length=50)

    # tag pill
    draw_tag(draw, (140, 140), tag, font(26, bold=True), fg=tag_color,
             bg=(tag_color[0] // 5, tag_color[1] // 5, tag_color[2] // 5))

    # Title
    draw.text((140, 230), title, font=font(80, bold=True), fill=WHITE)

    # bullets
    y = 400
    for b in bullets:
        # amber accent square
        draw.rectangle((140, y + 14, 158, y + 32), fill=tag_color)
        draw.text((190, y), b, font=font(38), fill=(225, 225, 225))
        y += 80

    img.save(CARDS / filename)


def make_stats_card(filename):
    img = radial_bg(BG_DARK, (32, 22, 14))
    draw = ImageDraw.Draw(img)
    draw_tag(draw, (140, 140), "FOOTPRINT", font(26, bold=True), fg=AMBER,
             bg=(AMBER[0] // 5, AMBER[1] // 5, AMBER[2] // 5))
    draw.text((140, 230), "runs where heavy NLEs can't", font=font(62, bold=True), fill=WHITE)

    stats = [
        ("~3 MB", "binary size"),
        ("~70 MB", "idle RAM at rest"),
        ("OpenGL 3.2+", "minimum GPU"),
    ]
    # Layout-safe: measure each "big" text, size down if it would overflow its column.
    big_fnt = font(96, bold=True)
    small_fnt = font(30)
    col_w = (W - 280) // 3
    y_big = 560
    y_small = 700
    for i, (big, small) in enumerate(stats):
        col_center = 140 + col_w * i + col_w // 2
        # Pick largest size that fits with 40px horizontal margin inside its column.
        size = 96
        while size > 40:
            f = font(size, bold=True)
            bbox = draw.textbbox((0, 0), big, font=f)
            if (bbox[2] - bbox[0]) <= col_w - 40:
                break
            size -= 4
        f = font(size, bold=True)
        draw_text_center(draw, (col_center, y_big), big, f, AMBER)
        draw_text_center(draw, (col_center, y_small), small, small_fnt, MUTED)
        # Subtle divider between columns.
        if i < 2:
            x = 140 + col_w * (i + 1)
            draw.line((x, 520, x, 760), fill=(60, 50, 40), width=1)

    img.save(CARDS / filename)


def make_outro_card():
    img = radial_bg(BG_DARK, (56, 36, 16))
    draw = ImageDraw.Draw(img)
    draw_corner_brackets(draw, color=AMBER_DARK, thickness=3, inset=90, length=70)
    draw_text_center(draw, (W // 2, int(H * 0.32)), "AMBER", font(160, bold=True), AMBER_LIGHT)
    draw_text_center(draw, (W // 2, int(H * 0.46)), "free, open-source — GPLv3", font(40), WHITE)
    draw_text_center(draw, (W // 2, int(H * 0.56)), "1.x feature-complete · 2.0 in active development",
                     font(32), MUTED)
    draw_text_center(draw, (W // 2, int(H * 0.70)), "github.com/baptisterajaut/amber",
                     font(40, mono=True), AMBER)
    img.save(CARDS / "99_outro.png")


# ---------- Scene definitions (kept in one place for easy tweaking) ----------

def generate_cards():
    make_title_card()
    make_origin_card()

    make_section_divider("10_section_foundation.png", "NEW FOUNDATION", color=AMBER,
                         subtitle="rebuilt on top of Olive 0.1's UX")

    make_feature_card(
        "11_rhi.png",
        "RENDERING",
        "Qt RHI — cross-backend GPU",
        [
            "Vulkan · Metal · D3D12 · OpenGL fallback",
            "zero raw OpenGL calls in the codebase",
            "backend auto-selected at runtime",
        ],
    )
    make_feature_card(
        "12_hw_decode.png",
        "DECODE",
        "Hardware video decode",
        [
            "VAAPI on Linux",
            "D3D11VA on Windows",
            "VideoToolbox on macOS",
            "software fallback is automatic",
        ],
    )
    make_feature_card(
        "13_ffmpeg.png",
        "CODECS",
        "FFmpeg 3.4 — 8 support",
        [
            "new channel_layouts & config APIs",
            "AV_FRAME_FLAG_INTERLACED guarded",
            "works with distro ffmpeg or Qt's bundle",
        ],
    )

    make_stats_card("14_footprint.png")

    make_section_divider("20_section_qol.png", "QUALITY OF LIFE", color=AMBER,
                         subtitle="landed on 2.0.x since the fork")

    make_feature_card(
        "21_track_select.png",
        "TIMELINE TOOL",
        "Track Select Tool",
        [
            "click = select everything to the right",
            "Shift+click = every track at once",
            "new tool next to the classic toolbar",
        ],
    )
    make_feature_card(
        "22_shift_arrow.png",
        "SHORTCUT",
        "Shift + Arrow multi-frame jump",
        [
            "alias for Jump Backward / Forward",
            "step count configurable in preferences",
            "matches muscle memory from Premiere / Resolve",
        ],
    )
    make_feature_card(
        "23_bold_tc.png",
        "READABILITY",
        "Bold timecodes in the viewer",
        [
            "heavier font weight on timecode displays",
            "viewer + effect controls",
            "no more squinting at 00:00:11:11",
        ],
    )
    make_feature_card(
        "24_silence.png",
        "AUTOMATION",
        "Auto-cut silence · ripple delete",
        [
            "finds silent ranges on audio clips",
            "ripple-deletes, configurable gap between clips",
            "feedback dialog when no cuts were produced",
        ],
    )

    # ---- 2.0 preview (cool blue accent) ----
    make_section_divider("50_section_2x.png", "COMING IN 2.0.x", color=ACCENT,
                         subtitle="active development — lands progressively via preview builds")

    make_feature_card(
        "51_shadertoy.png",
        "SHADER IMPORT",
        "ShaderToy effect import",
        [
            "drop a .shadertoy file into effects/",
            "iChannel0, iResolution, iTime, iFrame mapped automatically",
            "compiled to .qsb and disk-cached",
            "optional XML sidecar for parameter sliders",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "52_gpu_effects.png",
        "GPU-NATIVE EFFECTS",
        "Frei0r → RHI shaders",
        [
            "brightness · contrast · blur · chroma key",
            "curves · levels · sharpen · basic denoise",
            "~15–20 new GLSL 440 fragment shaders",
            "-DFREI0R_LEGACY keeps the old bridge",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "53_color.png",
        "COLOR",
        "Lift / Gamma / Gain + scopes",
        [
            "3-way color corrector",
            "curves editor",
            "waveform · vectorscope · histogram",
            "pixel sampler and FPS overlay",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "54_new_fx.png",
        "NEW BUILT-IN EFFECTS",
        "more creative tools, shipped",
        [
            "gradient generator (linear / radial, multi-stop)",
            "timer · countdown · progress bar",
            "rich-text stroke on the text effect",
            "EQ · compressor · reverb · delay · limiter",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "55_editing.png",
        "EDITING",
        "timeline workflow upgrades",
        [
            "track mute / solo / lock headers",
            "linked clip vertical drag (V+A together)",
            "layout presets · range markers",
            "effect presets save / load",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "56_render.png",
        "RENDERING PIPELINE",
        "GPU-only, pool everything",
        [
            "FFmpeg → YUV → GPU → readback only for export",
            "RHI pipeline / SRB cache per clip",
            "pre-allocated YUV staging buffers",
            "half-res readback while scrubbing",
        ],
        tag_color=ACCENT,
    )
    make_feature_card(
        "57_amb.png",
        "PROJECT FORMAT",
        ".ove → .amb",
        [
            "new XML schema for GPU effect parameters",
            ".ove import preserved for backward compatibility",
            "hardware encoding: NVENC · VAAPI · QSV",
            "non-modal render queue & batch export",
        ],
        tag_color=ACCENT,
    )

    make_outro_card()


# ---------- ffmpeg helpers ----------

def run(cmd):
    print("[run]", " ".join(shlex.quote(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True)


def zoompan_card(src_png, out_mp4, duration_s, z_start=1.0, z_end=1.04, cx=0.5, cy=0.5):
    """Render a card with a slow zoom. zoompan is very tricky — easier: scale+crop+tween via 'scale' + overlay."""
    frames = int(duration_s * FPS)
    # Use ffmpeg's zoompan filter (input is a single image, looped)
    # zoompan wants frames not seconds
    expr_z = f"'{z_start}+({z_end}-{z_start})*on/{frames}'"
    expr_x = f"'iw*{cx}-(iw/zoom/2)'"
    expr_y = f"'ih*{cy}-(ih/zoom/2)'"
    vf = (
        f"scale=3840:2160:flags=lanczos,"  # supersample before zoompan (it's jittery at native res)
        f"zoompan=z={expr_z}:x={expr_x}:y={expr_y}:d={frames}:s={W}x{H}:fps={FPS}"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(src_png),
        "-t", f"{duration_s}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
        "-r", str(FPS),
        str(out_mp4),
    ])


def screenshot_zoom_clip(src_jpg, out_mp4, duration_s,
                          start_crop, end_crop):
    """Ken-burns over the screenshot between two crop rectangles (x,y,w,h in source pixels).

    We scale the cropped region to WxH using an interpolated crop via 'crop' with expressions driven
    by 'enable' and 't', but simpler: render each frame with a per-frame crop expression.
    """
    frames = int(duration_s * FPS)
    sx, sy, sw, sh = start_crop
    ex, ey, ew, eh = end_crop
    # Crop expressions use n (frame number). Tween linearly.
    # We need to compute x/y/w/h in SOURCE pixel coords.
    # crop=w:h:x:y supports expressions, but w,h must be constants across frames for scale to behave.
    # Easier approach: upscale the source once, then use zoompan-free approach using 'crop' + 'scale'
    # Since source has a fixed aspect, we trust both crops share W:H ratio. Enforce that up front.
    aspect = W / H
    for name, (x, y, w, h) in (("start", start_crop), ("end", end_crop)):
        a = w / h
        if abs(a - aspect) > 0.02:
            raise ValueError(f"{name} crop aspect {a:.3f} mismatches output {aspect:.3f}")

    # Interpolation with n (n is the current frame count from 0 .. frames-1)
    x_expr = f"({sx})+(({ex})-({sx}))*n/{max(frames-1,1)}"
    y_expr = f"({sy})+(({ey})-({sy}))*n/{max(frames-1,1)}"
    w_expr = f"({sw})+(({ew})-({sw}))*n/{max(frames-1,1)}"
    h_expr = f"({sh})+(({eh})-({sh}))*n/{max(frames-1,1)}"

    vf = (
        f"crop=w='{w_expr}':h='{h_expr}':x='{x_expr}':y='{y_expr}':exact=1,"
        f"scale={W}:{H}:flags=lanczos,setsar=1"
    )
    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(src_jpg),
        "-t", f"{duration_s}",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
        "-r", str(FPS),
        str(out_mp4),
    ])


def text_overlay_clip(base_mp4, out_mp4, text, position="bottom",
                      fg="0xFFD87A", bg="0x0b0808"):
    """Put a label strip on top of a clip — fully-opaque dark band, thick amber
    border above and below, bold amber text with black stroke. Picked to read
    clearly even at downscaled resolutions and against dark editor UI."""
    if position == "bottom":
        # drawbox parameter expressions use ih/iw for input dims ("h" refers to
        # the box's own height variable and evaluates to 0 at parse time).
        y_box = "ih-250"
    elif position == "top":
        y_box = "120"
    else:
        y_box = position
    # drawtext allows "h" for main input height.
    y_text = y_box.replace("ih", "h")
    safe_text = text.replace("\\", "\\\\").replace("'", r"\'").replace(":", r"\:")
    vf = (
        f"drawbox=x=40:y={y_box}:w=iw-80:h=160:color={bg}@1.0:t=fill,"
        f"drawbox=x=40:y={y_box}:w=iw-80:h=6:color={fg}@1.0:t=fill,"
        f"drawbox=x=40:y=({y_box})+154:w=iw-80:h=6:color={fg}@1.0:t=fill,"
        f"drawtext=fontfile={FONT_BOLD}:text='{safe_text}':"
        f"fontsize=56:fontcolor={fg}:borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=({y_text})+50"
    )
    run([
        "ffmpeg", "-y", "-i", str(base_mp4),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
        str(out_mp4),
    ])


def concat_xfade(clips, out_mp4, xfade_dur=0.4, transitions=None):
    """Transition every adjacent pair. All inputs assumed same fps/size.

    `transitions` is an optional list of length len(clips)-1 with one of the
    ffmpeg xfade names per gap (e.g. 'fade', 'fadeblack', 'slideleft'). If not
    provided, defaults to 'fadeblack' everywhere — avoids ghosted text since
    the outgoing and incoming frames never appear blended with each other.
    """
    if len(clips) == 1:
        run(["ffmpeg", "-y", "-i", str(clips[0]), "-c", "copy", str(out_mp4)])
        return
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    durs = []
    for c in clips:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(c)],
            capture_output=True, text=True, check=True,
        )
        durs.append(float(r.stdout.strip()))

    if transitions is None:
        transitions = ["fadeblack"] * (len(clips) - 1)
    assert len(transitions) == len(clips) - 1

    graph = []
    prev = "[0:v]"
    prev_dur = durs[0]
    for i in range(1, len(clips)):
        offset = prev_dur - xfade_dur
        out = f"[v{i}]"
        t = transitions[i - 1]
        graph.append(f"{prev}[{i}:v]xfade=transition={t}:duration={xfade_dur}:offset={offset:.3f}{out}")
        prev = out
        prev_dur = prev_dur + durs[i] - xfade_dur
    filtergraph = ";".join(graph)

    run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filtergraph,
        "-map", prev,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "18",
        "-r", str(FPS),
        str(out_mp4),
    ])


# ---------- Scene list (ordered) ----------

SCENE_TRANSITIONS = []  # filled as scenes are added; len = len(scenes)-1


def build_scene_clips():
    screenshot = ROOT / ".github" / "amber.jpg"
    if not screenshot.exists():
        raise FileNotFoundError(screenshot)
    # Source dimensions for the screenshot:
    with Image.open(screenshot) as im:
        src_w, src_h = im.size
    print(f"screenshot size: {src_w}x{src_h}")

    # Helper: full-frame crop respecting output 16:9
    # Source is ~1024x555 which is ~1.845; output is 1.778. We'll either letterbox or crop top/bottom.
    # Easiest: crop centered to 16:9.
    src_ar = src_w / src_h
    out_ar = W / H
    if src_ar > out_ar:
        full_w = int(src_h * out_ar)
        full_x = (src_w - full_w) // 2
        full = (full_x, 0, full_w, src_h)
    else:
        full_h = int(src_w / out_ar)
        full_y = (src_h - full_h) // 2
        full = (0, full_y, src_w, full_h)

    def ar_crop(x, y, w, h):
        """Enforce 16:9 aspect around the requested region, staying inside the source."""
        cx, cy = x + w / 2, y + h / 2
        if w / h > out_ar:
            # too wide → grow h
            h = w / out_ar
        else:
            w = h * out_ar
        # clamp
        x = max(0, min(src_w - w, cx - w / 2))
        y = max(0, min(src_h - h, cy - h / 2))
        return (int(x), int(y), int(w), int(h))

    # Regions of interest in amber.jpg (source is 2083x1212; window chrome ~60px top + 20px sides).
    # We frame each ROI and ar_crop() grows it to 16:9 while clamping inside the source.
    # All values are source pixels. Coordinates are tuned against the current screenshot.
    project = ar_crop(20, 110, 700, 560)            # Project panel (clip list)
    effects = ar_crop(700, 110, 580, 560)           # Effect Controls / Transform
    viewer = ar_crop(1280, 110, 780, 560)           # Viewer pane with subtitle text
    timeline = ar_crop(180, 630, 1800, 440)         # full timeline tracks + waveforms
    toolbar = ar_crop(0, 630, 180, 440)             # left tools column

    scenes = []

    def add(card_name, out_name, duration, zoom_end=1.04, cx=0.5, cy=0.5, trans="fade"):
        out = CLIPS / out_name
        zoompan_card(CARDS / card_name, out, duration, 1.0, zoom_end, cx, cy)
        if scenes:
            SCENE_TRANSITIONS.append(trans)
        scenes.append(out)

    def add_shot(out_name, duration, start, end, label=None, trans="slideleft"):
        base = CLIPS / out_name
        screenshot_zoom_clip(screenshot, base, duration, start, end)
        if scenes:
            SCENE_TRANSITIONS.append(trans)
        scenes.append(base)
        if label:
            overlay = CLIPS / f"lbl_{out_name}"
            text_overlay_clip(base, overlay, label)
            scenes[-1] = overlay

    # ---- Intro ----
    add("01_title.png", "s01_title.mp4", 4.0, zoom_end=1.05)
    add("02_origin.png", "s02_origin.mp4", 3.5, zoom_end=1.05, trans="fade")

    # ---- Section: new foundation ----
    add("10_section_foundation.png", "s10_sect.mp4", 2.5, trans="fadeblack")
    add("11_rhi.png", "s11_rhi.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("12_hw_decode.png", "s12_hw.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("13_ffmpeg.png", "s13_ff.mp4", 3.5, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("14_footprint.png", "s14_foot.mp4", 4.0, zoom_end=1.04, trans="fadeblack")

    # ---- Screenshot tour — slide for continuous pan feel ----
    add_shot("s15_tour_wide.mp4", 3.0, full, full, label="Amber 1.x — the UI today", trans="fadeblack")
    add_shot("s16_tour_viewer.mp4", 3.0, full, viewer, label="Viewer with bold timecodes")
    add_shot("s17_tour_effects.mp4", 3.0, viewer, effects, label="Effect Controls — transform & keyframes")
    add_shot("s18_tour_timeline.mp4", 3.0, effects, timeline, label="Multi-track timeline")
    add_shot("s19_tour_tools.mp4", 3.0, timeline, toolbar, label="Timeline tools — incl. new Track Select")
    add_shot("s20_tour_project.mp4", 3.0, toolbar, project, label="Project panel")

    # ---- Section: quality of life ----
    add("20_section_qol.png", "s25_sect.mp4", 2.5, trans="fadeblack")
    add("21_track_select.png", "s26_ts.mp4", 3.5, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("22_shift_arrow.png", "s27_sa.mp4", 3.2, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("23_bold_tc.png", "s28_tc.mp4", 3.2, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("24_silence.png", "s29_sil.mp4", 3.5, zoom_end=1.05, cx=0.3, trans="fadeblack")

    # ---- Section: 2.0 preview ----
    add("50_section_2x.png", "s50_sect.mp4", 3.0, trans="fadeblack")
    add("51_shadertoy.png", "s51_st.mp4", 4.0, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("52_gpu_effects.png", "s52_gpu.mp4", 4.0, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("53_color.png", "s53_color.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("54_new_fx.png", "s54_fx.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("55_editing.png", "s55_edit.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("56_render.png", "s56_rend.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")
    add("57_amb.png", "s57_amb.mp4", 3.8, zoom_end=1.05, cx=0.3, trans="fadeblack")

    # ---- Outro ----
    add("99_outro.png", "s99_outro.mp4", 4.0, zoom_end=1.03, trans="fadeblack")

    return scenes


def main():
    generate_cards()
    clips = build_scene_clips()

    final = ROOT / ".github" / "demo" / "amber_features_demo.mp4"
    concat_xfade(clips, final, xfade_dur=0.35, transitions=SCENE_TRANSITIONS)
    print("final:", final)


if __name__ == "__main__":
    main()
