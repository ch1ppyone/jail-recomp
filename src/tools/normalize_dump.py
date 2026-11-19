#!/usr/bin/env python3
"""normalize_dump.py -- make an already-decrypted dump look the way Nativ's
`add` expects, without touching the bytes.

Nativ's `add` accepts a folder only if it can see `eboot.bin.elf` (its
convention for "the main program as a plain ELF"). A dump produced by a tool
that decrypted the SELF on-console (Vitamin, FAGDec, some translation patches)
has `eboot.bin` itself as a plain ELF instead. The bytes are identical; only
the name differs. This writes the `<name>.elf` siblings Nativ looks for, as
hard links (no extra space, no copy of the original).

It never rewrites an existing file, and it refuses to guess: a file is only
linked when its first four bytes really are \\x7fELF.

usage: normalize_dump.py <folder> [--copy]
"""
from __future__ import annotations

import os
import shutil
import sys

ELF = b"\x7fELF"


def is_elf(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == ELF
    except OSError:
        return False


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = argv[0]
    copy = "--copy" in argv
    if not os.path.isdir(root):
        print(f"not a folder: {root}")
        return 2

    made = []
    # the main program, then the game's own modules
    cands = [os.path.join(root, "eboot.bin")]
    moddir = os.path.join(root, "sce_module")
    if os.path.isdir(moddir):
        cands += [os.path.join(moddir, n) for n in sorted(os.listdir(moddir))]

    for p in cands:
        if not os.path.isfile(p) or p.endswith(".elf"):
            continue
        if not is_elf(p):
            continue                       # still a SELF: leave it for the SELF decrypter
        dst = p + ".elf"
        if os.path.exists(dst):
            continue
        if copy:
            shutil.copyfile(p, dst)
        else:
            try:
                os.link(p, dst)
            except OSError:
                shutil.copyfile(p, dst)
        made.append(os.path.relpath(dst, root))

    if made:
        print("linked plain ELFs as Nativ expects:")
        for m in made:
            print(f"  {m}")
    else:
        print("nothing to do: no plain ELF eboot/modules found (this dump still needs SELF decryption)")
    return 0 if made else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
