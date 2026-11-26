#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_clip.py: кадры из Studio -> готовый клип библиотеки Ани (WebM с прозрачностью + манифест clip.json).

Делает то же, что frames_to_alpha.py, но кладёт результат в библиотеку клипов
(renders/library/<персонаж>/<имя_клипа>/) и записывает манифест, чтобы монтаж (ffmpeg, compose.ts)
находил клипы по имени. Для зацикленных клипов считает «шов»: насколько последний кадр отличается от первого
по сравнению с обычной разницей между соседними кадрами.

Запуск:
    python tools/clip/build_clip.py <папка_кадров> --name idle --fps 30 --loop --emotion neutral
    python tools/clip/build_clip.py <папка_кадров> --name wave --fps 30 --emotion happy --trim 0 74

Результат: renders/library/ani_main/idle/clip.webm, clip.json, и обновлённый renders/library/index.json.
Нужен ffmpeg; для расчёта шва нужны Pillow и numpy (без них клип собирается, шов не считается).
"""
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from frames_to_alpha import build_cmds, list_frames, png_size, stage_sequence


def seam_ratio(frames, sample=8):
    """Отношение разницы «последний кадр -> первый» к средней разнице соседних кадров. ~1 = шов незаметен.
    None, если нет Pillow/numpy или кадров мало."""
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None
    if len(frames) < 4:
        return None

    def load(p):
        return np.asarray(Image.open(p).convert("RGBA"), dtype=np.int16)

    def diff(a, b):
        return float(np.abs(a - b).mean())

    idx = [round(i * (len(frames) - 2) / max(sample - 1, 1)) for i in range(sample)]
    steps = [diff(load(frames[i]), load(frames[i + 1])) for i in sorted(set(idx))]
    base = sum(steps) / len(steps)
    seam = diff(load(frames[-1]), load(frames[0]))
    return round(seam / base, 2) if base > 1e-6 else (0.0 if seam < 1e-6 else None)


def main():
    ap = argparse.ArgumentParser(description="Кадры -> клип библиотеки Ани")
    ap.add_argument("frames", help="папка с PNG-кадрами")
    ap.add_argument("--name", required=True, help="имя клипа: idle, talk_a, happy, wave ...")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--character", default="ani_main", help="папка персонажа в библиотеке")
    ap.add_argument("--emotion", default="neutral")
    ap.add_argument("--loop", action="store_true", help="клип должен зацикливаться (проверить шов)")
    ap.add_argument("--trim", nargs=2, type=int, metavar=("FROM", "TO"), help="взять кадры с номера FROM по TO включительно")
    ap.add_argument("--feather", type=float, default=0.8)
    ap.add_argument("--library", default=os.path.join("renders", "library"))
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    a = ap.parse_args()

    if not shutil.which(a.ffmpeg) and not os.path.isfile(a.ffmpeg):
        raise SystemExit("ffmpeg не найден: добавьте в PATH или задайте переменную FFMPEG / параметр --ffmpeg")
    frames = list_frames(a.frames)
    if a.trim:
        frames = frames[a.trim[0]: a.trim[1] + 1]
        if not frames:
            raise SystemExit("после --trim кадров не осталось")
    size = png_size(frames[0])
    out_dir = os.path.join(a.library, a.character, a.name)
    os.makedirs(out_dir, exist_ok=True)
    out_base = os.path.join(out_dir, "clip")

    with tempfile.TemporaryDirectory(prefix="agaiani_") as tmp:
        pattern = stage_sequence(frames, tmp)
        for cmd in build_cmds(a.ffmpeg, pattern, a.fps, None, a.feather, out_base, {"webm"}, False, size):
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
            if r.returncode != 0:
                print(r.stderr[-1500:])
                raise SystemExit(f"ffmpeg завершился с ошибкой ({r.returncode})")

    ratio = seam_ratio(frames) if a.loop else None
    manifest = {
        "name": a.name, "character": a.character, "emotion": a.emotion, "fps": a.fps,
        "size": list(size), "frames": len(frames), "duration_s": round(len(frames) / a.fps, 3),
        "loop": bool(a.loop), "loop_seam_ratio": ratio, "webm": "clip.webm",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "source_frames": os.path.abspath(a.frames),
    }
    with open(os.path.join(out_dir, "clip.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    index_path = os.path.join(a.library, "index.json")
    index = {}
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)
    index.setdefault(a.character, {})[a.name] = {
        "path": os.path.join(a.character, a.name, "clip.webm").replace("\\", "/"),
        "emotion": a.emotion, "fps": a.fps, "duration_s": manifest["duration_s"], "loop": bool(a.loop)}
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)

    print(f"Клип {a.character}/{a.name}: {len(frames)} кадров, {manifest['duration_s']} с, {size[0]}x{size[1]}")
    if a.loop:
        if ratio is None:
            print("Шов цикла не посчитан (нужны Pillow и numpy: pip install -r requirements.txt)")
        elif ratio < 0.3:
            print(f"Шов цикла: {ratio} (последний кадр почти равен первому: при зацикливании поза замрёт на один "
                  f"кадр; уберите последний кадр: --trim 0 {len(frames) - 2})")
        elif ratio <= 1.5:
            print(f"Шов цикла: {ratio} (хорошо, петля должна быть незаметна)")
        else:
            print(f"Шов цикла: {ratio} (последний кадр заметно отличается от первого; "
                  f"обрежьте клип по точке, где поза повторяется: --trim)")
    print(f"Манифест: {os.path.join(out_dir, 'clip.json')}")


if __name__ == "__main__":
    main()
