#!/usr/bin/env python3
"""Turn the prompt PNG into the C array runtime/ui/overlay.cpp includes.

This is the same generation runtime/build.py performs into its object directory. Keeping it in
the Android project means the native build never depends on a desktop build artifact.
"""
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: gen_prompts_header.py <input.png> <output.h>", file=sys.stderr)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "rb") as f:
        data = f.read()
    with open(dst, "w", encoding="ascii") as f:
        f.write("static const unsigned char prompts_png[] = {\n")
        for i in range(0, len(data), 40):
            f.write(",".join(str(b) for b in data[i:i + 40]) + ",\n")
        f.write("};\n")
    print(f"gen_prompts_header: {len(data)} bytes -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
