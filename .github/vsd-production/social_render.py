"""Drawing for photo reels and carousels: full-frame photo, gradient, readable text.

Pure Pillow, deterministic. Text wrapped in *asterisks* is drawn in the accent
colour (prices, durations, line names). Layout keeps clear of the Instagram
interface: nothing important in the top 110 px, the bottom 320 px or the right
130 px of a reel.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REEL_SIZE = (1080, 1920)
SLIDE_SIZE = (1080, 1350)
FPS = 30
ACCENT = (255, 214, 64)
INK = (17, 27, 48)
WHITE = (255, 255, 255)
MARGIN = 72
REEL_RIGHT_SAFE = 130
REEL_TEXT_BOTTOM = 1590
SLIDE_TEXT_BOTTOM = 1270
CROSSFADE_FRAMES = 8
TEXT_INTRO_FRAMES = 11
ZOOM_RANGE = 0.09
HEADLINE_MAX = {"hook": 118, "scene": 96, "cta": 100}
HEADLINE_MIN = 60
DETAIL_SIZE = 44
TAG_SIZE = 27
KICKER_SIZE = 29
SCRIM_ALPHA = 125


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class Fonts:
    regular: str
    bold: str
    serif: str


@lru_cache(maxsize=64)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=32)
def photo(path: str) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def segments(line: str) -> list[tuple[str, bool]]:
    """Split 'Tram *3,30 €*' into [('Tram ', False), ('3,30 €', True)]."""
    parts = line.split("*")
    if len(parts) % 2 == 0:
        raise LayoutError("Unbalanced highlight markers: " + line)
    return [(part, index % 2 == 1) for index, part in enumerate(parts) if part]


def plain(line: str) -> str:
    return line.replace("*", "")


def text_width(draw: ImageDraw.ImageDraw, line: str, face: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(plain(line), font=face)


def wrap(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    # Ordinary spaces only: a non-breaking space keeps "1 h 37" or "9 €" on one line.
    words, lines, current = [w for w in re.split(r"[ \t\n]+", text) if w], [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and text_width(draw, candidate, face) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def ease(t: float) -> float:
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))


def cover_box(image_size, target, zoom, center):
    """Source box with the target aspect, zoomed and clamped inside the photo."""
    iw, ih = image_size
    tw, th = target
    scale = max(tw / iw, th / ih) * zoom
    bw, bh = tw / scale, th / scale
    cx = min(max(center[0] * iw, bw / 2), iw - bw / 2)
    cy = min(max(center[1] * ih, bh / 2), ih - bh / 2)
    return (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)


def photo_frame(path: str, target, focus, t: float, index: int) -> Image.Image:
    """Slow Ken Burns move: alternate zoom-in and zoom-out, drifting across the focus."""
    image = photo(path)
    progress = ease(t)
    zoom_in = index % 2 == 0
    zoom = 1.0 + ZOOM_RANGE * (progress if zoom_in else 1 - progress)
    drift = (-0.06 + 0.12 * progress) if index % 3 != 1 else (0.06 - 0.12 * progress)
    center = (focus[0] + drift, focus[1])
    box = cover_box(image.size, target, zoom, center)
    return image.resize(target, Image.Resampling.BILINEAR, box=box)


def gradient(size, start_y: int, strength: float, top: int = 300, top_strength: float = 0.55) -> Image.Image:
    width, height = size
    column = Image.new("L", (1, height), 0)
    pixels = column.load()
    for y in range(height):
        value = 0.0
        if y > start_y:
            value = strength * ((y - start_y) / (height - start_y)) ** 0.7
        if y < top:
            value = max(value, top_strength * (1 - y / top) ** 1.6)
        pixels[0, y] = int(255 * min(1.0, value))
    mask = column.resize(size)
    layer = Image.new("RGBA", size, (8, 12, 24, 0))
    layer.putalpha(mask)
    return layer


def draw_rich(draw: ImageDraw.ImageDraw, xy, line: str, face, fill, accent=ACCENT):
    x, y = xy
    for text, highlighted in segments(line):
        draw.text((x, y), text, font=face, fill=accent if highlighted else fill)
        x += draw.textlength(text, font=face)


def pill(draw: ImageDraw.ImageDraw, x, y, label: str, face, fill, text_fill, padding=(22, 12)):
    w = draw.textlength(label, font=face)
    ascent, descent = face.getmetrics()
    h = ascent + descent
    draw.rounded_rectangle((x, y, x + w + 2 * padding[0], y + h + 2 * padding[1]), radius=(h + 2 * padding[1]) // 2, fill=fill)
    draw.text((x + padding[0], y + padding[1]), label, font=face, fill=text_fill)
    return w + 2 * padding[0], h + 2 * padding[1]


def fit_headline(draw, lines, face_path: str, role: str, width: int) -> ImageFont.FreeTypeFont:
    size = HEADLINE_MAX[role]
    while size >= HEADLINE_MIN:
        face = font(face_path, size)
        if max(text_width(draw, line, face) for line in lines) <= width:
            return face
        size -= 4
    raise LayoutError("Headline too long for the frame: " + " / ".join(lines))


def text_layer(scene: dict, size, fonts: Fonts, role: str, bottom: int, width: int, button: str | None) -> Image.Image:
    """Kicker, headline, detail and source tag, stacked from the bottom up, with a soft shadow."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    probe = ImageDraw.Draw(layer)
    headline_face = fit_headline(probe, scene["headline"], fonts.bold, role, width)
    detail_face = font(fonts.regular, DETAIL_SIZE)
    tag_face = font(fonts.bold, TAG_SIZE)
    kicker_face = font(fonts.bold, KICKER_SIZE)
    button_face = font(fonts.bold, 36)
    detail_lines = wrap(probe, scene["detail"], detail_face, width) if scene.get("detail") else []
    if len(detail_lines) > 3:
        raise LayoutError("Detail longer than three lines: " + scene["detail"])
    head_step = int(headline_face.size * 1.08)
    detail_step = int(DETAIL_SIZE * 1.3)
    blocks = [("kicker", 64), *[("headline", head_step)] * len(scene["headline"])]
    if detail_lines:
        blocks += [("gap", 18)] + [("detail", detail_step)] * len(detail_lines)
    if button:
        blocks += [("gap", 34), ("button", 76)]
    if scene.get("tag"):
        blocks += [("gap", 26), ("tag", 52)]
    y = bottom - sum(height for _, height in blocks)
    # Soft dark scrim behind the whole block: legible on any photo, no hard box.
    scrim = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(scrim).rounded_rectangle((MARGIN - 60, y - 50, MARGIN + width + 60, bottom + 40), radius=80, fill=(6, 10, 20, SCRIM_ALPHA))
    scrim = scrim.filter(ImageFilter.GaussianBlur(48))
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow_draw, draw = ImageDraw.Draw(shadow), ImageDraw.Draw(layer)
    headline, detail = iter(scene["headline"]), iter(detail_lines)
    for kind, height in blocks:
        if kind == "kicker":
            pill(draw, MARGIN, y, scene["kicker"].upper(), kicker_face, ACCENT, INK, padding=(18, 9))
        elif kind == "headline":
            line = next(headline)
            draw_rich(shadow_draw, (MARGIN, y), line, headline_face, (0, 0, 0, 200), accent=(0, 0, 0, 200))
            draw_rich(draw, (MARGIN, y), line, headline_face, WHITE)
        elif kind == "detail":
            line = next(detail)
            draw_rich(shadow_draw, (MARGIN, y), line, detail_face, (0, 0, 0, 220), accent=(0, 0, 0, 220))
            draw_rich(draw, (MARGIN, y), line, detail_face, (242, 244, 248))
        elif kind == "button":
            pill(draw, MARGIN, y, button, button_face, ACCENT, INK, padding=(28, 16))
        elif kind == "tag":
            pill(draw, MARGIN, y + 4, scene["tag"], tag_face, (255, 255, 255, 46), (255, 255, 255, 235), padding=(16, 8))
        y += height
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    return Image.alpha_composite(Image.alpha_composite(scrim, shadow), layer)


def chrome_layer(size, fonts: Fonts, index: int, total: int, carousel: bool) -> Image.Image:
    """Brand wordmark and progress (reel) or slide counter (carousel)."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    brand = font(fonts.serif, 34)
    if carousel:
        draw.text((MARGIN, 58), "Voyage Sans Détour", font=brand, fill=(255, 255, 255, 235))
        label = f"{index + 1}/{total}"
        face = font(fonts.bold, 28)
        w = draw.textlength(label, font=face)
        pill(draw, size[0] - MARGIN - w - 36, 56, label, face, (0, 0, 0, 120), WHITE, padding=(18, 8))
    else:
        draw.text((MARGIN, 128), "Voyage Sans Détour", font=brand, fill=(255, 255, 255, 235))
    return layer


def progress_bar(frame: Image.Image, index: int, total: int, fraction: float) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    gap, top, height = 10, 92, 6
    span = (frame.width - 2 * MARGIN - gap * (total - 1)) / total
    for n in range(total):
        x0 = MARGIN + n * (span + gap)
        draw.rounded_rectangle((x0, top, x0 + span, top + height), radius=3, fill=(255, 255, 255, 90))
        filled = 1.0 if n < index else fraction if n == index else 0.0
        if filled > 0:
            draw.rounded_rectangle((x0, top, x0 + max(height, span * filled), top + height), radius=3, fill=(255, 255, 255, 240))


def role_of(index: int, total: int, scene: dict) -> str:
    if scene.get("cta"):
        return "cta"
    return "hook" if index == 0 else "scene"


@dataclass(frozen=True)
class PreparedScene:
    photo: str
    focus: tuple
    overlay: Image.Image
    text: Image.Image
    frames: int


def prepare(scenes: list[dict], photo_paths: list[str], fonts: Fonts, size, carousel: bool, button: str) -> list[PreparedScene]:
    total = len(scenes)
    bottom = SLIDE_TEXT_BOTTOM if carousel else REEL_TEXT_BOTTOM
    width = size[0] - 2 * MARGIN - (0 if carousel else REEL_RIGHT_SAFE)
    shade = gradient(size, int(size[1] * (0.38 if carousel else 0.42)), 0.9)
    prepared = []
    for index, (scene, path) in enumerate(zip(scenes, photo_paths)):
        role = role_of(index, total, scene)
        overlay = Image.alpha_composite(shade, chrome_layer(size, fonts, index, total, carousel))
        text = text_layer(scene, size, fonts, role, bottom, width, button if role == "cta" else None)
        frames = round(scene.get("seconds", 0) * FPS)
        prepared.append(PreparedScene(path, tuple(scene.get("focus", (0.5, 0.5))), overlay, text, frames))
    return prepared


def compose(scene: PreparedScene, index: int, size, t: float, text_alpha: float = 1.0, lift: int = 0) -> Image.Image:
    base = photo_frame(scene.photo, size, scene.focus, t, index).convert("RGBA")
    base = Image.alpha_composite(base, scene.overlay)
    text = scene.text
    if text_alpha < 1.0 or lift:
        faded = text.copy()
        faded.putalpha(text.getchannel("A").point(lambda value: int(value * text_alpha)))
        text = Image.new("RGBA", size, (0, 0, 0, 0))
        text.paste(faded, (0, lift))
    return Image.alpha_composite(base, text)


def slide(scene: PreparedScene, index: int) -> Image.Image:
    return compose(scene, index, SLIDE_SIZE, 0.5).convert("RGB")


def reel_frames(prepared: list[PreparedScene]):
    """Yield RGB frames: text slides in on each scene, scenes crossfade."""
    total = len(prepared)
    previous_last = None
    for index, scene in enumerate(prepared):
        for n in range(scene.frames):
            t = n / max(1, scene.frames - 1)
            intro = 1.0 if index == 0 else min(1.0, n / TEXT_INTRO_FRAMES)
            frame = compose(scene, index, REEL_SIZE, t, text_alpha=ease(intro), lift=int(36 * (1 - ease(intro))))
            if previous_last is not None and n < CROSSFADE_FRAMES:
                frame = Image.blend(previous_last, frame, (n + 1) / (CROSSFADE_FRAMES + 1))
            progress_bar(frame, index, total, (n + 1) / scene.frames)
            if n == scene.frames - 1:
                previous_last = frame.copy()
            yield frame.convert("RGB")


def still(scene: PreparedScene, index: int, total: int) -> Image.Image:
    frame = compose(scene, index, REEL_SIZE, 0.5)
    progress_bar(frame, index, total, 0.5)
    return frame.convert("RGB")


def contact_sheet(images: list[Image.Image], columns: int = 4, thumb_width: int = 270) -> Image.Image:
    ratio = images[0].height / images[0].width
    thumb = (thumb_width, round(thumb_width * ratio))
    rows = math.ceil(len(images) / columns)
    sheet = Image.new("RGB", (columns * thumb[0] + (columns + 1) * 12, rows * thumb[1] + (rows + 1) * 12), (24, 26, 32))
    for n, image in enumerate(images):
        sheet.paste(image.resize(thumb, Image.Resampling.LANCZOS), (12 + (n % columns) * (thumb[0] + 12), 12 + (n // columns) * (thumb[1] + 12)))
    return sheet
