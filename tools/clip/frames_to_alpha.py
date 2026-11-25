#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frames_to_alpha.py: PNG-кадры с прозрачностью -> видео с прозрачным фоном (WebM VP9 и/или MOV ProRes 4444).

Зачем: VideoExport собирает обычный mp4 (в нём альфа-канала нет, фон чёрный). Если сохранить кадры
(в VideoExport выключить «Auto Delete Images»), этим скриптом их можно собрать в видео с прозрачностью
и наложить на промо-ролики. Волосы из Studio дают «дробные» края: опция --feather слегка размывает
альфа-канал, чтобы убрать мерцание.

Запуск:
    python tools/clip/frames_to_alpha.py <папка_с_png> --fps 30 --out renders/test1
    python tools/clip/frames_to_alpha.py <папка_с_png> --fps 30 --out renders/test1 --feather 0.8 --audio voice.wav --preview

Результат: <out>.webm (и/или <out>.mov), <out>_preview.mp4 (персонаж на зелёном фоне, для проверки краёв).
Нужен ffmpeg (в PATH или переменная FFMPEG). Только стандартная библиотека.
"""
import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"не PNG: {path}")
    return struct.unpack(">II", head[16:24])


def list_frames(folder):
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".png"))
    if not names:
        raise SystemExit(f"В папке нет PNG-кадров: {folder}")
    return [os.path.join(folder, n) for n in names]


def stage_sequence(frames, tmp):
    """Нумерует кадры подряд (ffmpeg на Windows не понимает glob): hardlink, а если нельзя, копия."""
    for i, src in enumerate(frames, 1):
        dst = os.path.join(tmp, f"f{i:06d}.png")
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)
    return os.path.join(tmp, "f%06d.png")


def alpha_filter(feather):
    base = "format=rgba"
    if feather and feather > 0:
        return (f"{base},split=2[c][a];[a]alphaextract,gblur=sigma={feather}[m];[c][m]alphamerge")
    return base


def build_cmds(ffmpeg, pattern, fps, audio, feather, out, formats, preview, size):
    flt = alpha_filter(feather)
    vf = ["-vf", flt] if "[" not in flt else ["-filter_complex", flt]
    inputs = ["-framerate", str(fps), "-i", pattern]
    if audio:
        inputs += ["-i", audio]
    cmds = []
    if "webm" in formats:
        c = [ffmpeg, "-y", *inputs, *vf, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "24",
             "-auto-alt-ref", "0"]
        if audio:
            c += ["-c:a", "libopus", "-shortest"]
        cmds.append(c + [out + ".webm"])
    if "mov" in formats:
        c = [ffmpeg, "-y", *inputs, *vf, "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
        if audio:
            c += ["-c:a", "pcm_s16le", "-shortest"]
        cmds.append(c + [out + ".mov"])
    if preview:
        w, h = size
        if feather and feather > 0:
            fg = (f"[0:v]format=rgba,split=2[c][a];[a]alphaextract,gblur=sigma={feather}[m];"
                  f"[c][m]alphamerge[fg]")
        else:
            fg = "[0:v]format=rgba[fg]"
        chain = f"{fg};[1:v][fg]overlay=shortest=1,format=yuv420p"
        c = [ffmpeg, "-y", "-framerate", str(fps), "-i", pattern, "-f", "lavfi", "-i",
             f"color=c=0x00ff00:s={w}x{h}:r={fps}", "-filter_complex", chain, "-c:v", "libx264", "-crf", "20",
             out + "_preview.mp4"]
        cmds.append(c)
    return cmds


def main():
    ap = argparse.ArgumentParser(description="PNG-кадры с альфой -> видео с прозрачным фоном")
    ap.add_argument("frames", help="папка с PNG-кадрами (порядок по имени файла)")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--out", required=True, help="базовое имя результата без расширения")
    ap.add_argument("--formats", default="webm", help="webm, mov или webm,mov")
    ap.add_argument("--feather", type=float, default=0.0, help="размытие альфа-канала (sigma), напр. 0.8; 0 = нет")
    ap.add_argument("--audio", help="звуковая дорожка (wav/mp3)")
    ap.add_argument("--preview", action="store_true", help="сделать mp4 на зелёном фоне для проверки краёв")
    ap.add_argument("--ffmpeg", default=os.environ.get("FFMPEG", "ffmpeg"))
    a = ap.parse_args()

    if not shutil.which(a.ffmpeg) and not os.path.isfile(a.ffmpeg):
        raise SystemExit("ffmpeg не найден: добавьте в PATH или задайте переменную FFMPEG / параметр --ffmpeg")
    frames = list_frames(a.frames)
    size = png_size(frames[0])
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    formats = {f.strip().lower() for f in a.formats.split(",") if f.strip()}
    with tempfile.TemporaryDirectory(prefix="agaiani_") as tmp:
        pattern = stage_sequence(frames, tmp)
        for cmd in build_cmds(a.ffmpeg, pattern, a.fps, a.audio, a.feather, a.out, formats, a.preview, size):
            print(">", " ".join(cmd[:3]), "...", cmd[-1])
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
            if r.returncode != 0:
                print(r.stderr[-1500:])
                raise SystemExit(f"ffmpeg завершился с ошибкой ({r.returncode})")
    print(f"Готово: {len(frames)} кадров, {size[0]}x{size[1]}, {a.fps:g} к/с")


if __name__ == "__main__":
    main()
