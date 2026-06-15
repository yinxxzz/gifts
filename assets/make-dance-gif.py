#!/usr/bin/env python3
"""Generate a looping dance GIF from a static character image."""

import math
from pathlib import Path

from PIL import Image

SRC = Path("/Users/john/.cursor/projects/Users-john-Cursor/assets/image-b319101a-dbb5-433f-92f5-e7c1031b5aee.png")
OUT = Path(__file__).resolve().parent / "banma-dance.gif"

FRAMES = 20
DURATION_MS = 70
OUTPUT_SIZE = 480


def find_center(img: Image.Image) -> tuple[float, float]:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    pixels = rgba.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if pixels[x, y][3] > 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return w / 2, h / 2
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def make_frame(base: Image.Image, cx: float, cy: float, t: float) -> Image.Image:
    beat = t * 2 * math.pi
    angle = math.sin(beat) * 12 + math.sin(beat * 2) * 4
    bounce = abs(math.sin(beat)) * 22
    sway = math.sin(beat * 2) * 16
    scale_x = 1.0 + 0.06 * math.sin(beat + math.pi / 2)
    scale_y = 1.0 - 0.04 * math.sin(beat + math.pi / 2)

    w, h = base.size
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 255))

    scaled = base.resize(
        (max(1, int(w * scale_x)), max(1, int(h * scale_y))),
        Image.Resampling.LANCZOS,
    )
    pivot_x = cx * scale_x
    pivot_y = cy * scale_y

    rotated = scaled.rotate(angle, resample=Image.Resampling.BICUBIC, center=(pivot_x, pivot_y))
    paste_x = int((w - rotated.width) / 2 + sway)
    paste_y = int((h - rotated.height) / 2 - bounce)

    canvas.paste(rotated, (paste_x, paste_y), rotated)
    return canvas.convert("P", palette=Image.ADAPTIVE, colors=128)


def main() -> None:
    base = Image.open(SRC).convert("RGBA")
    w, h = base.size
    scale = OUTPUT_SIZE / max(w, h)
    if scale < 1:
        base = base.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    cx, cy = find_center(base)
    frames = [make_frame(base, cx, cy, i / FRAMES) for i in range(FRAMES)]

    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Saved: {OUT} ({OUT.stat().st_size // 1024} KB, {FRAMES} frames)")


if __name__ == "__main__":
    main()
