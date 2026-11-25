import struct
import zlib

import audit_card as ac


def _png(payload):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    head = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
    return head + ihdr + idat + chunk(b"IEND", b"") + payload


def test_split_card_finds_tail():
    payload, ok = ac.split_card(_png(b"hello-tail"))
    assert ok and payload == b"hello-tail"


def test_guid_hits_with_msgpack_prefix_bytes():
    by_guid = {"com.test.mod": [{"author": "A"}], "other.mod": [{"author": "B"}]}
    payload = b"\x00\xd9\x0ccom.test.mod\x05\xa9nothing!!"
    hits = ac.find_hits(payload, by_guid)
    assert "com.test.mod" in hits and "other.mod" not in hits


def test_uar_state_empty_and_filled():
    empty = b"xx" + ac.UAR + b"\x92\x00\x81\xa4info\x90"
    filled = b"xx" + ac.UAR + b"\x92\x00\x81\xa4info\x91\x82"
    assert ac.uar_state(empty) == "empty"
    assert ac.uar_state(filled) == "filled"
    assert ac.uar_state(b"nothing here") == "absent"


def test_plugin_ids_listed():
    ids = ac.plugin_ids(b"\xa5com.fairbair.hs2_boobsettings\x01 moreAccessories")
    assert any(k.startswith("com.fairbair") for k in ids)
    assert any("moreAccessories" in k for k in ids)
