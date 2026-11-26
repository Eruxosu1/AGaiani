import os
import shutil
import struct
import zlib

import pytest

import frames_to_alpha as fa


def _rgba_png(path, w=8, h=8, alpha_left=0):
    raw = b""
    for y in range(h):
        raw += b"\x00" + b"".join(
            bytes((200, 30, 30, alpha_left if x < w // 2 else 255)) for x in range(w))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(data)


def test_png_size(tmp_path):
    p = tmp_path / "a.png"
    _rgba_png(str(p), 8, 6)
    assert fa.png_size(str(p)) == (8, 6)


def test_alpha_filter_modes():
    assert fa.alpha_filter(0) == "format=rgba"
    assert "gblur=sigma=0.8" in fa.alpha_filter(0.8)


def test_build_cmds_webm_uses_alpha_pixfmt():
    cmds = fa.build_cmds("ffmpeg", "x/f%06d.png", 30, None, 0, "out/c", {"webm"}, False, (8, 8))
    assert len(cmds) == 1 and "yuva420p" in cmds[0] and cmds[0][-1] == "out/c.webm"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_end_to_end_webm(tmp_path):
    frames = tmp_path / "frames"
    frames.mkdir()
    for i in range(3):
        _rgba_png(str(frames / f"shot_{i:03d}.png"), 16, 16)
    out = tmp_path / "res" / "clip"
    import subprocess
    import sys
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "clip",
                          "frames_to_alpha.py")
    r = subprocess.run([sys.executable, script, str(frames), "--fps", "10", "--out", str(out), "--formats", "webm"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert os.path.getsize(str(out) + ".webm") > 0


def test_list_frames_natural_order(tmp_path):
    for n in ("0", "1", "2", "10", "11", "100", "99"):
        _rgba_png(str(tmp_path / f"{n}.png"), 4, 4)
    got = [os.path.basename(p) for p in fa.list_frames(str(tmp_path))]
    assert got == ["0.png", "1.png", "2.png", "10.png", "11.png", "99.png", "100.png"]
