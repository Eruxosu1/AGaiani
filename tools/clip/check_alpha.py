#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_alpha.py: проверка PNG с прозрачностью (рендер из Studio / кадр из VideoExport).

Показывает режим, размер, долю полностью прозрачных, непрозрачных и полупрозрачных пикселей
и сохраняет два файла для проверки краёв: <out>_green.png (на зелёном фоне) и <out>_hair_crop.png
(увеличенный фрагмент края). Нужны Pillow и numpy: pip install -r requirements.txt

Запуск:
    python tools/clip/check_alpha.py "<путь>\\StudioNEOV2-...-Render.png" --out renders/alpha_check
"""
import argparse
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("Нужны Pillow и numpy: pip install pillow numpy")


def analyse(path):
    im = Image.open(path)
    a = np.array(im.convert("RGBA"))
    al = a[..., 3]
    total = al.size
    return im, a, {
        "mode": im.mode,
        "size": im.size,
        "transparent_pct": float(round((al == 0).sum() / total * 100, 1)),
        "opaque_pct": float(round((al == 255).sum() / total * 100, 1)),
        "semi_pct": float(round(((al > 0) & (al < 255)).sum() / total * 100, 2)),
        "has_alpha": bool(al.min() < 255),
    }


def main():
    ap = argparse.ArgumentParser(description="Проверка прозрачности PNG")
    ap.add_argument("png")
    ap.add_argument("--out", default="alpha_check")
    a = ap.parse_args()
    im, arr, info = analyse(a.png)
    print(info)
    if not info["has_alpha"]:
        print("Прозрачности нет: проверьте режим «Transparent background: Composite» в Screenshot settings и пустую карту.")
    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (0, 255, 0, 255))
    bg.alpha_composite(rgba)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    bg.convert("RGB").save(a.out + "_green.png")
    # фрагмент: самая левая непрозрачная область (там обычно край волос/руки)
    ys, xs = np.nonzero(arr[..., 3] > 0)
    if len(xs):
        x0, y0 = max(int(xs.min()) - 10, 0), int(np.median(ys))
        box = (x0, max(y0 - 150, 0), min(x0 + 300, rgba.size[0]), min(y0 + 150, rgba.size[1]))
        bg.convert("RGB").crop(box).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.NEAREST) \
            .save(a.out + "_hair_crop.png")
    print(f"Сохранено: {a.out}_green.png, {a.out}_hair_crop.png")


if __name__ == "__main__":
    main()
