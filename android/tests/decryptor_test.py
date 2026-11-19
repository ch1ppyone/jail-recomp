#!/usr/bin/env python3
"""Host-side checks for the Android PKG decryptor.

Builds synthetic PKGs with the project's Python reference implementation, then
runs the Java decryptor against them. Covers the happy path and the failures
that matter on a phone: a licence from another copy, a truncated download, a
corrupted payload, a file that is not a PKG, and a failed reinstall that must
leave the existing app0 and saves untouched.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "nativ" / "decrypt"))

from vitadecrypt import pkg as PKG, pfs as PFS, sfo as SFO, rif as RIF  # noqa: E402
from vitadecrypt.game import _pfs_encrypt_member, _pfs_verify_only_member  # noqa: E402

KLIC = bytes.fromhex("00112233445566778899aabbccddeeff")
WRONG_KLIC = bytes.fromhex("ffeeddccbbaa99887766554433221100")
CONTENT_ID = "JP0700-PCSG00615_00-TOKYOGHOUL000001"


def build_fixtures(out: Path) -> Path:
    sfo = SFO.build_sfo({
        "APP_VER": "01.00", "CATEGORY": "gd", "TITLE_ID": "PCSG00615",
        "CONTENT_ID": CONTENT_ID, "TITLE": "Synthetic JAIL",
    })
    eboot = b"SCE\x00" + bytes(range(256)) * 20
    big = (b"0123456789abcdef" * 8192) + b"tail!"
    short = b"x" * 5000

    eboot_sigs, eboot_box = _pfs_encrypt_member(eboot, KLIC)
    big_sigs, big_box = _pfs_encrypt_member(big, KLIC)
    short_sigs, short_box = _pfs_encrypt_member(short, KLIC)

    entries = [
        (0, "sce_sys", 1, PFS.FT_SYS_DIR, 0),
        (1, "param.sfo", 2, PFS.FT_UNENC_SYS_RO, len(sfo)),
        (0, "eboot.bin", 3, PFS.FT_NORMAL_FILE, len(eboot)),
        (0, "data", 4, PFS.FT_NORMAL_DIR, 0),
        (4, "big.bin", 5, PFS.FT_NORMAL_FILE, len(big)),
        (4, "short.bin", 6, PFS.FT_NORMAL_FILE, len(short)),
        (0, "empty.bin", 7, PFS.FT_NORMAL_FILE, 0),
    ]
    files_db = PFS._build_files_db(KLIC, 0x1000, version=4, image_spec=1, entries=entries)
    unicv = PFS._build_unicv_db([
        {"num_sectors": len(PFS._chunks(sfo, PFS.FILE_SECTOR_SIZE)), "version": 1, "dbseed": None,
         "make_sigs": _pfs_verify_only_member(sfo, KLIC)},
        {"num_sectors": len(PFS._chunks(eboot, PFS.FILE_SECTOR_SIZE)), "version": 1, "dbseed": None,
         "make_sigs": eboot_sigs},
        {"num_sectors": len(PFS._chunks(big, PFS.FILE_SECTOR_SIZE)), "version": 1, "dbseed": None,
         "make_sigs": big_sigs},
        {"num_sectors": len(PFS._chunks(short, PFS.FILE_SECTOR_SIZE)), "version": 1, "dbseed": None,
         "make_sigs": short_sigs},
    ])
    pkg = PKG._build_synthetic_pkg(sfo, {
        "sce_pfs/files.db": files_db,
        "sce_pfs/unicv.db": unicv,
        "sce_sys/param.sfo": sfo,
        "eboot.bin": eboot_box["bytes"],
        "data/big.bin": big_box["bytes"],
        "data/short.bin": short_box["bytes"],
        "empty.bin": b"",
    }, key_type=2)

    (out / "good.pkg").write_bytes(pkg)
    (out / "good.rif").write_bytes(RIF.build_rif(CONTENT_ID, KLIC))
    (out / "wrong.rif").write_bytes(RIF.build_rif(CONTENT_ID, WRONG_KLIC))
    (out / "truncated.pkg").write_bytes(pkg[:-4096])
    (out / "notpkg.bin").write_bytes(b"this is not a Vita package\n" * 64)

    # Flip one byte inside the PKG's copy of big.bin: after the outer AES-CTR
    # layer is removed, PFS's per-sector ICV must catch the corruption instead
    # of writing garbage into app0.
    files_order = ["sce_pfs/files.db", "sce_pfs/unicv.db", "sce_sys/param.sfo", "eboot.bin",
                   "data/big.bin", "data/short.bin", "empty.bin"]
    lengths = [len(files_db), len(unicv), len(sfo), len(eboot_box["bytes"]),
               len(big_box["bytes"]), len(short_box["bytes"]), 0]
    pad16 = lambda n: (n + 15) & ~15
    cursor = len(files_order) * 32 + sum(pad16(len(n)) for n in files_order)
    data_offsets = []
    for n in lengths:
        data_offsets.append(cursor)
        cursor += pad16(n)
    sfo_offset = 0xC0 + 0x40 + 3 * 16
    data_offset_abs = sfo_offset + pad16(len(sfo))
    big_at = data_offset_abs + data_offsets[files_order.index("data/big.bin")]
    corrupt = bytearray(pkg)
    corrupt[big_at + 40000] ^= 0xFF   # second PFS sector: the table match still works, the ICV must fail
    (out / "corrupt.pkg").write_bytes(bytes(corrupt))

    expected = out / "expected"
    (expected / "sce_sys").mkdir(parents=True)
    (expected / "data").mkdir()
    (expected / "sce_sys/param.sfo").write_bytes(sfo)
    (expected / "eboot.bin").write_bytes(eboot)
    (expected / "data/big.bin").write_bytes(big)
    (expected / "data/short.bin").write_bytes(short)
    (expected / "empty.bin").write_bytes(b"")
    return expected


def tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file() and p.name != "game.json"}


def compile_java(classes: Path, java_home: str | None) -> tuple[str, str]:
    javac = str(Path(java_home) / "bin" / "javac") if java_home else "javac"
    java = str(Path(java_home) / "bin" / "java") if java_home else "java"
    src = ROOT / "android/app/src/main/java/dev/ch1ppy/jail/VitaDecryptor.java"
    subprocess.run([javac, "-d", str(classes), str(src)], check=True)
    subprocess.run([javac, "-cp", str(classes), "-d", str(classes),
                    str(ROOT / "android/tests/SpaceCheck.java")], check=True)
    return javac, java


def run_decryptor(java: str, classes: Path, pkg: Path, rif: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([java, "-cp", str(classes), "dev.ch1ppy.jail.VitaDecryptor",
                           str(pkg), str(rif), str(out)],
                          capture_output=True, text=True)


def expect_failure(name: str, proc: subprocess.CompletedProcess, words: tuple[str, ...]) -> str | None:
    text = proc.stdout + proc.stderr
    if proc.returncode == 0:
        return f"{name}: expected a failure, exit was 0"
    if not any(w.lower() in text.lower() for w in words):
        return f"{name}: failure message does not mention {words}: {text[-400:]}"
    return None


def main() -> int:
    java_home = os.environ.get("JAVA_HOME")
    work = Path(tempfile.mkdtemp(prefix="jail-decryptor-test-"))
    failures: list[str] = []
    try:
        expected = build_fixtures(work)
        classes = work / "classes"
        classes.mkdir()
        _, java = compile_java(classes, java_home)

        good_out = work / "out-good"
        (good_out / "savedata0").mkdir(parents=True)
        (good_out / "savedata0" / "keep.txt").write_text("keep-me\n")
        proc = run_decryptor(java, classes, work / "good.pkg", work / "good.rif", good_out)
        if proc.returncode != 0:
            failures.append("good: decryptor failed: " + (proc.stdout + proc.stderr)[-500:])
        else:
            got = tree(good_out / "app0")
            want = tree(expected)
            if got != want:
                diff = sorted(set(got) ^ set(want)) or [k for k in got if got[k] != want.get(k)]
                failures.append(f"good: tree differs: {diff[:6]}")
            if not (good_out / "savedata0" / "keep.txt").is_file():
                failures.append("good: savedata0 was modified")
        print("PASS good pkg" if not failures or not failures[-1].startswith("good:") else "FAIL good pkg")

        cases = [
            ("wrong licence", "wrong.rif", ("does not match", "signature", "PFS"), "out-wrong"),
            ("truncated pkg", "good.rif", ("truncated", "smaller", "PKG"), "out-truncated"),
            ("corrupt payload", "good.rif", ("integrity", "mismatch", "corrupt", "sector"), "out-corrupt"),
            ("not a pkg", "good.rif", ("not a Vita PKG", "bad magic"), "out-notpkg"),
        ]
        for name, rif, words, dirname in cases:
            pkg = work / ("truncated.pkg" if name == "truncated pkg" else
                          "corrupt.pkg" if name == "corrupt payload" else
                          "notpkg.bin" if name == "not a pkg" else "good.pkg")
            proc = run_decryptor(java, classes, pkg, work / rif, work / dirname)
            err = expect_failure(name, proc, words)
            if err:
                failures.append(err)
                print(f"FAIL {name}")
            else:
                print(f"PASS {name}")

        # A failed reinstall must leave the previous app0 and saves intact and
        # must not leave a second ~1 GB tree behind.
        before = tree(good_out / "app0")
        proc = run_decryptor(java, classes, work / "corrupt.pkg", work / "good.rif", good_out)
        err = expect_failure("preserved install", proc, ("integrity", "mismatch", "corrupt", "sector"))
        if err:
            failures.append(err)
        if tree(good_out / "app0") != before:
            failures.append("preserved install: the previous app0 changed")
        if not (good_out / "savedata0" / "keep.txt").is_file():
            failures.append("preserved install: savedata0 was modified")
        for leftover in ("app0.new", "app0.part", "prepare.part"):
            if (good_out / leftover).exists():
                failures.append(f"preserved install: {leftover} was left behind")
        print("PASS preserved install" if not err else "FAIL preserved install")

        space = subprocess.run([java, "-cp", str(classes), "dev.ch1ppy.jail.SpaceCheck"],
                               capture_output=True, text=True)
        if space.returncode != 0 or "space check: OK" not in space.stdout:
            failures.append("space check failed: " + (space.stdout + space.stderr)[-300:])
            print("FAIL space check")
        else:
            print("PASS space check")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nall decryptor checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
