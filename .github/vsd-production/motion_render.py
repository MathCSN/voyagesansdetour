"""Fast vertical reels (scenario schema 3): short plans, a hook readable on the first frame,
boxed captions that work without sound, a pause-and-read table card, and real video clips.

Pure Pillow, deterministic. What the research showed (docs/strategie-videos.md): the reels
that travel open on a boxed promise in the middle of the frame, change picture every 1.5 to
3 seconds and never depend on the sound. So each plan here is one photo or one clip, the text
appears at once, and a figure lands alone before its explanation (a cut inside the plan).
Layout keeps clear of the Instagram, TikTok and Shorts interfaces: nothing in the top 230 px,
the bottom 360 px or the right 130 px.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import subprocess

from PIL import Image, ImageDraw, ImageFilter

import social_render as base

SIZE = base.REEL_SIZE
W, H = SIZE
FPS = base.FPS
LEFT, RIGHT = 72, W - 130
TEXT_WIDTH = RIGHT - LEFT
TOP, BOTTOM = 230, 1560
HOOK_CENTER = 900                 # the hook sits where the cover crop and the eye are
ACCENT, INK, WHITE = base.ACCENT, base.INK, base.WHITE
BLUE = (35, 76, 221)
PANEL = (8, 12, 24, 190)
CLEAR = (0, 0, 0, 0)
LAYOUTS = ("hook", "fact", "table", "cta")
SOLO_FRAMES = 18                  # a figure stays alone 0.6 s before its explanation lands
SOLO_MIN_SECONDS = 2.2
TEXT_INTRO_FRAMES = 4
ZOOM_RANGE = 0.13
PUNCH = 0.07                      # zoom jump when the explanation lands: a cut without a new picture
BOX_SIZES = {"hook": (104, 60), "fact": (84, 54), "table": (72, 50), "cta": (88, 56)}
FIGURE_SIZES = (168, 84)
DETAIL_SIZE, KICKER_SIZE, TAG_SIZE, NOTE_SIZE, BUTTON_SIZE, ROW_SIZE = 50, 34, 26, 36, 42, 44
MAX_DETAIL_LINES, MAX_ROWS = 3, 6
NOTDEF = "\U0010ffff"
LayoutError = base.LayoutError


@dataclass(frozen=True)
class Fonts:
    regular: str
    bold: str
    serif: str
    fallback_regular: str
    fallback_bold: str

    def fallback(self, path: str) -> str:
        return self.fallback_bold if path == self.bold else self.fallback_regular


# --- text that never shows an empty box -----------------------------------

@lru_cache(maxsize=4096)
def has_glyph(path: str, char: str) -> bool:
    face = base.font(path, 48)
    return char.isspace() or bytes(face.getmask(char)) != bytes(face.getmask(NOTDEF))


def runs(text: str, path: str, fonts: Fonts) -> list[tuple[str, str]]:
    """Split a string into (substring, font path): the brand font, else the wide-coverage fallback."""
    result: list[tuple[str, str]] = []
    for char in text:
        chosen = path if has_glyph(path, char) else fonts.fallback(path)
        if chosen != path and not has_glyph(chosen, char):
            raise LayoutError("No font draws this character: " + repr(char) + " in " + text)
        if result and result[-1][1] == chosen:
            result[-1] = (result[-1][0] + char, chosen)
        else:
            result.append((char, chosen))
    return result


def width_of(draw: ImageDraw.ImageDraw, text: str, path: str, size: int, fonts: Fonts) -> float:
    return sum(draw.textlength(part, font=base.font(used, size)) for part, used in runs(base.plain(text), path, fonts))


def draw_text(draw: ImageDraw.ImageDraw, xy, line: str, path: str, size: int, fonts: Fonts, fill, accent=None) -> None:
    x, y = xy
    for text, highlighted_part in base.segments(line):
        for part, used in runs(text, path, fonts):
            face = base.font(used, size)
            draw.text((x, y), part, font=face, fill=accent if highlighted_part and accent else fill)
            x += draw.textlength(part, font=face)


def wrap(draw: ImageDraw.ImageDraw, text: str, path: str, size: int, fonts: Fonts, width: int) -> list[str]:
    # Ordinary spaces only: a non-breaking space keeps "1 h 37" or "9 €" on one line.
    lines, current = [], ""
    for word in (w for w in text.replace("\t", " ").replace("\n", " ").split(" ") if w):
        candidate = (current + " " + word).strip()
        if current and width_of(draw, candidate, path, size, fonts) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current] if current else lines


def fit(draw: ImageDraw.ImageDraw, lines: list[str], path: str, sizes: tuple[int, int], fonts: Fonts, width: int) -> int:
    size = sizes[0]
    while size >= sizes[1]:
        if max(width_of(draw, line, path, size, fonts) for line in lines) <= width:
            return size
        size -= 4
    raise LayoutError("Headline too long for the frame: " + " / ".join(lines))


def line_height(path: str, size: int) -> int:
    ascent, descent = base.font(path, size).getmetrics()
    return ascent + descent


# --- blocks: each returns its height; `paint` False only measures ----------

def highlighted(line: str) -> bool:
    return line.startswith("*") and line.endswith("*") and line.count("*") == 2


def pill(draw, paint: bool, x, y, label, size, fonts, fill, text_fill, padding=(22, 11)) -> tuple[int, int]:
    width = width_of(draw, label, fonts.bold, size, fonts)
    height = line_height(fonts.bold, size) + 2 * padding[1]
    if paint:
        draw.rounded_rectangle((x, y, x + width + 2 * padding[0], y + height), radius=height // 2, fill=fill)
        draw_text(draw, (x + padding[0], y + padding[1]), label, fonts.bold, size, fonts, text_fill)
    return int(width + 2 * padding[0]), height


def boxed(draw, paint: bool, y, line, size, fonts) -> int:
    """One caption line on its own rounded box: white with ink text, or yellow for the promise."""
    pad_x, pad_y = 26, 10
    height = line_height(fonts.bold, size) + 2 * pad_y
    if paint:
        width = width_of(draw, line, fonts.bold, size, fonts)
        draw.rounded_rectangle((LEFT, y, LEFT + width + 2 * pad_x, y + height), radius=22, fill=ACCENT if highlighted(line) else WHITE)
        draw_text(draw, (LEFT + pad_x, y + pad_y), line, fonts.bold, size, fonts, INK, accent=INK if highlighted(line) else BLUE)
    return height + 8


def panel(draw, paint: bool, y, lines, fonts) -> int:
    """The explanation: white text on one dark rounded panel, readable on any picture."""
    step, pad = int(DETAIL_SIZE * 1.28), 24
    height = step * len(lines) + 2 * pad
    if paint:
        width = max(width_of(draw, line, fonts.regular, DETAIL_SIZE, fonts) for line in lines)
        draw.rounded_rectangle((LEFT, y, LEFT + width + 2 * pad, y + height), radius=28, fill=PANEL)
        for n, line in enumerate(lines):
            draw_text(draw, (LEFT + pad, y + pad + n * step), line, fonts.regular, DETAIL_SIZE, fonts, (246, 247, 250), accent=ACCENT)
    return height


def table(draw, paint: bool, y, rows, fonts) -> int:
    """Two columns: what you want on the left, the answer in yellow on the right."""
    pad, gap, left_width = 24, 12, 440
    right_width = TEXT_WIDTH - left_width - 3 * pad
    step, total = int(ROW_SIZE * 1.22), 0
    for row in rows:
        left = wrap(draw, row[0], fonts.bold, ROW_SIZE, fonts, left_width)
        right = wrap(draw, row[1], fonts.bold, ROW_SIZE, fonts, right_width)
        if len(left) > 2 or len(right) > 2:
            raise LayoutError("Table cell longer than two lines: " + " | ".join(row))
        height = step * max(len(left), len(right)) + 36
        if paint:
            top = y + total
            draw.rounded_rectangle((LEFT, top, RIGHT, top + height), radius=24, fill=PANEL)
            for n, line in enumerate(left):
                draw_text(draw, (LEFT + pad, top + 18 + n * step), line, fonts.bold, ROW_SIZE, fonts, WHITE)
            for n, line in enumerate(right):
                draw_text(draw, (LEFT + left_width + 2 * pad, top + 18 + n * step), line, fonts.bold, ROW_SIZE, fonts, ACCENT)
        total += height + gap
    return total - gap


def text_layer(scene: dict, fonts: Fonts, button: str | None, solo: bool = False) -> Image.Image:
    """Everything a viewer reads on one plan. `solo` keeps only the kicker and the headline."""
    layout = scene["layout"]
    layer = Image.new("RGBA", SIZE, CLEAR)
    shadow = Image.new("RGBA", SIZE, CLEAR)
    draw, shadow_draw = ImageDraw.Draw(layer), ImageDraw.Draw(shadow)
    headline = scene["headline"]
    figures = [line for line in headline if highlighted(line)] if layout == "fact" else []
    boxes = [line for line in headline if line not in figures]
    figure_size = fit(draw, figures, fonts.bold, FIGURE_SIZES, fonts, TEXT_WIDTH) if figures else 0
    box_size = fit(draw, boxes, fonts.bold, BOX_SIZES[layout], fonts, TEXT_WIDTH - 52) if boxes else 0
    detail = [] if solo or not scene.get("detail") else wrap(draw, scene["detail"], fonts.regular, DETAIL_SIZE, fonts, TEXT_WIDTH - 48)
    if len(detail) > MAX_DETAIL_LINES:
        raise LayoutError("Detail longer than three lines: " + scene["detail"])
    rows = scene.get("rows") or []
    if len(rows) > MAX_ROWS:
        raise LayoutError("Too many table rows")

    def stack(paint: bool, y: int) -> int:
        start, x = y, LEFT
        if scene.get("badge"):
            x += pill(draw, paint, x, y, scene["badge"], KICKER_SIZE, fonts, INK, WHITE)[0] + 10
        y += pill(draw, paint, x, y, scene["kicker"].upper(), KICKER_SIZE, fonts, ACCENT, INK)[1] + 16
        for line in headline:
            if line in figures:
                if paint:
                    draw_text(shadow_draw, (LEFT, y), line, fonts.bold, figure_size, fonts, (0, 0, 0, 215))
                    draw_text(draw, (LEFT, y), line, fonts.bold, figure_size, fonts, ACCENT)
                y += int(figure_size * 1.12)
            else:
                y += boxed(draw, paint, y, line, box_size, fonts)
        if rows:
            y += 18 + table(draw, paint, y + 18, rows, fonts)
        if detail:
            y += 14 + panel(draw, paint, y + 14, detail, fonts)
        if button:
            y += 30 + pill(draw, paint, LEFT, y + 30, button, BUTTON_SIZE, fonts, ACCENT, INK, padding=(30, 18))[1]
        if scene.get("note") and not solo:
            y += 22
            if paint:
                draw_text(shadow_draw, (LEFT, y), scene["note"], fonts.bold, NOTE_SIZE, fonts, (0, 0, 0, 230))
                draw_text(draw, (LEFT, y), scene["note"], fonts.bold, NOTE_SIZE, fonts, WHITE)
            y += line_height(fonts.bold, NOTE_SIZE)
        if scene.get("tag") and not solo:
            y += 22 + pill(draw, paint, LEFT, y + 22, scene["tag"], TAG_SIZE, fonts, (255, 255, 255, 50), (255, 255, 255, 240), padding=(16, 8))[1]
        return y - start

    height = stack(False, 0)
    if height > BOTTOM - TOP:
        raise LayoutError("Text block taller than the safe area")
    if layout in ("hook", "cta", "table"):
        top = min(max(TOP, HOOK_CENTER - height // 2), BOTTOM - height)
    else:
        top = BOTTOM - height
    stack(True, top)
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)), layer)


# --- pictures: a photo that moves, or a real clip ------------------------

@lru_cache(maxsize=4)
def chrome(serif: str) -> Image.Image:
    layer = base.gradient(SIZE, int(H * 0.5), 0.72, top=360, top_strength=0.5)
    ImageDraw.Draw(layer).text((LEFT, 168), "Voyage Sans Détour", font=base.font(serif, 32), fill=(255, 255, 255, 235))
    return layer


DRIFT = 0.07           # how far the frame slides to each side of the photo's subject, as a share of the photo's width
DRIFT_IN_FRAME = 0.19  # …and never further than this share of the frame's own width: the subject stays in the picture
                       # (a 3:2 photo slides as it always did; only wider ones slide less)


def drift_of(size: tuple[int, int], progress: float, index: int) -> float:
    """The sideways slide of the frame at this moment of the plan. On a panorama the vertical frame is narrow: sliding
    7 % of the photo's width carried its subject out of the picture (the temple of Tulum, 12/11/2026)."""
    frame_share = min(1.0, (SIZE[0] / SIZE[1]) * (size[1] / size[0]))
    reach = min(DRIFT, DRIFT_IN_FRAME * frame_share)
    return (2 * progress - 1) * reach * (1 if index % 3 != 1 else -1)


def photo_frame(path: str, focus, t: float, index: int, punched: bool) -> Image.Image:
    image = base.photo(path)
    progress = base.ease(t)
    zoom = 1.0 + ZOOM_RANGE * (progress if index % 2 == 0 else 1 - progress) + (PUNCH if punched else 0.0)
    drift = drift_of(image.size, progress, index)
    return image.resize(SIZE, Image.Resampling.BILINEAR, box=base.cover_box(image.size, SIZE, zoom, (focus[0] + drift, focus[1])))


def clip_frames(path: str, count: int):
    """Decode `count` frames of a normalised 1080 x 1920, 30 fps clip; the last frame is held if it runs short."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", path, "-an", "-vf", f"scale={W}:{H},fps={FPS}",
               "-frames:v", str(count), "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size, last = W * H * 3, None
    try:
        for _ in range(count):
            raw = process.stdout.read(size)
            if len(raw) == size:
                last = Image.frombytes("RGB", SIZE, raw)
            if last is None:
                raise LayoutError("Clip cannot be decoded: " + path)
            yield last
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()


@dataclass(frozen=True)
class Plan:
    media: str
    clip: bool
    focus: tuple
    text: Image.Image
    solo: Image.Image | None
    frames: int
    cover: bool                   # the hook is fully visible on frame 0: it is the cover


def prepare(scenes: list[dict], media: list[tuple[str, bool]], fonts: Fonts, button: str) -> list[Plan]:
    plans = []
    for scene, (path, is_clip) in zip(scenes, media):
        layout = scene["layout"]
        if layout not in LAYOUTS:
            raise LayoutError("Unknown layout: " + str(layout))
        text = text_layer(scene, fonts, button if layout == "cta" else None)
        two_beats = layout == "fact" and scene.get("detail") and scene["seconds"] >= SOLO_MIN_SECONDS
        solo = text_layer(scene, fonts, None, solo=True) if two_beats else None
        plans.append(Plan(path, is_clip, tuple(scene.get("focus", (0.5, 0.5))), text, solo, round(scene["seconds"] * FPS), layout == "hook"))
    return plans


def _with_alpha(layer: Image.Image, alpha: float, lift: int) -> Image.Image:
    if alpha >= 1.0 and not lift:
        return layer
    faded = layer.copy()
    faded.putalpha(layer.getchannel("A").point(lambda value: int(value * alpha)))
    moved = Image.new("RGBA", SIZE, CLEAR)
    moved.paste(faded, (0, lift))
    return moved


def compose(plan: Plan, picture: Image.Image, overlay: Image.Image, n: int) -> Image.Image:
    in_solo = plan.solo is not None and n < SOLO_FRAMES
    since = n if in_solo or plan.solo is None else n - SOLO_FRAMES
    intro = 1.0 if plan.cover else min(1.0, (since + 1) / TEXT_INTRO_FRAMES)
    text = _with_alpha(plan.solo if in_solo else plan.text, base.ease(intro), int(28 * (1 - base.ease(intro))))
    return Image.alpha_composite(Image.alpha_composite(picture.convert("RGBA"), overlay), text)


def progress_bar(frame: Image.Image, index: int, total: int, fraction: float) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    gap, top, height = 8, 140, 6
    span = (RIGHT - LEFT - gap * (total - 1)) / total
    for n in range(total):
        x0 = LEFT + n * (span + gap)
        draw.rounded_rectangle((x0, top, x0 + span, top + height), radius=3, fill=(255, 255, 255, 90))
        filled = 1.0 if n < index else fraction if n == index else 0.0
        if filled > 0:
            draw.rounded_rectangle((x0, top, x0 + max(height, span * filled), top + height), radius=3, fill=(255, 255, 255, 240))


def reel_frames(plans: list[Plan], fonts: Fonts):
    """Yield RGB frames: hard cuts between plans, the text lands in four frames."""
    overlay, total = chrome(fonts.serif), len(plans)
    for index, plan in enumerate(plans):
        pictures = clip_frames(plan.media, plan.frames) if plan.clip else None
        try:
            for n in range(plan.frames):
                punched = plan.solo is not None and n >= SOLO_FRAMES
                picture = next(pictures) if pictures else photo_frame(plan.media, plan.focus, n / max(1, plan.frames - 1), index, punched)
                frame = compose(plan, picture, overlay, n)
                progress_bar(frame, index, total, (n + 1) / plan.frames)
                yield frame.convert("RGB")
        finally:
            if pictures:
                pictures.close()


def still(plan: Plan, index: int, total: int, fonts: Fonts) -> Image.Image:
    """The plan once its text is complete, for the poster, the contact sheet and the layout check."""
    if plan.clip:
        frames = clip_frames(plan.media, 1)
        try:
            picture = next(frames)
        finally:
            frames.close()
    else:
        picture = photo_frame(plan.media, plan.focus, 0.5, index, plan.solo is not None)
    frame = compose(plan, picture, chrome(fonts.serif), plan.frames - 1)
    progress_bar(frame, index, total, 0.5)
    return frame.convert("RGB")
