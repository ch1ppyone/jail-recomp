# Tokyo Ghoul: JAIL v0.1.2

## Desktop release

This release uses the shared PyQt6 launcher on macOS, Windows and Linux. Put
your own game inputs in the release's `data/` directory:

```text
data/PCSG00615.pkg
data/work.bin
data/PSVUPDAT.PUP
```

The package does not include original game resources, firmware, licences,
decrypted files or generated game builds. The first launch prepares the local
library; later launches use **PLAY JAIL**.

Generated builds, saves, settings and logs are stored in the user's data
directory. They are not written into the release folder.

## Platform status

- **macOS Apple Silicon:** DMG package with the native PyQt6 launcher.
- **Windows x86-64:** ZIP package with `Tokyo Ghoul JAIL.exe`, Qt6 runtime
  files, the JAIL icon and the LLVM C++ runtime DLLs beside the host. The game
  was tested through to the end on an ASUS ROG Xbox Ally X.
- **Linux x86-64:** Planned; no Linux package is included in this release.
- **Android arm64:** APK release flow remains documented in `README.md`.

The Windows package was verified on real hardware through the complete game.
The game reaches the runtime, shows frames, accepts input, plays audio, writes
saves and can be completed. A VM without a supported SDL GPU backend uses the
software renderer and can be slow:

```text
window: no GPU device; presenting with the SDL software renderer
```

On a Windows host with D3D12 or Vulkan available, SDL can use the hardware
renderer. `RECOMP_NO_GPU=1` forces software presentation for diagnostics.

## Candidate artifacts

The local candidate built from the uncommitted working tree was staged at:

`~/Desktop/Tokyo-Ghoul-JAIL-Release-Candidate-v0.1.2-dirty/`

```text
6cecaef5f1e82079b89f234f9b32e3c9f5f5a005c97520b04f28e25f109a9bf3  JAIL-v0.1.2-dirty-mac.dmg
b45495b9f332c7ec9512cfeae65fdb941a70d2fcf92f75b089f506d35325f6b4  JAIL-v0.1.2-dirty-windows.zip
```

These are verification candidates, not final tag artifacts. Build the final
release from a clean exact tag so `version.txt` contains the release tag and
the package can be published reproducibly.
