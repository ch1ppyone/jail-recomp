#!/bin/zsh
# prepare_jail.sh -- Tokyo Ghoul: JAIL from the files in data/ to a native build.
#
# data/ is the only input location. Place the user's PKG (or VPK / decrypted
# folder), its matching work.bin/.rif and Sony's PSVUPDAT.PUP there. Nothing is
# downloaded, and nothing is copied into Git.
#
# usage: src/tools/prepare_jail.sh [--frames N]
set -euo pipefail
HERE=${0:A:h}; ROOT=${HERE:h:h}
NATIV=$ROOT/nativ
DATA=$ROOT/data
export ATIV_DUMP=${ATIV_DUMP:-$NATIV/dump}
export ATIV_PACKS=${ATIV_PACKS:-$NATIV/packs}
export ATIV_MAC_TOOLCHAIN=${ATIV_MAC_TOOLCHAIN:-$HOME/toolchains/ativ-mac}
mkdir -p "$ATIV_DUMP"

FIRST_FILE() { find "$DATA" -type f "$@" 2>/dev/null | head -1 || true; }
find_pkg()    { FIRST_FILE -name '*.pkg'; }
find_vpk()    { FIRST_FILE -iname '*.vpk'; }
find_licence(){ FIRST_FILE \( -name 'work.bin' -o -name '*.rif' \); }
find_pup()    { FIRST_FILE \( -name 'PSVUPDAT.PUP' -o -name 'PSP2UPDAT.PUP' -o -name '*.PUP' \); }
find_dump() {
  local sfo
  sfo=$(FIRST_FILE -path '*/sce_sys/param.sfo')
  [[ -n $sfo ]] && dirname "$(dirname "$sfo")"
}

FRAMES=600
while (( $# )); do
  case $1 in
    (--frames) FRAMES=$2; shift 2 ;;
    (*) echo "usage: src/tools/prepare_jail.sh [--frames N]"; exit 1 ;;
  esac
done

[[ -d $DATA ]] || { echo "missing data/ directory"; exit 1; }

PKG=$(find_pkg)
VPK=$(find_vpk)
DUMPDIR=$(find_dump)
LIC=$(find_licence)
PUP=$(find_pup)

if [[ -n $PKG ]]; then GAME=$PKG
elif [[ -n $VPK ]]; then GAME=$VPK
elif [[ -n $DUMPDIR ]]; then GAME=$DUMPDIR
else
  echo "no game copy in data/: put the PKG (or VPK / decrypted folder) there"
  exit 1
fi

if [[ -z $LIC && -f $GAME/sce_sys/package/work.bin ]]; then
  LIC=$GAME/sce_sys/package/work.bin
fi
if [[ $GAME == *.pkg && -z $LIC ]]; then
  echo "the encrypted PKG needs its matching work.bin/.rif in data/"
  exit 1
fi

HAVE_FIRMWARE=$(find "$ATIV_DUMP/firmware" -maxdepth 2 -type f -name version.txt 2>/dev/null | head -1 || true)
if [[ -z $HAVE_FIRMWARE ]]; then
  [[ -n $PUP ]] || { echo "put Sony's PSVUPDAT.PUP in data/ (firmware is not processed yet)"; exit 1; }
  echo "firmware: $PUP"
  ( cd "$NATIV" && ./vitarecomp firmware "$PUP" )
fi

case $GAME in
  (*.rif|*/work.bin) ;;
  (*) python3 "$ROOT/src/tools/check_dump.py" "$GAME" || true ;;
esac

if [[ -d $GAME && -f $GAME/eboot.bin ]]; then
  python3 "$ROOT/src/tools/normalize_dump.py" "$GAME" || true
fi

if [[ -f $ROOT/packs/PCSG00615/pack.toml ]]; then
  mkdir -p "$NATIV/packs/PCSG00615"
  cp "$ROOT/packs/PCSG00615/pack.toml" "$NATIV/packs/PCSG00615/pack.toml"
  echo "pack: packs/PCSG00615/pack.toml"
fi

cd "$NATIV"
[[ -n $LIC ]] && ./vitarecomp licenses import "$LIC"
ADD=("$GAME")
[[ -n $LIC ]] && ADD+=(--license "$LIC")
./vitarecomp add "${ADD[@]}" --no-build
./vitarecomp analyze PCSG00615
./vitarecomp recompile PCSG00615
./vitarecomp build PCSG00615
TEST_FRAMES=$FRAMES ./vitarecomp test PCSG00615 || true

echo
echo "built: $ATIV_DUMP/decrypted/PCSG00615"
echo "play:  cd nativ && ./vitarecomp run PCSG00615"
echo "or:    ./JAIL-PyQt.command"
