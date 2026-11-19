#!/usr/bin/env python3
"""check_dump.py -- decide, before doing anything else, whether a copy of
Tokyo Ghoul: JAIL can be used WITHOUT a licence, and what it contains.

Accepts: a folder, a .vpk / .zip (read without extracting), or a .pkg.

Why this matters: a PKG and a folder dump are protected by different layers.

  PKG (.pkg)                  -> outer AES-CTR (no licence) + inner PFS (licence)
  VitaShell / NoNpDrm dump    -> files decrypted, but eboot.bin is still an
                                 NPDRM *APP* SELF: unwrapping its metadata needs
                                 the title's klicensee
  Vitamin / FAGDec dump       -> eboot.bin is a plain ELF: usable now, only the
                                 firmware keys (already local) are needed
  rePatch / translation patch -> the replacement files are plaintext; whatever
                                 it ships is immediately analysable

So "I found a VPK" is not a yes/no answer: the tool reads the actual bytes and
says which of the above it is.

usage: check_dump.py <path> [--json OUT]
Exit: 0 usable without a licence, 1 needs a licence, 2 not this game / unreadable.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import struct
import sys
import zipfile

SCE_MAGIC = b"SCE\x00"
ELF_MAGIC = b"\x7fELF"
PKG_MAGIC = b"\x7fPKG"
WANT_TITLE = "PCSG00615"


def entropy(b: bytes) -> float:
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())


def parse_sfo(data: bytes) -> dict:
    """PSF/param.sfo -> {key: value} (strings/ints)."""
    if len(data) < 20 or data[:4] != b"\x00PSF":
        return {}
    _magic, _ver, key_off, data_off, count = struct.unpack_from("<IIIII", data, 0)
    out = {}
    for i in range(count):
        o = 0x14 + i * 16
        if o + 16 > len(data):
            break
        koff, fmt, dlen, dmax, doff = struct.unpack_from("<HHIII", data, o)
        kend = data.find(b"\x00", key_off + koff)
        key = data[key_off + koff:kend].decode("utf-8", "replace")
        raw = data[data_off + doff:data_off + doff + dlen]
        # PSF formats: 0x0004/0x0204/0x0402 are text (UTF-8/UTF-8-NUL/ASCII),
        # 0x0404 is a little-endian uint32.
        if fmt == 0x0404 and len(raw) >= 4:
            out[key] = struct.unpack("<I", raw[:4])[0]
        elif fmt in (0x0004, 0x0204, 0x0402):
            out[key] = raw.rstrip(b"\x00").decode("utf-8", "replace")
        else:
            out[key] = raw.hex()
    return out


class Source:
    """uniform access to a directory or a zip"""

    def __init__(self, path: str):
        self.path = path
        self.zip = None
        self.root = ""
        if os.path.isdir(path):
            self.names = []
            for dp, _dn, fn in os.walk(path):
                for f in fn:
                    self.names.append(os.path.relpath(os.path.join(dp, f), path).replace(os.sep, "/"))
            self.kind = "dir"
        elif path.lower().endswith((".vpk", ".zip")):
            self.zip = zipfile.ZipFile(path)
            self.names = [n for n in self.zip.namelist() if not n.endswith("/")]
            self.kind = "zip"
        else:
            self.kind = "file"
            self.names = []
        # a VPK often has everything under one folder: find the prefix holding sce_sys/
        if self.names:
            for n in self.names:
                if n.endswith("sce_sys/param.sfo"):
                    self.root = n[: -len("sce_sys/param.sfo")]
                    break

    def has(self, rel: str) -> bool:
        return (self.root + rel) in self.names

    def find(self, suffix: str) -> list[str]:
        return [n for n in self.names if n.endswith(suffix)]

    def head(self, rel: str, n: int = 4096) -> bytes:
        name = self.root + rel
        if self.kind == "dir":
            p = os.path.join(self.path, name)
            if not os.path.isfile(p):
                return b""
            with open(p, "rb") as f:
                return f.read(n)
        if self.kind == "zip" and name in self.names:
            with self.zip.open(name) as f:
                return f.read(n)
        return b""


def classify_eboot(head: bytes) -> str:
    if not head:
        return "absent"
    if head[:4] == ELF_MAGIC:
        return "elf"
    if head[:4] == SCE_MAGIC:
        # the SELF header itself is plaintext: self_type tells APP (NPDRM) from a system module
        try:
            _magic, _ver, _plat, _keyrev, sce_type, _mo, _hl, _fs = struct.unpack_from("<IIHHHQQQ", head, 0)
            _fl, _f8, _so, appinfo = struct.unpack_from("<QQQQ", head, 0x20)
            _aid, _vid, self_type = struct.unpack_from("<QQQ", head, appinfo)
            return "self-app" if self_type == 8 else f"self-{self_type}"
        except struct.error:
            return "self"
    return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)

    if not os.path.exists(a.path):
        print(f"no such path: {a.path}")
        return 2

    # a bare PKG: report what is knowable without its licence
    if os.path.isfile(a.path):
        with open(a.path, "rb") as f:
            magic = f.read(4)
        if magic == PKG_MAGIC:
            print("kind            : PKG (retail)")
            print("outer layer     : readable without a licence")
            print("inner layer     : PFS, needs the title's klicensee")
            print("verdict         : NEEDS-LICENCE (see BLOCKERS.md, B1)")
            return 1

    src = Source(a.path)
    res: dict = {"path": a.path, "kind": src.kind, "root": src.root}

    sfo = parse_sfo(src.head("sce_sys/param.sfo", 4096))
    res["title_id"] = sfo.get("TITLE_ID", "")
    res["app_ver"] = sfo.get("APP_VER", "")
    res["title"] = sfo.get("TITLE", "")

    res["pfs_layer"] = src.has("sce_pfs/files.db")
    res["work_bin"] = src.has("sce_sys/package/work.bin")
    res["eboot"] = classify_eboot(src.head("eboot.bin", 64))
    res["eboot_elf_sibling"] = src.has("eboot.bin.elf")
    res["elf_files"] = len(src.find(".elf"))
    res["suprx"] = len(src.find(".suprx"))

    # a data file: plaintext game data has structure, ciphertext is uniform
    data_rel = "PSP2_GAME/USRDIR/resource.dat"
    d = src.head(data_rel, 65536)
    res["resource_head"] = d[:8].hex()
    res["resource_entropy"] = round(entropy(d), 4) if d else None
    res["resource_present"] = bool(d)
    res["resource_readable"] = bool(d) and entropy(d) < 7.9

    # rePatch-style translation patch?
    res["repatch_paths"] = sorted({n.split("/")[0] for n in src.names if "/rePatch/" in "/" + n or n.startswith("rePatch/")})[:5]

    verdict, why = "UNKNOWN", []
    if res["title_id"] and res["title_id"] != WANT_TITLE:
        verdict = "WRONG-TITLE"
        why.append(f"это {res['title_id']}, нужен {WANT_TITLE}")
    elif res["work_bin"]:
        verdict = "LICENCE-INSIDE"
        why.append("в копии есть sce_sys/package/work.bin — лицензия внутри")
    elif res["eboot"] == "elf" or res["eboot_elf_sibling"] or res["elf_files"]:
        verdict = "USABLE-NOW"
        why.append("eboot уже расшифрован (ELF): лицензия не нужна")
    elif res["pfs_layer"] or res["eboot"] in ("self-app", "unknown", "absent"):
        verdict = "NEEDS-LICENCE"
        if res["pfs_layer"]:
            why.append("присутствует слой PFS (sce_pfs/files.db)")
        if res["eboot"] == "self-app":
            why.append("eboot.bin — NPDRM APP SELF, для распаковки нужен klicensee")
        elif res["eboot"] == "unknown":
            why.append("eboot.bin не ELF и не SELF: файлы зашифрованы")
        elif res["eboot"] == "absent":
            why.append("нет eboot.bin")

    if res["resource_present"]:
        why.append("resource.dat: " + ("открытые данные" if res["resource_readable"]
                                       else f"шифротекст (энтропия {res['resource_entropy']})"))

    res["verdict"] = verdict
    res["why"] = why

    print(f"path            : {a.path}")
    print(f"container       : {src.kind}" + (f" (root '{src.root}')" if src.root else ""))
    print(f"title id        : {res['title_id'] or '-'}   version: {res['app_ver'] or '-'}")
    print(f"title           : {res['title'] or '-'}")
    print(f"PFS layer       : {'yes' if res['pfs_layer'] else 'no'}")
    print(f"work.bin        : {'yes' if res['work_bin'] else 'no'}")
    print(f"eboot.bin       : {res['eboot']}")
    print(f"ELF files       : {res['elf_files']}   SUPRX: {res['suprx']}")
    if res["resource_present"]:
        print(f"resource.dat    : entropy {res['resource_entropy']} -> "
              f"{'readable' if res['resource_readable'] else 'ciphertext'}")
    if res["repatch_paths"]:
        print(f"rePatch layout  : {', '.join(res['repatch_paths'])}")
    print(f"\nVERDICT: {verdict}")
    for w in why:
        print(f"  - {w}")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, ensure_ascii=False)
        print(f"\nwritten: {a.json}")

    return {"USABLE-NOW": 0, "LICENCE-INSIDE": 0}.get(verdict, 1)


if __name__ == "__main__":
    raise SystemExit(main())
