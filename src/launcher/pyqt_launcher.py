#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tokyo Ghoul: JAIL Recompiled launcher (PyQt6 / QSS, macOS - Windows - Linux).

The launcher validates the player's own local inputs (PKG, work.bin/.rif, Vita
firmware), runs the local recompilation pipeline, writes the runtime's
settings.ini and starts the built game.
"""
from __future__ import annotations

import datetime
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import QProcess, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QKeyEvent, QPainter, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QSizePolicy, QSlider, QStackedWidget,
    QVBoxLayout, QWidget,
)

TITLE = "PCSG00615"
CONTENT_ID = "JP0700-PCSG00615_00-TOKYOGHOUL000001"
ROOT = Path(__file__).resolve().parents[2]
NATIV = ROOT / "nativ"
DATA_DIR = ROOT / "data"
LOG_PATH = ROOT / "logs" / "launcher.log"
PIPELINE = NATIV / "pipeline" / "vitarecomp.py"
DUMP = Path(os.environ.get("ATIV_DUMP", NATIV / "dump")).expanduser()
GAME_DIR = DUMP / "decrypted" / TITLE
RECOMP_DIR = GAME_DIR / "recomp"
GAME_EXE = RECOMP_DIR / ("game_host.exe" if os.name == "nt" else "game_host")

STYLE = """
* { outline: none; }
QMainWindow { background: #050506; }
QWidget { color: #d8d0c3; }
#accent { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #26030a, stop:0.35 #7e0012, stop:0.55 #e01430, stop:1 #26030a); }
#sidebar { background: rgba(7, 6, 8, 242); border-right: 1px solid #2a1216; }
#brandJp { color: #9b8f80; font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
    font-size: 14px; letter-spacing: 6px; }
#brand { color: #e8e1d5; font-family: "Georgia", "Times New Roman", serif;
    font-size: 27px; font-weight: bold; letter-spacing: 3px; }
#brandJail { color: #e8e1d5; font-family: "Georgia", "Times New Roman", serif;
    font-size: 54px; font-weight: bold; letter-spacing: 13px;
    border-left: 4px solid #b00018; padding-left: 13px; }
#brandRed { color: #c8102e; font-size: 10px; font-weight: bold; letter-spacing: 5px; }
#brandSub { color: #6b625a; font-size: 10px; letter-spacing: 2px; }
#section { color: #5e554d; font-size: 9px; font-weight: bold; letter-spacing: 3px; }
QPushButton#nav {
    background: transparent; color: #8d8378; text-align: left;
    padding: 11px 14px; border: none; border-left: 2px solid transparent;
    font-size: 12px; font-weight: bold; letter-spacing: 2px;
}
QPushButton#nav:hover { background: #110c0e; color: #e8e1d5; }
QPushButton#nav:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #26060b, stop:1 #0a0709);
    color: #f2ece2; border-left: 2px solid #d21026; padding-left: 14px;
}
#footer { color: #453d38; font-size: 9px; font-weight: bold; letter-spacing: 2px; }
#kicker { color: #c8102e; font-size: 9px; font-weight: bold; letter-spacing: 4px; }
#h1 { color: #f0eadf; font-family: "Georgia", "Times New Roman", serif;
    font-size: 36px; font-weight: bold; letter-spacing: 2px; }
#subtitle { color: #8d8378; font-size: 13px; }
#rule { background: #4a0a12; }
#card { background: #0c0b0d; border: 1px solid #241317; border-left: 2px solid #6d000f; }
#cardTitle { color: #ece5d9; font-size: 15px; font-weight: bold; letter-spacing: 2px; }
#muted { color: #7f756b; font-size: 12px; }
#body { color: #c8bfb2; font-size: 13px; }
#path { color: #8d8378; font-size: 11px; }
#status { color: #8d8378; font-size: 12px; }
#ok { color: #55c785; font-size: 12px; font-weight: bold; }
#badgeOk { background: #0d2116; color: #55c785; border: 1px solid #1d4a30;
    padding: 4px 9px; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
#badgeBad { background: #26070c; color: #ff5165; border: 1px solid #5c1019;
    padding: 4px 9px; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
#badgeWait { background: #26200a; color: #d9b64a; border: 1px solid #5a4a12;
    padding: 4px 9px; font-size: 9px; font-weight: bold; letter-spacing: 1px; }
QComboBox {
    background: #080709; border: 1px solid #2c1a1e; padding: 8px 11px;
    color: #e8e1d5; font-size: 12px;
}
QComboBox:hover { border-color: #5a2028; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #0d0b0e; color: #e8e1d5;
    selection-background-color: #6d000f; border: 1px solid #2c1a1e;
}
QCheckBox { color: #c8bfb2; font-size: 12px; spacing: 9px; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #4a2a30; background: #080709; }
QCheckBox::indicator:checked { background: #b00018; border-color: #e01430; }
QSlider::groove:horizontal { height: 3px; background: #2a1a1e; }
QSlider::sub-page:horizontal { background: #b00018; }
QSlider::handle:horizontal { background: #e8e1d5; width: 12px; margin: -5px 0; border-radius: 6px; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #c8102e, stop:1 #820010);
    color: #ffffff; border: 1px solid #e01430; padding: 12px 26px;
    font-size: 12px; font-weight: bold; letter-spacing: 2px;
}
QPushButton#primary:hover { background: #e01430; }
QPushButton#primary:disabled { background: #25070c; color: #6f4a50; border-color: #3a1319; }
QPushButton#secondary {
    background: #0b090c; color: #bdb2a4; border: 1px solid #3a252b;
    padding: 10px 16px; font-size: 11px; font-weight: bold; letter-spacing: 1px;
}
QPushButton#secondary:hover { background: #170e11; color: #f0eadf; border-color: #6d000f; }
QPushButton#bind {
    background: #080709; color: #d8d0c3; border: 1px solid #3a252b;
    padding: 5px 8px; font-size: 11px; min-width: 0px;
}
QPushButton#bind:hover { border-color: #b00018; }
QPushButton#bind:focus { border-color: #e01430; background: #24070c; }
QProgressBar {
    background: #0a080a; border: 1px solid #2c1a1e;
    max-height: 8px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: #c8102e; }
QMessageBox { background: #0c0b0d; }
"""

# ---- runtime keyboard defaults (nativ/runtime/ui/kb_bind.h) -----------------
KEY_BINDINGS = [
    ("bind_move_up", "Left stick up", "Left stick", "W"),
    ("bind_move_down", "Left stick down", "Left stick", "S"),
    ("bind_move_left", "Left stick left", "Left stick", "A"),
    ("bind_move_right", "Left stick right", "Left stick", "D"),
    ("bind_look_up", "Right stick up", "Right stick", "I"),
    ("bind_look_down", "Right stick down", "Right stick", "K"),
    ("bind_look_left", "Right stick left", "Right stick", "J"),
    ("bind_look_right", "Right stick right", "Right stick", "L"),
    ("bind_up", "D-pad up", "D-pad", "Up"),
    ("bind_down", "D-pad down", "D-pad", "Down"),
    ("bind_left", "D-pad left", "D-pad", "Left"),
    ("bind_right", "D-pad right", "D-pad", "Right"),
    ("bind_cross", "Cross", "Face buttons", "X"),
    ("bind_circle", "Circle", "Face buttons", "C"),
    ("bind_square", "Square", "Face buttons", "Z"),
    ("bind_triangle", "Triangle", "Face buttons", "V"),
    ("bind_l", "L (right mouse)", "Shoulder buttons", "Q"),
    ("bind_r", "R (left mouse)", "Shoulder buttons", "E"),
    ("bind_start", "Start", "System", "Return"),
    ("bind_select", "Select", "System", "Right Shift"),
    ("bind_ps", "PS button", "System", "P"),
    ("bind_l2", "L2 (PS TV)", "PS TV only", "U"),
    ("bind_r2", "R2 (PS TV)", "PS TV only", "O"),
    ("bind_l3", "L3 (PS TV)", "PS TV only", "F"),
    ("bind_r3", "R3 (PS TV)", "PS TV only", "H"),
]

QT_KEYS = {
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Return: "Return", Qt.Key.Key_Enter: "Return",
    Qt.Key.Key_Escape: "Escape", Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Backspace: "Backspace", Qt.Key.Key_Space: "Space",
    Qt.Key.Key_Shift: "Right Shift", Qt.Key.Key_Control: "Left Ctrl",
    Qt.Key.Key_Alt: "Left Alt", Qt.Key.Key_Meta: "Left GUI",
    Qt.Key.Key_Minus: "-", Qt.Key.Key_Equal: "=",
    Qt.Key.Key_BracketLeft: "[", Qt.Key.Key_BracketRight: "]",
    Qt.Key.Key_Backslash: "\\", Qt.Key.Key_Semicolon: ";",
    Qt.Key.Key_Apostrophe: "'", Qt.Key.Key_QuoteLeft: "`",
    Qt.Key.Key_Comma: ",", Qt.Key.Key_Period: ".", Qt.Key.Key_Slash: "/",
}
for _i in range(12):
    QT_KEYS[getattr(Qt.Key, f"Key_F{_i + 1}")] = f"F{_i + 1}"


class Backdrop(QWidget):
    """The window's own dark surface: thin cell bars and a faint JAIL mark."""

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#050506"))
        pen = QPen(QColor(126, 0, 18, 22))
        pen.setWidth(1)
        painter.setPen(pen)
        for x in range(0, self.width(), 38):
            painter.drawLine(x, 0, x, self.height())
        painter.setPen(QColor(126, 0, 18, 16))
        font = QFont("Georgia", 210, QFont.Weight.Black)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 16)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, -30, 44, 0),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "JAIL")
        pen = QPen(QColor(176, 0, 24, 55))
        pen.setWidth(2)
        painter.setPen(pen)
        h = self.height()
        for offset in (0, 34, 76):
            painter.drawLine(18 + offset, h - 110, 118 + offset, h - 10)
        painter.end()


class IniFile:
    """A small INI writer that keeps unrelated keys and comments intact."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.path.is_file():
            return values
        for line in self.path.read_text(errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith(("#", ";")):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values

    def update(self, values: dict[str, object]) -> None:
        wanted = {key: str(value) for key, value in values.items()}
        lines = self.path.read_text(errors="replace").splitlines() if self.path.is_file() else []
        written: set[str] = set()
        result: list[str] = []
        for line in lines:
            if "=" in line and not line.lstrip().startswith(("#", ";")):
                key = line.split("=", 1)[0].strip()
                if key in wanted:
                    result.append(f"{key}={wanted[key]}")
                    written.add(key)
                    continue
            result.append(line)
        for key, value in wanted.items():
            if key not in written:
                result.append(f"{key}={value}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(result) + "\n")


def shared_settings_path() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProjectNativ" / "Nativ" / "settings.ini"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "ProjectNativ" / "Nativ" / "settings.ini"
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "ProjectNativ" / "Nativ" / "settings.ini"


class Settings:
    """The runtime's settings, written into this game's and the shared file."""

    def __init__(self) -> None:
        self.game = IniFile(RECOMP_DIR / "settings.ini")
        self.shared = IniFile(shared_settings_path())

    def read(self) -> dict[str, str]:
        values = self.shared.read()
        values.update(self.game.read())
        return values

    def write(self, values: dict[str, object]) -> None:
        self.game.update(values)
        self.shared.update(values)


class KeyButton(QPushButton):
    captured = pyqtSignal(str)

    def __init__(self, name: str):
        super().__init__(name)
        self.setObjectName("bind")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._capturing = False
        self._idle = name
        self.clicked.connect(self.begin_capture)

    def begin_capture(self) -> None:
        self._capturing = True
        self.setText("Press a key…")
        self.setFocus()

    def set_idle_text(self, text: str) -> None:
        self._idle = text
        if not self._capturing:
            self.setText(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Escape:
            self._capturing = False
            self.setText(self._idle)
            return
        name = QT_KEYS.get(event.key())
        if name is None:
            key = event.key()
            if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                name = chr(key)
            elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                name = chr(key)
        if name is None:
            return
        self._capturing = False
        self.setText(name)
        self.captured.emit(name)


class Launcher(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(DATA_DIR / "launcher.ini"), QSettings.Format.IniFormat)
        self.runtime = Settings()
        self.process: QProcess | None = None
        self.stages: list[tuple[str, list[str], bool]] = []
        self.stage = 0
        self.stage_fraction = 0.0
        self.cancelled = False
        self.data_state = "missing"
        self.inputs: dict[str, Path | None] = {"pkg": None, "licence": None, "firmware": None}
        self.validity: dict[str, str] = {}
        self.valid_flags: dict[str, bool] = {}
        self._pkg_cache: dict[tuple[str, int, int], tuple[bool, str]] = {}
        self.bind_buttons: dict[str, KeyButton] = {}
        self.output_tail: list[str] = []
        self._loading = True

        self.setWindowTitle("Tokyo Ghoul: JAIL — Recompiled")
        self.setMinimumSize(1120, 820)
        self.resize(1220, 830)
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        self.build_ui()
        self.load_values()
        self.refresh_bindings()
        self.set_data_state("checking")
        self._loading = False
        QTimer.singleShot(0, self.refresh_data)

    # ---------------------------------------------------------------- discovery
    @staticmethod
    def find_file(folder: Path, patterns: tuple[str, ...], recursive: bool = True) -> Path | None:
        if not folder.is_dir():
            return None
        for pattern in patterns:
            matches = sorted(p for p in (folder.rglob(pattern) if recursive else folder.glob(pattern)) if p.is_file())
            if matches:
                return matches[0]
        return None

    def detect_all(self) -> None:
        # data/ is the only input location. Files elsewhere are copied here by
        # the Browse actions before they are used.
        self.inputs["pkg"] = self.find_file(DATA_DIR, ("*.pkg", "*.PKG"))
        self.inputs["licence"] = self.find_file(DATA_DIR, ("work.bin", "*.rif", "*.RIF"))
        self.inputs["firmware"] = self.find_file(
            DATA_DIR, ("PSVUPDAT.PUP", "PSP2UPDAT.PUP", "*.PUP", "*.pup"))

    # ---------------------------------------------------------------- validation
    def pkg_info(self, path: Path) -> tuple[bool, str]:
        key = (str(path), path.stat().st_size, path.stat().st_mtime_ns)
        if key in self._pkg_cache:
            return self._pkg_cache[key]
        try:
            result = subprocess.run(
                [sys.executable, str(NATIV / "pipeline" / "packs.py"), "info", str(path)],
                capture_output=True, text=True, timeout=30, cwd=str(NATIV))
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"cannot inspect PKG: {exc}"
        output = (result.stdout + result.stderr).strip()
        ok = result.returncode == 0 and TITLE in output and CONTENT_ID in output
        answer = (ok, output if ok else f"not {TITLE} / {CONTENT_ID}")
        self._pkg_cache[key] = answer
        return answer

    @staticmethod
    def licence_info(path: Path) -> tuple[bool, str]:
        if path.stat().st_size != 512:
            return False, f"{path.stat().st_size} bytes, expected 512"
        try:
            data = path.read_bytes()
            _ver, _vf, _type, _flags, _aid, content_id, *_ = struct.unpack(
                "<HHHHQ48s16s16sQQ40sQ16s16s16s16s20sIIi256s", data)
            cid = content_id.rstrip(b"\x00").decode("ascii", "replace")
        except (OSError, struct.error) as exc:
            return False, f"not a RIF/work.bin: {exc}"
        if cid != CONTENT_ID:
            return False, f"licence is for {cid or 'an unknown title'}"
        return True, cid

    @staticmethod
    def pup_info(path: Path) -> tuple[bool, str]:
        try:
            with path.open("rb") as handle:
                head = handle.read(0x80)
        except OSError as exc:
            return False, f"cannot read firmware: {exc}"
        if len(head) < 0x80 or head[:5] != b"SCEUF":
            return False, "not a Vita PUP (missing SCEUF header)"
        fw_version, = struct.unpack_from("<I", head, 0x10)
        count, = struct.unpack_from("<I", head, 0x18)
        if not fw_version or not count:
            return False, "PUP header has no firmware version/entries"
        major, minor = (fw_version >> 24) & 0xFF, (fw_version >> 16) & 0xFF
        return True, f"{major}.{minor:02x}"

    def refresh_data(self) -> None:
        self.detect_all()
        self.validity = {}
        self.valid_flags = {}
        problems = []
        pkg = self.inputs["pkg"]
        if pkg:
            ok, detail = self.pkg_info(pkg)
            self.validity["pkg"] = detail
            self.valid_flags["pkg"] = ok
            if not ok:
                problems.append(f"PKG: {detail}")
        else:
            problems.append("PKG: not found")
        lic = self.inputs["licence"]
        if lic:
            ok, detail = self.licence_info(lic)
            self.validity["licence"] = detail
            self.valid_flags["licence"] = ok
            if not ok:
                problems.append(f"licence: {detail}")
        else:
            problems.append("licence: not found")
        pup = self.inputs["firmware"]
        if pup:
            ok, detail = self.pup_info(pup)
            self.validity["firmware"] = detail
            self.valid_flags["firmware"] = ok
            if not ok:
                problems.append(f"firmware: {detail}")
        else:
            problems.append("firmware: not found")

        good = not problems
        self.update_inputs_ui()
        if good:
            self.set_data_state("ready")
            self.update_ready_text()
        elif pkg or lic or pup:
            self.set_data_state("invalid")
            self.detail_label.setText("The local data failed its check:\n" + "\n".join(problems))
            self.update_status("Game data is incomplete or invalid. Use Browse to replace it.")
        else:
            self.set_data_state("missing")
            self.update_status("Game data not found. Put the PKG, licence and firmware into data/ or press Browse.")

    def update_inputs_ui(self) -> None:
        rows = (("pkg", "Game PKG", self.pkg_status, self.pkg_path),
                ("licence", "Licence", self.licence_status, self.licence_path),
                ("firmware", "Firmware", self.firmware_status, self.firmware_path))
        for key, _label, status, path_label in rows:
            path = self.inputs[key]
            if not path:
                status.setText("NOT FOUND")
                status.setObjectName("badgeBad")
                path_label.setText("—")
            else:
                valid = self.valid_flags.get(key, False)
                short = {"pkg": "VALID", "licence": "VALID",
                         "firmware": self.validity.get(key, "VALID") if valid else "INVALID"}[key]
                status.setText(short if valid else "INVALID")
                status.setObjectName("badgeOk" if valid else "badgeBad")
                name = path.name
                path_label.setText(name if len(name) <= 46 else name[:26] + "…" + name[-12:])
                path_label.setToolTip(str(path))
            for widget in (status, path_label):
                widget.style().unpolish(widget)
                widget.style().polish(widget)

    # ---------------------------------------------------------------- interface
    def build_ui(self) -> None:
        central = Backdrop()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("accent")
        accent.setFixedHeight(3)
        outer.addWidget(accent)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)
        body.addWidget(self.build_sidebar())

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(48, 34, 48, 24)
        main_layout.setSpacing(0)
        body.addWidget(main, 1)

        self.stack = QStackedWidget()
        for page in (self.build_home(), self.build_data(), self.build_controls(),
                     self.build_display(), self.build_settings()):
            self.stack.addWidget(page)
        main_layout.addWidget(self.stack, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 14, 0, 0)
        bottom.setSpacing(12)
        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bottom.addWidget(self.status, 1)
        self.stop_button = QPushButton("STOP")
        self.stop_button.setObjectName("secondary")
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        self.stop_button.clicked.connect(self.stop_pipeline)
        bottom.addWidget(self.stop_button)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(160)
        self.progress.hide()
        bottom.addWidget(self.progress)
        close = QPushButton("CLOSE")
        close.setObjectName("secondary")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        self.play = QPushButton("PREPARE && PLAY")
        self.play.setObjectName("primary")
        self.play.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play.clicked.connect(self.play_clicked)
        bottom.addWidget(self.play)
        main_layout.addLayout(bottom)
        self.show_page(0)

    def build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(318)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(30, 30, 26, 24)
        layout.setSpacing(4)

        jp = QLabel("東京喰種")
        jp.setObjectName("brandJp")
        brand = QLabel("TOKYO GHOUL")
        brand.setObjectName("brand")
        jail = QLabel("JAIL")
        jail.setObjectName("brandJail")
        red = QLabel("R E C O M P I L E D")
        red.setObjectName("brandRed")
        sub = QLabel("PS VITA · PCSG00615\nORIGINAL JAPANESE DATA")
        sub.setObjectName("brandSub")
        layout.addWidget(jp)
        layout.addWidget(brand)
        layout.addWidget(jail)
        layout.addSpacing(6)
        layout.addWidget(red)
        layout.addSpacing(2)
        layout.addWidget(sub)

        layout.addSpacing(42)
        section = QLabel("CONFIGURATION")
        section.setObjectName("section")
        layout.addWidget(section)
        layout.addSpacing(8)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for index, (number, text) in enumerate((("01", "HOME"), ("02", "GAME DATA"),
                                                ("03", "CONTROLS"), ("04", "DISPLAY"),
                                                ("05", "SETTINGS"))):
            button = QPushButton(f"{number}   {text}")
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, i=index: self.show_page(i))
            self.nav_group.addButton(button, index)
            layout.addWidget(button)

        layout.addStretch(1)
        footer = QLabel("LOCAL BUILD\nPCSG00615 · 1.00")
        footer.setObjectName("footer")
        layout.addWidget(footer)
        return sidebar

    def page_header(self, kicker: str, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        k = QLabel(kicker)
        k.setObjectName("kicker")
        h = QLabel(title)
        h.setObjectName("h1")
        s = QLabel(subtitle)
        s.setObjectName("subtitle")
        s.setWordWrap(True)
        rule = QFrame()
        rule.setObjectName("rule")
        rule.setFixedHeight(1)
        layout.addWidget(k)
        layout.addWidget(h)
        layout.addWidget(s)
        layout.addSpacing(12)
        layout.addWidget(rule)
        layout.addSpacing(16)
        return page, layout

    def card(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        detail = QLabel(subtitle)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)
        return frame, layout

    def build_home(self) -> QWidget:
        page, layout = self.page_header(
            "SURVIVAL PROTOCOL", "READY TO RUN",
            "Your own copy of Tokyo Ghoul: JAIL, rebuilt natively. "
            "The launcher prepares what is missing and starts the game.")

        source, source_layout = self.card("GAME SOURCE", "JAPAN · PCSG00615 · VERSION 1.00 · ORIGINAL JAPANESE DATA")
        self.data_badge = QLabel("DATA NOT FOUND")
        self.data_badge.setObjectName("badgeBad")
        self.detail_label = QLabel("No game data found.")
        self.detail_label.setObjectName("body")
        self.detail_label.setWordWrap(True)
        self.browse = QPushButton("BROWSE")
        self.browse.setObjectName("secondary")
        self.browse.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(self.browse)
        menu.addAction("Data folder (PKG + licence + PUP)…", self.browse_data_folder)
        menu.addAction("Game PKG…", lambda: self.choose_file("pkg", "Game package (*.pkg *.PKG)"))
        menu.addAction("Licence (work.bin / .rif)…", lambda: self.choose_file("licence", "Licence (*.rif work.bin)"))
        menu.addAction("Firmware (PSVUPDAT.PUP)…", lambda: self.choose_file("firmware", "Firmware (*.PUP *.pup)"))
        self.browse.setMenu(menu)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(14)
        badge_row.addWidget(self.data_badge)
        badge_row.addStretch(1)
        badge_row.addWidget(self.browse)
        source_layout.addSpacing(14)
        source_layout.addLayout(badge_row)
        source_layout.addSpacing(10)
        source_layout.addWidget(self.detail_label)
        source_layout.addStretch(1)
        layout.addWidget(source)
        layout.addSpacing(12)

        status, status_layout = self.card("BUILD STATUS", "What the local pipeline has ready")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)
        self.build_rows: dict[str, QLabel] = {}
        for row, (key, label) in enumerate((("firmware", "Vita firmware"), ("licence", "Licence kept"),
                                            ("game", "Decrypted game"), ("build", "Native build"))):
            name = QLabel(label)
            name.setObjectName("body")
            value = QLabel("—")
            value.setObjectName("muted")
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            grid.setColumnStretch(1, 1)
            self.build_rows[key] = value
        status_layout.addSpacing(10)
        status_layout.addLayout(grid)
        actions = QHBoxLayout()
        actions.addStretch(1)
        recheck = QPushButton("RE-CHECK")
        recheck.setObjectName("secondary")
        recheck.setCursor(Qt.CursorShape.PointingHandCursor)
        recheck.clicked.connect(self.refresh_data)
        open_data = QPushButton("OPEN DATA")
        open_data.setObjectName("secondary")
        open_data.setCursor(Qt.CursorShape.PointingHandCursor)
        open_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR))))
        actions.addWidget(open_data)
        actions.addWidget(recheck)
        status_layout.addSpacing(10)
        status_layout.addLayout(actions)
        status_layout.addStretch(1)
        layout.addWidget(status)
        layout.addSpacing(12)

        layout.addStretch(1)
        return page

    def build_data(self) -> QWidget:
        page, layout = self.page_header(
            "ARCHIVE", "GAME DATA",
            "Everything is read from your own local files. Nothing is downloaded or uploaded.")

        inputs, input_layout = self.card("LOCAL INPUTS", "The PKG, its matching licence and Sony's Vita firmware")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.pkg_status, self.licence_status, self.firmware_status = QLabel("—"), QLabel("—"), QLabel("—")
        self.pkg_path, self.licence_path, self.firmware_path = QLabel("—"), QLabel("—"), QLabel("—")
        for row, (label, status, path_label, key, filt) in enumerate((
                ("Game PKG", self.pkg_status, self.pkg_path, "pkg", "Game package (*.pkg *.PKG)"),
                ("Licence", self.licence_status, self.licence_path, "licence", "Licence (*.rif work.bin)"),
                ("Firmware", self.firmware_status, self.firmware_path, "firmware", "Firmware (*.PUP *.pup)"))):
            for widget in (status, path_label):
                widget.setObjectName("muted")
            path_label.setWordWrap(True)
            name = QLabel(label)
            name.setObjectName("body")
            choose = QPushButton("CHOOSE…")
            choose.setObjectName("secondary")
            choose.setCursor(Qt.CursorShape.PointingHandCursor)
            choose.clicked.connect(lambda _checked=False, k=key, f=filt: self.choose_file(k, f))
            grid.addWidget(name, row, 0)
            grid.addWidget(path_label, row, 1)
            grid.addWidget(status, row, 2)
            grid.addWidget(choose, row, 3)
            grid.setColumnStretch(1, 1)
        input_layout.addSpacing(12)
        input_layout.addLayout(grid)
        input_layout.addStretch(1)
        layout.addWidget(inputs)
        layout.addSpacing(12)

        layout.addStretch(1)
        return page

    def build_controls(self) -> QWidget:
        page, layout = self.page_header(
            "COMBAT", "CONTROLS",
            "Keyboard and connected controllers work at the same time. Click a key, then press the new one.")

        bindings, bind_layout = self.card("KEYBOARD BINDINGS", "Click a key, then press the new key. Esc cancels.")
        header = QHBoxLayout()
        header.addStretch(1)
        reset = QPushButton("RESET DEFAULTS")
        reset.setObjectName("secondary")
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.clicked.connect(self.reset_bindings)
        header.addWidget(reset)
        bind_layout.addSpacing(6)
        bind_layout.addLayout(header)

        labels = {key: (label, group, default) for key, label, group, default in KEY_BINDINGS}
        groups = (
            (("LEFT STICK", ("bind_move_up", "bind_move_down", "bind_move_left", "bind_move_right")),
             ("D-PAD", ("bind_up", "bind_down", "bind_left", "bind_right"))),
            (("RIGHT STICK", ("bind_look_up", "bind_look_down", "bind_look_left", "bind_look_right")),
             ("FACE BUTTONS", ("bind_cross", "bind_circle", "bind_square", "bind_triangle"))),
            (("SHOULDERS", ("bind_l", "bind_r")),
             ("SYSTEM", ("bind_start", "bind_select", "bind_ps")),
             ("PS TV ONLY", ("bind_l2", "bind_r2", "bind_l3", "bind_r3"))),
        )
        columns = QHBoxLayout()
        columns.setSpacing(26)
        for group_column in groups:
            column = QVBoxLayout()
            column.setSpacing(6)
            for title, keys in group_column:
                heading = QLabel(title)
                heading.setObjectName("section")
                column.addWidget(heading)
                for key in keys:
                    label, _group, _default = labels[key]
                    row = QHBoxLayout()
                    row.setSpacing(8)
                    name = QLabel(label)
                    name.setObjectName("body")
                    name.setMinimumWidth(104)
                    button = KeyButton("")
                    button.setFixedWidth(92)
                    button.setMinimumHeight(28)
                    button.captured.connect(lambda value, k=key: self.bind_key(k, value))
                    self.bind_buttons[key] = button
                    row.addWidget(name)
                    row.addStretch(1)
                    row.addWidget(button)
                    column.addLayout(row)
                column.addSpacing(6)
            column.addStretch(1)
            columns.addLayout(column, 1)
        bind_layout.addSpacing(10)
        bind_layout.addLayout(columns)
        bind_layout.addStretch(1)
        layout.addWidget(bindings)
        layout.addStretch(1)
        return page

    def build_display(self) -> QWidget:
        page, layout = self.page_header(
            "PERCEPTION", "DISPLAY",
            "Internal resolution, frame rate and how the picture fills your screen.")

        display, display_layout = self.card("DISPLAY SETTINGS", "Applied the next time the game starts")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(11)
        labels = ("RESOLUTION", "FRAME RATE", "PICTURE FIT", "ASPECT RATIO", "ON-SCREEN STATS", "VOLUME")
        for row, text in enumerate(labels):
            label = QLabel(text)
            label.setObjectName("body")
            grid.addWidget(label, row, 0)
        self.resolution = QComboBox()
        for n in range(1, 7):
            self.resolution.addItem(f"{n}x — {960 * n}×{544 * n}", n)
        self.resolution.currentIndexChanged.connect(self.persist)
        self.fps = QComboBox()
        self.fps.addItem("Original (30)", 30)
        self.fps.addItem("60 fps", 60)
        self.fps.currentIndexChanged.connect(self.persist)
        self.fit = QComboBox()
        self.fit.addItem("Letterbox", "fit")
        self.fit.addItem("Stretch", "stretch")
        self.fit.addItem("Fill (crop)", "fill")
        self.fit.currentIndexChanged.connect(self.persist)
        self.aspect = QComboBox()
        for label, value in (("Native (Vita)", "native"), ("16:10", "16:10"), ("3:2", "3:2"),
                             ("21:9", "21:9"), ("32:9", "32:9"), ("Window", "window")):
            self.aspect.addItem(label, value)
        self.aspect.currentIndexChanged.connect(self.persist)
        self.osd = QComboBox()
        for label, value in (("Off", 0), ("FPS", 1), ("Full", 2)):
            self.osd.addItem(label, value)
        self.osd.currentIndexChanged.connect(self.persist)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.valueChanged.connect(self.persist)
        self.fullscreen = QCheckBox("Fullscreen")
        self.fullscreen.stateChanged.connect(self.persist)
        for row, widget in enumerate((self.resolution, self.fps, self.fit,
                                      self.aspect, self.osd, self.volume)):
            grid.addWidget(widget, row, 1)
        grid.addWidget(self.fullscreen, 6, 1)
        grid.setColumnStretch(1, 1)
        display_layout.addSpacing(14)
        display_layout.addLayout(grid)
        note = QLabel("The in-game settings menu is disabled in this build. "
                      "These settings are saved for the next start.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        display_layout.addSpacing(12)
        display_layout.addWidget(note)
        display_layout.addStretch(1)
        layout.addWidget(display)
        layout.addStretch(1)
        return page

    def build_settings(self) -> QWidget:
        page, layout = self.page_header(
            "SYSTEM", "SETTINGS",
            "Diagnostics, local data and the components used by this build.")

        diagnostics, diag_layout = self.card("DIAGNOSTICS", "Off by default; the game does not need a log")
        self.logging = QCheckBox("Write system log (logs/launcher.log)")
        self.logging.setChecked(str(self.settings.value("logging", "false")).lower() in {"1", "true"})
        self.logging.stateChanged.connect(self.toggle_logging)
        diag_layout.addSpacing(8)
        diag_layout.addWidget(self.logging)
        row = QHBoxLayout()
        row.addStretch(1)
        open_log = QPushButton("OPEN LOG")
        open_log.setObjectName("secondary")
        open_log.setCursor(Qt.CursorShape.PointingHandCursor)
        open_log.clicked.connect(self.open_log)
        open_folder = QPushButton("OPEN LOG FOLDER")
        open_folder.setObjectName("secondary")
        open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_PATH.parent))))
        row.addWidget(open_log)
        row.addWidget(open_folder)
        diag_layout.addSpacing(10)
        diag_layout.addLayout(row)
        diag_layout.addStretch(1)
        layout.addWidget(diagnostics)
        layout.addSpacing(12)

        about, about_layout = self.card("ABOUT", "Local build · PCSG00615 version 1.00")
        text = QLabel(
            "Recompilation by "
            "<a href='https://github.com/ch1ppyone' style='color:#c8102e;'>ch1ppyone</a>"
            " — this launcher only uses files you provide.<br>"
            "Source, licences and third-party notices are in the repository.")
        text.setOpenExternalLinks(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setObjectName("body")
        text.setWordWrap(True)
        cr = QLabel(
            "Tokyo Ghoul: JAIL © 石田スイ／集英社・東京喰種製作委員会\n"
            "©2015 BANDAI NAMCO Entertainment Inc.\n"
            "All rights to the game, its characters and assets belong to their respective owners.\n"
            "This recompilation does not include any copyrighted game content.")
        cr.setObjectName("muted")
        cr.setWordWrap(True)
        about_layout.addSpacing(8)
        about_layout.addWidget(text)
        about_layout.addSpacing(10)
        about_layout.addWidget(cr)
        row = QHBoxLayout()
        row.addStretch(1)
        github = QPushButton("GITHUB")
        github.setObjectName("secondary")
        github.setCursor(Qt.CursorShape.PointingHandCursor)
        github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/ch1ppyone")))
        licence = QPushButton("OPEN LICENCE")
        licence.setObjectName("secondary")
        licence.setCursor(Qt.CursorShape.PointingHandCursor)
        licence.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT / "LICENSE"))))
        third = QPushButton("THIRD-PARTY NOTICES")
        third.setObjectName("secondary")
        third.setCursor(Qt.CursorShape.PointingHandCursor)
        third.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(NATIV / "THIRD_PARTY.md"))))
        build = QPushButton("OPEN BUILD FOLDER")
        build.setObjectName("secondary")
        build.setCursor(Qt.CursorShape.PointingHandCursor)
        build.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(RECOMP_DIR))))
        row.addWidget(github)
        row.addWidget(licence)
        row.addWidget(third)
        row.addWidget(build)
        about_layout.addSpacing(10)
        about_layout.addLayout(row)
        about_layout.addStretch(1)
        layout.addWidget(about)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------------- settings
    def load_values(self) -> None:
        values = self.runtime.read()
        def number(key: str, default: int) -> int:
            try:
                return int(float(values.get(key, default)))
            except ValueError:
                return default
        scale = number("render_scale", 1)
        index = self.resolution.findData(scale)
        self.resolution.setCurrentIndex(index if index >= 0 else 0)
        rate = number("frame_rate", 30)
        index = self.fps.findData(rate)
        self.fps.setCurrentIndex(index if index >= 0 else 0)
        index = self.fit.findData(values.get("aspect", "fit"))
        self.fit.setCurrentIndex(index if index >= 0 else 0)
        index = self.aspect.findData(values.get("aspect_ratio", "native"))
        self.aspect.setCurrentIndex(index if index >= 0 else 0)
        index = self.osd.findData(number("osd", 0))
        self.osd.setCurrentIndex(index if index >= 0 else 0)
        self.fullscreen.setChecked(number("fullscreen", 0) != 0)
        try:
            volume = float(values.get("volume", 1.0))
        except ValueError:
            volume = 1.0
        self.volume.setValue(round(max(0.0, min(1.0, volume)) * 100))
        page = int(self.settings.value("page", 0) or 0)
        self.show_page(page if 0 <= page <= 4 else 0)

    def persist(self, *_args) -> None:
        if self._loading:
            return
        self.runtime.write({
            "render_scale": self.resolution.currentData() or 1,
            "frame_rate": self.fps.currentData() or 30,
            "aspect": self.fit.currentData() or "fit",
            "aspect_ratio": self.aspect.currentData() or "native",
            "osd": self.osd.currentData() or 0,
            "fullscreen": 1 if self.fullscreen.isChecked() else 0,
            "volume": round(self.volume.value() / 100, 2),
        })
        self.update_status("Display settings saved for the next start.")

    def refresh_bindings(self) -> None:
        values = self.runtime.read()
        for key, _label, _group, default in KEY_BINDINGS:
            self.bind_buttons[key].set_idle_text(values.get(key, default))

    def bind_key(self, key: str, value: str) -> None:
        self.runtime.write({key: value})
        self.settings.setValue(f"binds/{key}", value)
        self.refresh_bindings()
        self.update_status(f"Saved: {value} bound.")

    def reset_bindings(self) -> None:
        self.runtime.write({key: default for key, _label, _group, default in KEY_BINDINGS})
        for key, _label, _group, _default in KEY_BINDINGS:
            self.settings.remove(f"binds/{key}")
        self.refresh_bindings()
        self.update_status("Keyboard defaults restored.")

    # ---------------------------------------------------------------- logging
    def toggle_logging(self, _state: int) -> None:
        enabled = self.logging.isChecked()
        self.settings.setValue("logging", "true" if enabled else "false")
        self.settings.sync()
        if enabled:
            try:
                with LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(f"\n# session {datetime.datetime.now().isoformat(timespec='seconds')}\n")
            except OSError as exc:
                self.update_status(f"Cannot write the log: {exc}")
                return
            self.update_status(f"System log enabled: {LOG_PATH}")
        else:
            self.update_status("System log disabled.")

    def open_log(self) -> None:
        if LOG_PATH.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_PATH)))
        else:
            QMessageBox.information(self, "No log yet", "Enable the system log and run a build first.")

    # ---------------------------------------------------------------- data import
    def choose_file(self, key: str, filt: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a local file", str(DATA_DIR), filt)
        if not path:
            return
        candidate = Path(path)
        ok, detail = {"pkg": self.pkg_info, "licence": self.licence_info,
                      "firmware": self.pup_info}[key](candidate)
        if not ok:
            QMessageBox.warning(self, "Invalid file", detail)
            return
        target = DATA_DIR / candidate.name
        if candidate.resolve() != target.resolve():
            shutil.copy2(candidate, target)
        self.settings.remove(f"paths/{key}")
        self.append(f"Copied the validated {key} into data/{target.name}.")
        self.refresh_data()

    def browse_data_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a folder or mounted disk with the game data", str(Path.home()))
        if not folder:
            return
        source = Path(folder)
        pkg = self.find_file(source, ("*.pkg", "*.PKG"))
        licence = self.find_file(source, ("work.bin", "*.rif", "*.RIF"))
        pup = self.find_file(source, ("PSVUPDAT.PUP", "PSP2UPDAT.PUP", "*.PUP", "*.pup"))
        missing = [name for name, value in (("PKG", pkg), ("licence", licence), ("firmware", pup)) if value is None]
        if missing:
            message = "Missing: " + ", ".join(missing)
            QMessageBox.warning(self, "Incomplete game data", message)
            self.update_status("Data check failed: " + message)
            return
        assert pkg and licence and pup
        for checker, path in ((self.pkg_info, pkg), (self.licence_info, licence), (self.pup_info, pup)):
            ok, detail = checker(path)
            if not ok:
                QMessageBox.warning(self, "Invalid game data", detail)
                self.update_status("Data check failed: " + detail)
                return
        for source_file in (pkg, licence, pup):
            if source_file.resolve() != (DATA_DIR / source_file.name).resolve():
                shutil.copy2(source_file, DATA_DIR / source_file.name)
        for key in ("pkg", "licence", "firmware"):
            self.settings.remove(f"paths/{key}")
        self.append("Copied the validated PKG, licence and firmware into data/.")
        self.refresh_data()

    # ---------------------------------------------------------------- state
    def set_data_state(self, state: str) -> None:
        self.data_state = state
        if state == "checking":
            self.set_badge("CHECKING DATA", "badgeWait")
            self.detail_label.setText("Checking the local PKG, licence and firmware…")
            self.browse.hide()
            self.play.setEnabled(False)
            self.play.setText("CHECKING…")
        elif state == "ready":
            self.set_badge("DATA VERIFIED", "badgeOk")
            self.detail_label.setText("Game data is ready. No path selection is needed — press Prepare & Play.")
            self.browse.hide()
            self.play.setEnabled(True)
            self.update_play_caption()
        elif state == "invalid":
            self.set_badge("DATA INVALID", "badgeBad")
            self.browse.show()
            self.browse.setText("REPLACE")
            self.play.setEnabled(False)
            self.play.setText("DATA INVALID")
        else:
            self.set_badge("DATA NOT FOUND", "badgeBad")
            self.detail_label.setText("Put your PKG, matching work.bin/.rif and PSVUPDAT.PUP into data/, "
                                      "or press Browse to copy them from a disk.")
            self.browse.show()
            self.browse.setText("BROWSE")
            self.play.setEnabled(False)
            self.play.setText("DATA NOT FOUND")
        self.refresh_build_status()

    def set_badge(self, text: str, style_name: str) -> None:
        self.data_badge.setText(text)
        self.data_badge.setObjectName(style_name)
        self.data_badge.style().unpolish(self.data_badge)
        self.data_badge.style().polish(self.data_badge)

    def refresh_build_status(self) -> None:
        firmware = any((DUMP / "firmware").glob("*/version.txt")) if (DUMP / "firmware").is_dir() else False
        licence = any((DUMP / "licenses").glob("*.rif")) if (DUMP / "licenses").is_dir() else False
        game = (GAME_DIR / "elf" / "eboot.bin.elf").is_file()
        build = GAME_EXE.is_file()
        for key, ready in (("firmware", firmware), ("licence", licence), ("game", game), ("build", build)):
            self.build_rows[key].setText("✓ ready" if ready else "— not yet")
            self.build_rows[key].setObjectName("ok" if ready else "muted")
            self.build_rows[key].style().unpolish(self.build_rows[key])
            self.build_rows[key].style().polish(self.build_rows[key])
        if self.data_state == "ready":
            self.play.setEnabled(True)
            self.update_play_caption()
            self.update_ready_text()

    def update_play_caption(self) -> None:
        self.play.setText("PLAY JAIL" if GAME_EXE.is_file() else "PREPARE && PLAY")

    def update_ready_text(self) -> None:
        if self.data_state != "ready":
            return
        if GAME_EXE.is_file():
            self.detail_label.setText("Game data is ready. No path selection is needed — press PLAY JAIL.")
            self.update_status("Game data verified. Press PLAY JAIL.")
        else:
            self.detail_label.setText("Game data is ready. No path selection is needed — press Prepare & Play.")
            self.update_status("Game data verified. Nothing to choose — press Prepare & Play.")

    def update_status(self, text: str) -> None:
        self.status.setText(text)

    # ---------------------------------------------------------------- pipeline
    def play_clicked(self) -> None:
        if self.process:
            return
        if self.data_state != "ready":
            QMessageBox.warning(self, "Game data", "Game data is missing or invalid.\n\n"
                                                   "Put the PKG, licence and firmware into data/ or use Browse.")
            self.show_page(1)
            return
        self.cancelled = False
        self.stages = []
        pkg, licence, pup = (self.inputs["pkg"], self.inputs["licence"], self.inputs["firmware"])
        assert pkg and licence and pup
        firmware_ready = (DUMP / "firmware").is_dir() and any((DUMP / "firmware").glob("*/version.txt"))
        if not firmware_ready:
            self.stages.append(("Vita firmware", ["firmware", str(pup)], False))
        self.stages.append(("Licence", ["licenses", "import", str(licence)], False))
        first_build = not (GAME_DIR / "elf" / "eboot.bin.elf").is_file()
        if first_build:
            self.stages.append(("Decrypt & build", ["add", str(pkg), "--license", str(licence)], False))
        else:
            self.stages.append(("Update build", ["ready", TITLE], False))
        self.stage = 0
        self.stage_fraction = 0.0
        self.progress.setValue(0)
        self.progress.show()
        self.append("Starting the local pipeline.")
        self.show_page(0)
        self.run_next()

    def pipeline_command(self, args: list[str]) -> list[str]:
        return [sys.executable, str(PIPELINE), *args]

    def process_environment(self) -> "QProcessEnvironment":
        from PyQt6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("ATIV_DUMP", str(DUMP))
        env.insert("ATIV_PACKS", str(NATIV / "packs"))
        env.insert("ATIV_MAC_TOOLCHAIN", os.environ.get("ATIV_MAC_TOOLCHAIN", str(Path.home() / "toolchains" / "ativ-mac")))
        env.insert("PYTHONUNBUFFERED", "1")
        return env

    def run_next(self) -> None:
        if self.cancelled:
            return
        if self.stage >= len(self.stages):
            self.finish_pipeline(True)
            return
        name, args, _optional = self.stages[self.stage]
        argv = self.pipeline_command(args)
        self.append(f"\n== {name} ==\n$ {' '.join(argv)}")
        self.update_status(f"{name}…")
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(NATIV))
        self.process.setProcessEnvironment(self.process_environment())
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_output)
        self.process.finished.connect(self.stage_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.play.setEnabled(False)
        self.play.setText("WORKING…")
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.process.start(argv[0], argv[1:])

    def read_output(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        data += bytes(self.process.readAllStandardError()).decode(errors="replace")
        if not data:
            return
        self.append(data.rstrip())
        percentages = re.findall(r"(\d+(?:\.\d+)?)%", data)
        if percentages:
            self.stage_fraction = min(1.0, float(percentages[-1]) / 100.0)
            self.update_progress()

    def update_progress(self) -> None:
        if not self.stages:
            return
        value = int((self.stage + self.stage_fraction) * 100 / len(self.stages))
        self.progress.setRange(0, 100)
        self.progress.setValue(min(100, max(0, value)))

    def stage_finished(self, code: int, _status: QProcess.ExitStatus) -> None:
        self.read_output()
        if self.cancelled:
            self.finish_pipeline(False, "Stopped by user.")
            return
        if code != 0:
            name, _args, optional = self.stages[self.stage]
            if not optional:
                self.process = None
                self.finish_pipeline(False, f"The stage '{name}' failed with exit code {code}.")
                return
            self.append(f"Warning: the optional stage '{name}' failed; continuing.")
        self.stage += 1
        self.stage_fraction = 0.0
        self.update_progress()
        self.process = None
        QTimer.singleShot(80, self.run_next)

    def process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.process = None
            self.finish_pipeline(False, "Could not start the local pipeline. Run ./JAIL-PyQt.command again.")

    def finish_pipeline(self, ok: bool, message: str = "") -> None:
        self.process = None
        self.progress.hide()
        self.stop_button.setEnabled(False)
        self.stop_button.hide()
        self.refresh_build_status()
        self.update_play_caption()
        self.play.setEnabled(self.data_state == "ready")
        if message:
            self.append(message)
            self.update_status(message)
            tail = "\n".join(self.output_tail[-18:])
            detail = message + ("\n\nLast output:\n" + tail if tail else "")
            if not self.logging.isChecked():
                detail += "\n\nEnable Settings > Write system log for the full output."
            QMessageBox.warning(self, "Pipeline stopped", detail[-1800:])
        if ok:
            self.progress.setValue(100)
            self.append("\nPipeline complete.")
            self.update_status("Pipeline complete. Starting the game…")
            QTimer.singleShot(150, self.launch_game)

    def stop_pipeline(self) -> None:
        self.cancelled = True
        if self.process:
            self.process.kill()
        else:
            self.finish_pipeline(False, "Stopped by user.")

    def launch_game(self) -> None:
        if not GAME_EXE.is_file():
            self.update_status("Native build not found. Prepare & Play again.")
            return
        env_keys = {"ATIV_DUMP": str(DUMP), "ATIV_PACKS": str(NATIV / "packs"),
                    "ATIV_MAC_TOOLCHAIN": os.environ.get("ATIV_MAC_TOOLCHAIN",
                                                         str(Path.home() / "toolchains" / "ativ-mac"))}
        previous = {key: os.environ.get(key) for key in env_keys}
        os.environ.update(env_keys)
        try:
            started, _pid = QProcess.startDetached(
                sys.executable, [str(PIPELINE), "run", TITLE], str(NATIV))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        if not started:
            self.update_status("The game could not be started.")
            return
        self.append("Game launched.")
        self.update_status("Game launched. Close its window when you are done.")
        self.play.setEnabled(False)
        self.play.setText("GAME RUNNING")
        QTimer.singleShot(4000, self.enable_play)

    def enable_play(self) -> None:
        if self.data_state == "ready":
            self.play.setEnabled(True)
            self.update_play_caption()

    # ---------------------------------------------------------------- navigation
    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button:
            button.setChecked(True)
        if not self._loading:
            self.settings.setValue("page", index)
            self.settings.sync()

    def append(self, text: str) -> None:
        clean = text.replace("\x1b", "")
        self.output_tail.extend(clean.splitlines())
        if len(self.output_tail) > 300:
            del self.output_tail[:-300]
        if self.logging.isChecked():
            try:
                with LOG_PATH.open("a", encoding="utf-8") as handle:
                    handle.write(clean + "\n")
            except OSError:
                pass

    def closeEvent(self, event) -> None:
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.sync()
        super().closeEvent(event)


def main() -> int:
    # A player's launch must not inherit automated test overrides from a shell.
    for key in list(os.environ):
        if key.startswith("TEST_") or key in {"INPUT_FILE", "INPUT_SCRIPT", "AUDIO_DUMP",
                                              "RECOMP_HEADLESS", "RECOMP_SETTINGS"}:
            os.environ.pop(key, None)

    app = QApplication(sys.argv)
    app.setApplicationName("Tokyo Ghoul JAIL Recompiled")
    app.setOrganizationName("JAIL")
    icon = NATIV / "assets" / "jail" / "icon-512.png"
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    app.setFont(QFont("Helvetica Neue" if sys.platform == "darwin" else "Segoe UI", 12))
    app.setStyleSheet(STYLE)
    launcher = Launcher()
    launcher.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
