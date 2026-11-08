"""VocaloidTTS - Tkinter desktop front-end."""
from __future__ import annotations

import json
import math
import os
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk
import tkinter.font as tkfont

from . import __version__
from .edits import (CharEdit, EditSet, load_userdict, parse_reading,
                    save_userdict)
from .paths import appdata_dir, localappdata_dir
from .pinyin import char_readings
from .progress import Cancelled, Reporter
from .project import SUFFIX, Project, load_project, save_project
from .prosody import STYLE_PRESETS, Song, VoiceOptions, compose
from .tray import CloseHook, TrayIcon
from .voicebank import (Voicebank, VoicebankRoot, add_voicebank_root,
                        detect_voicebanks, export_voicebank_roots,
                        get_jobplugin_dir, get_v4_exe, get_v5_exe,
                        get_voicebank_roots, import_voicebank_roots,
                        remove_voicebank_root, scan_voicebank_folder,
                        set_v4_exe, set_v5_exe, v4_available, v5_available)
from .jobfile import default_job_path, write_job
from .textio import decode_text
from .vsqx import write_vsqx
from .exporters import FORMATS, write_svip, write_svip3, write_ustx

FONT = "Microsoft YaHei UI"
BG = "#0b0e13"
PANEL = "#12151c"
CARD = "#171a21"
CARD2 = "#1b202a"
LINE = "#262d3a"
TEXT = "#e8ecf2"
MUTED = "#8b93a7"
ACCENT = "#53d3c7"
ACCENT2 = "#b08cff"
WARN = "#ffd166"
DANGER = "#ff8fa3"

TONE_COLORS = {1: "#6ee7d8", 2: "#8fd3ff", 3: "#ffd166", 4: "#ff8fa3", 5: "#a7b0c4"}
TONE_NAMES = {1: "阴平", 2: "阳平", 3: "上声", 4: "去声", 5: "轻声"}

PRESETS = {
    "自然朗读": ("read", "你好，欢迎来到语调教工坊。今天想聊点什么呢？"),
    "戏剧朗读": ("drama", "你给我听好了——这件事，绝对不能就这么算了！"),
    "新闻播报": ("news", "各位观众晚上好，今天是十月二十五日，欢迎收看今天的节目。"),
    "甜系撒娇": ("sweet", "你怎么才来呀，人家等了你好久好久呢。"),
    "气声耳语": ("soft", "别害怕，我就在你身边，闭上眼睛慢慢睡吧。"),
    "故事旁白": ("story", "很久很久以前，在山的那一边，住着一位会唱歌的少女。"),
}

PINYIN_PRESETS = {
    "自然朗读": ("read", "ni3 hao3, huan1 ying2 lai2 dao4 yu3 diao4 jiao4 gong1 fang1. jin1 tian1 xiang3 liao2 dian3 shen2 me5 ne5?"),
    "戏剧朗读": ("drama", "ni3 gei3 wo3 ting1 hao3 le5, zhe4 jian4 shi4, jue2 dui4 bu4 neng2 jiu4 zhe4 me5 suan4 le5!"),
    "新闻播报": ("news", "ge4 wei4 guan1 zhong4 wan3 shang4 hao3, jin1 tian1 shi4 shi2 yue4 er4 shi2 wu3 ri4, huan1 ying2 shou1 kan4 jin1 tian1 de5 jie2 mu4."),
    "甜系撒娇": ("sweet", "ni3 zen3 me5 cai2 lai2 ya5, ren2 jia1 deng3 le5 ni3 hao3 jiu3 hao3 jiu3 ne5."),
    "气声耳语": ("soft", "bie2 hai4 pa4, wo3 jiu4 zai4 ni3 shen1 bian1, bi4 shang4 yan3 jing1 man4 man4 shui4 ba5."),
    "故事旁白": ("story", "hen3 jiu3 hen3 jiu3 yi3 qian2, zai4 shan1 de5 na4 yi4 bian1, zhu4 zhe5 yi2 wei4 hui4 chang4 ge1 de5 shao4 nv3."),
}

STYLE_LABELS = {k: v["label"] for k, v in STYLE_PRESETS.items()}
LABEL_TO_STYLE = {v: k for k, v in STYLE_LABELS.items()}


def note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    # VOCALOID uses C3 = MIDI 60; match the editor's octave labels.
    octave = midi // 12 - 2
    return f"{names[midi % 12]}{octave}"


class RoundedChip(tk.Canvas):
    """Small rounded preset chip."""

    def __init__(self, parent, text, command):
        self._text = text
        self._command = command
        font = tkfont.Font(font=(FONT, 8))
        width = font.measure(text) + 24
        super().__init__(parent, width=width, height=28, bg=CARD,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", lambda e: self._command())
        self.bind("<Enter>", lambda e: self._draw(True))
        self.bind("<Leave>", lambda e: self._draw(False))
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Map>", lambda e: self._draw())
        self.after_idle(self._draw)
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w = int(self.cget("width"))
        if h <= 1:
            h = int(self.cget("height"))
        r = 9
        fill = "#27303f" if hover else CARD2
        fg = TEXT if hover else "#aeb7c8"
        # Tk arcs: 0=right, 90=top, 180=left, 270=bottom.
        self.create_arc(0, 0, 2 * r, 2 * r, start=90, extent=90,
                        style="pieslice", fill=fill, outline="")
        self.create_arc(w - 2 * r, 0, w, 2 * r, start=0, extent=90,
                        style="pieslice", fill=fill, outline="")
        self.create_arc(0, h - 2 * r, 2 * r, h, start=180, extent=90,
                        style="pieslice", fill=fill, outline="")
        self.create_arc(w - 2 * r, h - 2 * r, w, h, start=270, extent=90,
                        style="pieslice", fill=fill, outline="")
        self.create_rectangle(r, 0, w - r, h, fill=fill, outline="")
        self.create_rectangle(0, r, w, h - r, fill=fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=(FONT, 8))


class RoundedButton(tk.Canvas):
    """Canvas button with genuinely rounded corners and hover feedback."""

    def __init__(self, parent, text, command, kind="primary", padx=12):
        colors = {
            "primary": (ACCENT, "#08211f", "#7ce9de"),
            "accent": (ACCENT2, "#170f26", "#c9b2ff"),
            "ghost": (CARD, "#c4ccda", "#27303f"),
            "danger": (DANGER, "#2a0e14", "#ffb8c4"),
        }
        self._fill, self._fg, self._hover = colors.get(kind, colors["primary"])
        self._text = text
        self._command = command
        self._kind = kind
        font = tkfont.Font(font=(FONT, 9, "bold"))
        width = font.measure(text) + 2 * padx + 10
        super().__init__(parent, width=width, height=38, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", lambda e: self._command())
        self.bind("<ButtonRelease-1>", lambda e: self._draw(hover=False))
        self.bind("<Enter>", lambda e: self._draw(hover=True))
        self.bind("<Leave>", lambda e: self._draw(hover=False))
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Map>", lambda e: self._draw())
        self.after_idle(self._draw)
        self._draw()

    def _draw(self, hover=False):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w = int(self.cget("width"))
        if h <= 1:
            h = int(self.cget("height"))
        r = 13
        fill = self._hover if hover else self._fill
        border = {"primary": "#7ce9de", "accent": "#c9b2ff",
                  "ghost": "#2a3240"}.get(self._kind, "#7ce9de")
        self._round_rect(0, 0, w, h, r, fill=border, outline="")
        self._round_rect(1, 1, w - 1, h - 1, r - 1, fill=fill, outline="")
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg,
                         font=(FONT, 9, "bold"))

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        # Tk arcs: 0=right, 90=top, 180=left, 270=bottom.
        self.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r,
                        start=90, extent=90, style="pieslice", **kw)
        self.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r,
                        start=0, extent=90, style="pieslice", **kw)
        self.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2,
                        start=180, extent=90, style="pieslice", **kw)
        self.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2,
                        start=270, extent=90, style="pieslice", **kw)
        self.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
        self.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)


class RoundedSlider(tk.Canvas):
    """Rounded track + circular knob; click, drag, wheel and keyboard."""

    def __init__(self, parent, lo, hi, value, command,
                 step=0.01, default=None, height=24):
        super().__init__(parent, width=1, height=height, bg=CARD, highlightthickness=0,
                         bd=0, cursor="hand2", takefocus=True)
        self.lo, self.hi = float(lo), float(hi)
        self.step = step
        self.default = float(value if default is None else default)
        self.command = command
        self.var = tk.DoubleVar(value=float(value))
        self._hover = False
        self._focus = False
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Double-Button-1>", lambda e: self._reset())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<FocusIn>", lambda e: self._set_focus(True))
        self.bind("<FocusOut>", lambda e: self._set_focus(False))
        self.bind("<Left>", lambda e: self._nudge(-1))
        self.bind("<Right>", lambda e: self._nudge(1))
        self.bind("<MouseWheel>", self._on_wheel)
        self._draw()

    def get(self) -> float:
        return self.var.get()

    def set(self, value):
        self.var.set(max(self.lo, min(self.hi, float(value))))
        self._draw()

    def _set_hover(self, flag):
        self._hover = flag
        self._draw()

    def _set_focus(self, flag):
        self._focus = flag
        self._draw()

    def _quantize(self, value):
        value = max(self.lo, min(self.hi, value))
        if self.step:
            value = round(value / self.step) * self.step
        return max(self.lo, min(self.hi, value))

    def _coords(self):
        w = max(40, self.winfo_width())
        h = max(20, self.winfo_height())
        return 9, w - 9, h / 2

    def _x_for(self, value):
        x0, x1, _ = self._coords()
        return x0 + (x1 - x0) * (value - self.lo) / (self.hi - self.lo)

    def _value_for(self, x):
        x0, x1, _ = self._coords()
        ratio = (x - x0) / max(1.0, x1 - x0)
        return self.lo + ratio * (self.hi - self.lo)

    def _draw(self):
        self.delete("all")
        x0, x1, y = self._coords()
        xk = self._x_for(self.get())
        r = 7 if self._hover or self._focus else 6
        self.create_line(x0, y, x1, y, width=6, capstyle="round", fill="#2a3240")
        if xk > x0 + 1:
            self.create_line(x0, y, xk, y, width=6, capstyle="round",
                             fill="#7ce9de" if self._hover else ACCENT)
        if self._focus:
            self.create_oval(xk - r - 3, y - r - 3, xk + r + 3, y + r + 3,
                             outline="#2d6f69", width=1)
        self.create_oval(xk - r, y - r, xk + r, y + r,
                         fill=ACCENT if self._hover else "#6ee7d8",
                         outline=CARD, width=2)

    def _on_press(self, event):
        self.focus_set()
        self._apply_x(event.x)

    def _on_drag(self, event):
        self._apply_x(event.x)

    def _apply_x(self, x):
        self.var.set(self._quantize(self._value_for(x)))
        self._draw()
        self.command()

    def _nudge(self, direction):
        self.set(self._quantize(self.get() + direction * (self.step or 0.01)))
        self.command()
        return "break"

    def _on_wheel(self, event):
        self._nudge(1 if event.delta > 0 else -1)

    def _reset(self):
        self.set(self.default)
        self.command()
        return "break"


def default_output_dir() -> Path:
    docs = None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
            docs = Path(str(winreg.QueryValueEx(k, "Personal")[0]))
    except Exception:
        docs = None
    if docs is None:
        docs = Path.home() / "Documents"
    base = docs / "VocaloidTTS"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path.cwd() / "VocaloidTTS_Output"
        base.mkdir(exist_ok=True)
    return base


def resource_path(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel


#: 逐字修饰的下拉选项；None 表示「跟自动规则走」。
STRESS_CHOICES = [("自动", None), ("弱 -0.3", -0.3), ("强 +0.3", 0.3),
                  ("很强调 +0.6", 0.6)]
DUR_CHOICES = [("自动", None), ("短 0.7×", 0.7), ("长 1.3×", 1.3),
               ("更长 1.8×", 1.8)]
PAUSE_CHOICES = [("自动", None), ("100 ms", 100), ("200 ms", 200),
                 ("350 ms", 350), ("600 ms", 600), ("1 秒", 1000)]


def choice_label(choices, value):
    """把值还原成下拉框里的显示文本；找不到就用第一项（自动）。"""
    for label, candidate in choices:
        if candidate == value:
            return label
    return choices[0][0]


def choice_value(choices, label):
    """把下拉框文本还原成值；未知文本按「自动」处理。"""
    for name, value in choices:
        if name == label:
            return value
    return None


class VocaloidTTSApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("VocaloidTTS · VOCALOID4/5 · X Studio · OpenUTAU")
        self.geometry("1280x900")
        self.minsize(1080, 760)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tray = None
        self._quitting = False
        self._busy = False
        self._cancel = False
        self.recent: list[str] = []
        self._set_window_icon()
        self._close_hook = None
        self.bind("<<VocaloidTTSClose>>", lambda e: self._on_close())
        try:
            self._close_hook = CloseHook(self, self._on_close,
                                          on_drop=self._on_drop_files)
        except Exception:
            self._close_hook = None

        # Scanning walks the registry and several disks, so it runs on a worker
        # thread after the window is up.  Until it finishes the list is empty
        # and every consumer has to cope with that.
        self.voicebanks: list[Voicebank] = []
        self._scanning = False
        self._want_bank_id = ""
        self._want_bank_index: int | None = None
        self.vb_index = 0
        self.song: Song | None = None
        self.last_path: str | None = None
        self.last_job: str | None = None
        self.export_format = "vsqx"
        self._loading = False
        self.settings = self._load_settings()
        self.edits = EditSet()
        self.dictionary = load_userdict(appdata_dir() / "userdict.json")
        self.project_path: str | None = None
        self._autosave_job = None
        self._previewing = False

        self._init_style()
        self._build()
        self._apply_settings()
        self._log("VocaloidTTS 已就绪。输入文字后点“生成工程”，选择要导出的格式。")
        custom_roots = get_voicebank_roots()
        if custom_roots:
            self._log("自定义声库目录：" + "；".join(r.path for r in custom_roots))
        if v4_available():
            self._log(f"VOCALOID4：{get_v4_exe()}")
        if v5_available():
            self._log(f"VOCALOID5：{get_v5_exe()}")
        if not v4_available() and not v5_available():
            self._log("未找到 VOCALOID4/5；生成 VSQX 仍可用，但载入编辑器需要路径。")
            # 启动时不再弹窗；用户点「载入 V4/V5」时再询问。
        self.after(50, self._start_voicebank_scan)
        self.after(300, self._restore_autosave)

    def _post(self, fn, *args) -> None:
        """把回调排到主线程。

        Tk 的 ``after`` 在工作线程里可用，但窗口已经在销毁时 ``_register`` 会
        抛 ``RuntimeError``；那种情况下丢掉回调就行，不该让工作线程带着异常退出。
        """
        try:
            self.after(0, fn, *args)
        except Exception:
            pass

    def _set_window_icon(self) -> None:
        ico = resource_path("assets/vocaloidtts.ico")
        png = resource_path("assets/vocaloidtts.png")
        try:
            if ico.exists():
                self.iconbitmap(default=str(ico))
        except Exception:
            pass
        try:
            if png.exists():
                self._icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def _ensure_tray(self) -> bool:
        if self._tray is not None:
            return True
        if TrayIcon is None:
            return False
        try:
            icon = str(resource_path("assets/vocaloidtts.ico"))
            tray = TrayIcon(
                icon,
                on_show=lambda: self._post(self._show_from_tray),
                on_quit=lambda: self._post(self._quit_app),
                tooltip="VocaloidTTS",
            )
            ok = tray.start()
            if ok:
                self._tray = tray
                return True
        except Exception:
            pass
        self._tray = None
        return False

    def _show_from_tray(self) -> None:
        try:
            self.deiconify()
            self.state("normal")
            self.lift()
            self.focus_force()
            self._log("已从托盘恢复 VocaloidTTS。")
        except Exception:
            pass

    def _quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            self._save_settings()
        except Exception:
            pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        if self._close_hook is not None:
            try:
                self._close_hook.restore()
            except Exception:
                pass
            self._close_hook = None
        # 退出时把还在排队的自动保存取消掉，否则 destroy 之后它还会触发，
        # Tk 会报 invalid command name。
        job = getattr(self, "_autosave_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
            self._autosave_job = None
        try:
            self.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ UI
    def _init_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=CARD2, background=CARD2,
                        foreground=TEXT, arrowcolor=ACCENT, bordercolor=LINE,
                        lightcolor=LINE, darkcolor=LINE, insertcolor=TEXT,
                        selectbackground="#2b3a48", selectforeground=TEXT, padding=4)
        style.map("TCombobox",
                  fieldbackground=[("readonly", CARD2)],
                  foreground=[("readonly", TEXT)],
                  background=[("active", CARD2)])
        style.configure("TScale", background=CARD, troughcolor="#3b475c",
                        bordercolor=CARD, lightcolor=CARD, darkcolor=CARD,
                        sliderlength=13, gripcount=0)
        style.configure("TCheckbutton", background=CARD, foreground=TEXT,
                        focuscolor=CARD, font=(FONT, 10))
        style.map("TCheckbutton", background=[("active", CARD)],
                  foreground=[("active", TEXT)])

    def _build(self) -> None:
        header = tk.Frame(self, bg=BG, height=70)
        header.pack(fill="x", padx=22, pady=(8, 2))
        header.pack_propagate(False)

        logo = tk.Canvas(header, width=44, height=44, bg=BG, highlightthickness=0)
        logo.pack(side="left", pady=6)
        try:
            self._logo_img = tk.PhotoImage(file=str(resource_path("assets/vocaloidtts_44.png")))
            logo.create_image(22, 22, image=self._logo_img)
        except Exception:
            logo.create_oval(2, 2, 42, 42, fill="#152b2c", outline=ACCENT, width=1.5)
            logo.create_text(22, 22, text="V", fill=ACCENT, font=(FONT, 12, "bold"))

        title_box = tk.Frame(header, bg=BG)
        title_box.pack(side="left", padx=12, pady=4)
        tk.Label(title_box, text="VocaloidTTS", bg=BG, fg=TEXT,
                 font=(FONT, 18, "bold")).pack(anchor="w")
        tk.Label(title_box, text="把文字变成歌姬的说话声 · 自动生成音符、拼音、PIT 音高曲线与表情参数",
                 bg=BG, fg=MUTED, font=(FONT, 8)).pack(anchor="w", pady=(2, 0))

        pill = tk.Frame(header, bg="#142321", highlightbackground="#23514b",
                        highlightthickness=1)
        pill.pack(side="right", pady=10)
        tk.Label(pill, text="V4/V5", bg="#142321", fg=ACCENT,
                 font=(FONT, 8, "bold"), padx=9, pady=4).pack(side="left")
        # 启动时扫描还没跑，voicebanks 为空，这里不能下标取第一个。
        first_bank = self.voicebanks[0] if self.voicebanks else None
        self.bank_pill = tk.Label(
            pill,
            text=(self._bank_badge_text(first_bank) if first_bank
                  else "  未检测到声库"),
            bg="#142321", fg="#79a9a2", font=(FONT, 8), padx=5)
        self.bank_pill.pack(side="left")

        tk.Frame(self, bg=LINE, height=1).pack(fill="x", padx=22, pady=(1, 8))

        self.status = tk.StringVar(value="就绪")
        bar = tk.Frame(self, bg="#0e1117", height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status, bg="#0e1117", fg=MUTED,
                 font=(FONT, 8), anchor="w").pack(side="left", padx=(22, 10))
        self._build_progress(bar)
        self.path_label = tk.Label(bar, text="", bg="#0e1117", fg="#5d6678",
                                   font=(FONT, 8), anchor="e")
        self.path_label.pack(side="right", padx=(0, 22))
        tk.Label(bar, text=f"v{__version__}  ·  VSQX 4.0    ", bg="#0e1117",
                 fg="#4d5668", font=(FONT, 8)).pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=(0, 4))
        body.columnconfigure(0, weight=0, minsize=438)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.rowconfigure(0, weight=1)
        left.rowconfigure(1, weight=0)
        self._build_text_card(left)
        self._build_options_card(left)

        right = tk.Frame(body, bg=BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        self._build_actions(right)
        self._build_preview(right)
        self._build_log(right)

    def _build_progress(self, bar) -> None:
        """状态栏里的进度条与取消按钮；只在生成期间显示。"""
        self._progress_width = 150
        self.progress_canvas = tk.Canvas(
            bar, width=self._progress_width, height=6, bg="#1a1f2b",
            highlightthickness=0, bd=0)
        self._progress_rect = self.progress_canvas.create_rectangle(
            0, 0, 0, 6, fill=ACCENT, width=0)
        self.progress_pct = tk.Label(bar, text="", bg="#0e1117", fg="#7f8a9d",
                                     font=(FONT, 8), width=4, anchor="w")
        self.btn_cancel = tk.Label(bar, text="✕ 取消", bg="#0e1117", fg="#e06c75",
                                   font=(FONT, 8), cursor="hand2")
        self.btn_cancel.bind("<Button-1>", lambda e: self._request_cancel())
        self._progress_widgets = (self.progress_canvas, self.progress_pct,
                                  self.btn_cancel)

    def _show_progress(self) -> None:
        self.progress_canvas.pack(side="left", padx=(0, 6))
        self.progress_pct.pack(side="left", padx=(0, 8))
        self.btn_cancel.configure(text="✕ 取消", fg="#e06c75")
        self.btn_cancel.pack(side="left")
        self._set_progress(0.0)

    def _hide_progress(self) -> None:
        for widget in self._progress_widgets:
            widget.pack_forget()

    def _set_progress(self, fraction: float) -> None:
        """只在主线程调用；worker 线程通过 after(0, ...) 转发过来。"""
        fraction = 0.0 if fraction < 0.0 else 1.0 if fraction > 1.0 else fraction
        self.progress_canvas.coords(self._progress_rect, 0, 0,
                                    self._progress_width * fraction, 6)
        self.progress_pct.configure(text=f"{fraction * 100:.0f}%")

    def _request_cancel(self) -> None:
        if not getattr(self, "_busy", False):
            return
        self._cancel = True
        self.btn_cancel.configure(text="取消中…", fg="#8b93a7")
        self.status.set("正在取消…")
        self._log("已请求取消，等当前检查点停下。")

    def _card(self, parent, pad=14) -> tk.Frame:
        outer = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=True, padx=pad, pady=pad)
        return outer, inner

    def _build_text_card(self, parent) -> None:
        outer, inner = self._card(parent, pad=10)
        outer.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="输入文本", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(side="left")
        self.char_count = tk.Label(head, text="0 字", bg=CARD, fg=MUTED,
                                   font=(FONT, 8))
        self.char_count.pack(side="right")
        self.mode_var = tk.StringVar(value="中文文本")
        self.mode_combo = ttk.Combobox(head, textvariable=self.mode_var,
                                       values=["中文文本", "拼音输入"],
                                       state="readonly", width=8, font=(FONT, 8))
        self.mode_combo.pack(side="right", padx=(0, 8))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())
        self.import_chip = RoundedChip(head, "导入 TXT", self.import_text_file)
        self.import_chip.pack(side="right", padx=(0, 8))
        self.edit_chip = RoundedChip(head, "纠音", self.edit_pronunciation)
        self.edit_chip.pack(side="right", padx=(0, 8))

        presets = tk.Frame(inner, bg=CARD)
        presets.pack(fill="x", pady=(10, 8))
        for name in PRESETS:
            chip = RoundedChip(presets, name, lambda n=name: self._apply_preset(n))
            chip.pack(side="left", padx=(0, 6))

        wrap = tk.Frame(inner, bg=CARD2, highlightbackground="#2a3140", highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        self.text = tk.Text(wrap, bg=CARD2, fg=TEXT, insertbackground=ACCENT,
                            selectbackground="#2b4b48", selectforeground=TEXT,
                            relief="flat", bd=0, padx=12, pady=10, wrap="word",
                            height=7, undo=True, font=(FONT, 12), spacing1=2, spacing3=4)
        self.text.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview)
        sb.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=sb.set)
        self.text.insert("1.0", PRESETS["自然朗读"][1])
        self.char_count.configure(text=f"{len(PRESETS['自然朗读'][1])} 字")
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.edit_modified(False)

        self.hint_label = tk.Label(
            inner, text="小提示：逗号停半拍，句号换气；问号会自动抬高句尾。可直接把 .txt 拖进窗口。",
            bg=CARD, fg="#636d80", font=(FONT, 8), anchor="w")
        self.hint_label.pack(fill="x", pady=(8, 0))

    def _build_options_card(self, parent) -> None:
        outer, inner = self._card(parent, pad=10)
        outer.grid(row=1, column=0, sticky="ew")
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(0, 6))
        tk.Label(head, text="演唱设置", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="点击生成后更新", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="right")

        row1 = tk.Frame(inner, bg=CARD)
        row1.pack(fill="x", pady=(2, 6))
        vb_head = tk.Frame(row1, bg=CARD)
        vb_head.pack(fill="x")
        tk.Label(vb_head, text="歌姬", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="left")
        self.vb_add_btn = tk.Button(
            vb_head, text="＋ 添加文件夹", command=self.add_voicebank_folder,
            bg=CARD, fg=ACCENT, activebackground=CARD2, activeforeground=TEXT,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            font=(FONT, 8), padx=2, pady=0)
        self.vb_add_btn.pack(side="right")
        self.vb_rescan_btn = tk.Button(
            vb_head, text="↻ 重扫", command=self.rescan_voicebanks,
            bg=CARD, fg=MUTED, activebackground=CARD2, activeforeground=TEXT,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            font=(FONT, 8), padx=2, pady=0)
        self.vb_rescan_btn.pack(side="right", padx=(0, 8))
        self.vb_manage_btn = tk.Button(
            vb_head, text="管理点位…", command=self.manage_voicebank_roots,
            bg=CARD, fg=MUTED, activebackground=CARD2, activeforeground=TEXT,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            font=(FONT, 8), padx=2, pady=0)
        self.vb_manage_btn.pack(side="right", padx=(0, 8))
        tk.Label(vb_head, text="启动时自动扫描", bg=CARD, fg="#5f6a7d",
                 font=(FONT, 7)).pack(side="right", padx=(0, 10))
        self.vb_var = tk.StringVar()
        self.vb_combo = ttk.Combobox(row1, textvariable=self.vb_var, state="readonly",
                                     values=[v.label for v in self.voicebanks],
                                     font=(FONT, 9))
        self.vb_combo.pack(fill="x", pady=(2, 0))
        if self.voicebanks:
            self.vb_combo.current(0)
        self.vb_combo.bind("<<ComboboxSelected>>", lambda e: self._on_voicebank_change())
        self.vb_note = tk.Label(
            row1, text="找不到歌姬时，点“＋ 添加文件夹”选择声库根目录",
            bg=CARD, fg="#5f6a7d", font=(FONT, 7), anchor="w")
        self.vb_note.pack(fill="x", pady=(2, 0))

        row2 = tk.Frame(inner, bg=CARD)
        row2.pack(fill="x", pady=(0, 4))
        tk.Label(row2, text="风格", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(anchor="w")
        self.style_var = tk.StringVar(value=STYLE_LABELS["read"])
        self.style_combo = ttk.Combobox(row2, textvariable=self.style_var, state="readonly",
                                        values=list(STYLE_LABELS.values()), font=(FONT, 9))
        self.style_combo.pack(fill="x", pady=(2, 0))
        self.style_combo.bind("<<ComboboxSelected>>", lambda e: self._on_style_change())

        row3 = tk.Frame(inner, bg=CARD)
        row3.pack(fill="x", pady=(2, 2))
        tk.Label(row3, text="BPM", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left")
        self.bpm_var = tk.StringVar(value="120")
        self.bpm_spin = tk.Spinbox(
            row3, from_=40, to=240, increment=1, textvariable=self.bpm_var,
            width=5, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
            buttonbackground=CARD2, font=(FONT, 9), highlightthickness=1,
            highlightbackground=LINE, command=self._on_option_change)
        self.bpm_spin.pack(side="left", padx=(5, 14), ipady=2)
        tk.Label(row3, text="拍号", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left")
        self.num_var = tk.StringVar(value="4")
        self.num_spin = tk.Spinbox(
            row3, from_=1, to=16, increment=1, textvariable=self.num_var,
            width=3, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
            buttonbackground=CARD2, font=(FONT, 9), highlightthickness=1,
            highlightbackground=LINE, command=self._on_option_change)
        self.num_spin.pack(side="left", padx=(5, 2), ipady=2)
        tk.Label(row3, text="/", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left")
        self.den_var = tk.StringVar(value="4")
        self.den_combo = ttk.Combobox(
            row3, textvariable=self.den_var, values=["2", "4", "8", "16"],
            width=3, state="readonly", font=(FONT, 9))
        self.den_combo.pack(side="left", padx=(2, 0), ipady=1)
        tk.Label(row3, text="载入", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left", padx=(14, 4))
        self.target_var = tk.StringVar(value="V5" if v5_available() else "V4")
        self.target_combo = ttk.Combobox(
            row3, textvariable=self.target_var, values=["V4", "V5"],
            width=4, state="readonly", font=(FONT, 9))
        self.target_combo.pack(side="left", ipady=1)
        self.target_combo.bind("<<ComboboxSelected>>", lambda e: self._on_option_change())
        for w in (self.bpm_spin, self.num_spin, self.den_combo):
            w.bind("<FocusOut>", lambda e: self._on_option_change())
            w.bind("<Return>", lambda e: self._on_option_change())
        self.den_combo.bind("<<ComboboxSelected>>", lambda e: self._on_option_change())

        self.sliders = {}

        tone_head = tk.Frame(inner, bg=CARD)
        tone_head.pack(fill="x", pady=(4, 0))
        tk.Label(tone_head, text="声调音高", bg=CARD, fg="#aeb7c8",
                 font=(FONT, 8, "bold")).pack(side="left")
        tk.Label(tone_head, text="拖动 / 滚轮微调 / 双击复位", bg=CARD, fg="#5f6a7d",
                 font=(FONT, 7)).pack(side="right")

        tone_grid = tk.Frame(inner, bg=CARD)
        tone_grid.pack(fill="x", pady=(1, 2))
        for c in range(5):
            tone_grid.columnconfigure(c, weight=1)
        tone_specs = [
            ("pitch", "一声", 67),
            ("tone2", "二声", 66),
            ("tone3", "三声", 64),
            ("tone4", "四声", 65),
            ("tone5", "轻声", 64),
        ]
        for i, (key, label, dflt) in enumerate(tone_specs):
            cell = tk.Frame(tone_grid, bg=CARD)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0),
                      pady=(2, 2))
            top = tk.Frame(cell, bg=CARD)
            top.pack(fill="x")
            tk.Label(top, text=label, bg=CARD, fg="#aeb7c8",
                     font=(FONT, 8)).pack(side="left")
            val = tk.Label(top, text=note_name(dflt), bg=CARD, fg=ACCENT,
                           font=(FONT, 8, "bold"))
            val.pack(side="right")
            slider = RoundedSlider(cell, 43, 84, dflt, self._on_option_change,
                                   step=1, default=dflt, height=22)
            slider.pack(fill="x", pady=(1, 0))
            self.sliders[key] = (slider, val, lambda v: note_name(int(float(v))))

        grid = tk.Frame(inner, bg=CARD)
        grid.pack(fill="x", pady=(7, 0))
        for c in range(4):
            grid.columnconfigure(c, weight=1)
        specs = [
            ("rate", "语速", 0.7, 1.4, 1.0, 0.01, lambda v: f"{v:.2f}×"),
            ("tone", "起伏", 0.4, 2.0, 1.35, 0.01, lambda v: f"{v:.2f}"),
            ("energy", "力度", 0.5, 1.8, 1.25, 0.01, lambda v: f"{v:.2f}×"),
            ("pause", "停顿", 0.4, 1.8, 1.0, 0.01, lambda v: f"{v:.2f}×"),
            ("breath", "气声", 0, 100, 12, 1, lambda v: f"{int(float(v))}"),
            ("vibrato", "颤音", 0, 100, 16, 1, lambda v: f"{int(float(v))}"),
            ("gender", "性别", -100, 100, 0, 1, lambda v: f"{int(float(v)):+d}"),
        ]
        for i, (key, label, lo, hi, dflt, step, fmt) in enumerate(specs):
            cell = tk.Frame(grid, bg=CARD)
            col = i % 4
            cell.grid(row=i // 4, column=col, sticky="ew",
                      padx=(0 if col == 0 else 8, 0), pady=(2, 4))
            top = tk.Frame(cell, bg=CARD)
            top.pack(fill="x")
            tk.Label(top, text=label, bg=CARD, fg="#aeb7c8", font=(FONT, 7)).pack(side="left")
            val = tk.Label(top, text=fmt(dflt), bg=CARD, fg=ACCENT, font=(FONT, 7, "bold"))
            val.pack(side="right")
            slider = RoundedSlider(cell, lo, hi, dflt, self._on_option_change,
                                   step=step, default=dflt, height=22)
            slider.pack(fill="x", pady=(0, 0))
            self.sliders[key] = (slider, val, fmt)

        bottom = tk.Frame(inner, bg=CARD)
        bottom.pack(fill="x", pady=(6, 0))
        tk.Label(bottom, text="轻声独立可调 · V4 同八度标记", bg=CARD, fg="#7f8a9d",
                 font=(FONT, 8)).pack(side="left")
        tk.Label(bottom, text="种子", bg=CARD, fg=MUTED, font=(FONT, 8)).pack(side="left", padx=(10, 4))
        self.seed_var = tk.StringVar(value="20261025")
        seed = tk.Entry(bottom, textvariable=self.seed_var, width=9, bg=CARD2, fg=TEXT,
                        insertbackground=ACCENT, relief="flat", font=(FONT, 8),
                        highlightbackground=LINE, highlightthickness=1)
        seed.pack(side="left", padx=(6, 0), ipady=3)
        seed.bind("<FocusOut>", lambda e: self._on_option_change())

    def _build_actions(self, parent) -> None:
        bar = tk.Frame(parent, bg=BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(12, 8))
        self.btn_generate = self._button(bar, "生成工程 ▼", self._show_generate_menu,
                                         "primary", 12)
        self.btn_generate.pack(side="left")
        self.btn_open = self._button(bar, "载入 V4/V5", self.generate_and_open, "accent", 14)
        self.btn_open.pack(side="left", padx=(7, 0))
        self.btn_install = self._button(bar, "安装插件", self.install_plugin, "ghost", 9)
        self.btn_install.pack(side="left", padx=(7, 0))
        self.btn_folder = self._button(bar, "输出目录", self.open_output_folder, "ghost", 9)
        self.btn_folder.pack(side="left", padx=(7, 0))
        self.btn_v4path = self._button(bar, "编辑器", self.choose_editor_path, "ghost", 8)
        self.btn_v4path.pack(side="left", padx=(7, 0))

    def _show_generate_menu(self) -> None:
        if getattr(self, "_gen_menu", None) is not None:
            try:
                self._gen_menu.unpost()
                self._gen_menu.destroy()
            except Exception:
                pass
        menu = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT,
                       activebackground=ACCENT, activeforeground="#08211f",
                       relief="flat", bd=0, font=(FONT, 9))
        self._gen_menu = menu
        for key in ("vsqx", "svip3", "ustx", "svip"):
            meta = FORMATS[key]
            menu.add_command(
                label=f"{meta['short']}  ·  {meta['extension']}",
                command=lambda k=key: self.generate(fmt=k))
        menu.add_separator()
        menu.add_command(label="保存项目…", command=self.save_project_dialog)
        menu.add_command(label="打开项目…", command=self.open_project_dialog)
        if self.recent:
            menu.add_separator()
            recent = tk.Menu(menu, tearoff=0, bg=CARD, fg=TEXT,
                             activebackground=ACCENT, activeforeground="#08211f",
                             relief="flat", bd=0, font=(FONT, 9))
            for path in self.recent[:8]:
                recent.add_command(
                    label=Path(path).name,
                    command=lambda p=path: self._open_recent(p))
            menu.add_cascade(label="最近工程", menu=recent)
        try:
            x = self.btn_generate.winfo_rootx()
            y = self.btn_generate.winfo_rooty() + self.btn_generate.winfo_height() + 2
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _build_preview(self, parent) -> None:
        # 音高曲线只在点「预览音高」时算一次：每次按键都 compose 会让长文本
        # 卡死，这条限制从 1.1 就保留着。
        outer, inner = self._card(parent, pad=12)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=1)
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text="生成信息", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="按需分析，不随打字重算", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="left", padx=10)
        self.btn_preview = self._button(head, "预览音高", self.preview_pitch,
                                        "ghost", 9)
        self.btn_preview.pack(side="right")

        body = tk.Frame(inner, bg="#0f1218", highlightbackground="#222936",
                        highlightthickness=1)
        body.pack(fill="both", expand=True, pady=(4, 8))
        self.pitch_canvas = tk.Canvas(body, bg="#0b0e13", height=120,
                                      highlightthickness=0, bd=0)
        self.pitch_canvas.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.info_hint = tk.Label(
            body,
            text="点右上角「预览音高」分析当前文本\n\n"
                 "输入或调参数不会自动重算\n"
                 "点击“生成工程”后，这里显示工程统计",
            bg="#0f1218", fg="#66748b", justify="center",
            font=(FONT, 9), wraplength=300)
        self.info_hint.pack(fill="x", padx=6, pady=(4, 6))

        self.stats = tk.Frame(inner, bg=CARD)
        self.stats.pack(fill="x")
        self.stat_labels = {}
        for key, label in (("syll", "音节"), ("dur", "时长"), ("range", "音域"),
                           ("peak", "最高音"), ("neutral", "轻声"), ("size", "文件")):
            box = tk.Frame(self.stats, bg=CARD)
            box.pack(side="left", padx=(0, 12))
            tk.Label(box, text=label, bg=CARD, fg="#636d80", font=(FONT, 7)).pack(anchor="w")
            lab = tk.Label(box, text="—", bg=CARD, fg=TEXT, font=(FONT, 9, "bold"))
            lab.pack(anchor="w")
            self.stat_labels[key] = lab

    def preview_pitch(self) -> None:
        """按当前文本与参数算一次音高，画在预览区。"""
        if getattr(self, "_previewing", False):
            self._log("音高分析还在跑，稍等一下。")
            return
        text = self.text.get("1.0", "end-1c")
        if not text.strip():
            messagebox.showinfo("预览音高", "先写点文字再预览。")
            return
        if len(text) > 4000:
            if not messagebox.askyesno(
                    "预览音高",
                    f"文本有 {len(text)} 字，分析可能要几秒。继续吗？"):
                return
        mode = self._mode()
        options = self._voice_options()
        bpm = self._bpm()
        numerator, denominator = self._meter()
        edits = self._active_edits(text) if mode == "chinese" else {}
        dictionary = dict(self.dictionary) if mode == "chinese" else {}
        self._previewing = True
        self._log("正在分析音高…")

        def worker() -> None:
            try:
                song = compose(text, options, bpm=bpm, numerator=numerator,
                               denominator=denominator, input_mode=mode,
                               edits=edits, dictionary=dictionary)
            except Exception as exc:
                self._post(self._preview_failed, exc)
                return
            self._post(self._draw_pitch, song)

        threading.Thread(target=worker, daemon=True).start()

    def _preview_failed(self, exc: Exception) -> None:
        self._previewing = False
        self._log(f"音高分析失败：{exc}")

    def _draw_pitch(self, song: Song) -> None:
        self._previewing = False
        canvas = self.pitch_canvas
        canvas.delete("all")
        points = sorted(song.controls.get("P") or [], key=lambda p: p[0])
        if not points or not song.notes:
            self.info_hint.configure(text="没有可画的音高（文本里没有音节）",
                                     fg="#8b93a7")
            return
        width = max(160, canvas.winfo_width())
        height = max(80, canvas.winfo_height())
        total = max(1, song.total_ticks)
        pbs = song.options.pbs
        notes = song.notes
        sampled: list[tuple[int, float]] = []
        lowest, highest = math.inf, -math.inf
        idx = 0
        for tick, value in points:
            while idx + 1 < len(notes) and tick >= notes[idx].start + notes[idx].dur:
                idx += 1
            pitch = notes[idx].midi + value * pbs / 8192
            sampled.append((tick, pitch))
            lowest = min(lowest, pitch)
            highest = max(highest, pitch)
        if highest - lowest < 1.0:
            middle = (highest + lowest) / 2
            lowest, highest = middle - 0.5, middle + 0.5
        pad = 10

        def xy(tick: int, pitch: float) -> tuple[float, float]:
            x = pad + (width - 2 * pad) * tick / total
            y = height - pad - (height - 2 * pad) * (pitch - lowest) / (
                highest - lowest)
            return x, y

        previous_phrase = None
        for syl in song.syllables:
            if syl.phrase == previous_phrase:
                continue
            previous_phrase = syl.phrase
            x, _ = xy(int(getattr(syl, "_start_tick", 0)), lowest)
            canvas.create_line(x, pad, x, height - pad, fill="#1b2330")
        coords: list[float] = []
        for tick, pitch in sampled:
            x, y = xy(tick, pitch)
            coords.extend((x, y))
        if len(coords) >= 4:
            canvas.create_line(*coords, fill=ACCENT, width=2)
        canvas.create_text(pad, pad, anchor="nw",
                           text=f"{lowest:.1f} – {highest:.1f} st",
                           fill="#5f6a7d", font=(FONT, 7))
        self.info_hint.configure(
            text=f"音高预览：{len(song.notes)} 音节 · {song.duration_s:.2f}s\n"
                 f"音域 {highest - lowest:.1f} 半音，竖线是换气点",
            fg=ACCENT)

    def _build_log(self, parent) -> None:
        outer = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        outer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="x", padx=12, pady=8)
        tk.Label(inner, text="运行日志", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(anchor="w")
        self.log = tk.Text(inner, height=2, bg=CARD, fg="#9aa4b8", relief="flat",
                           font=("Consolas", 8), wrap="word", state="disabled")
        self.log.pack(fill="x", pady=(2, 0))

    # --------------------------------------------------------------- helpers
    def _button(self, parent, text, cmd, kind="primary", padx=14):
        return RoundedButton(parent, text, cmd, kind, padx)

    def _log(self, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self._append_log_file(line)
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message)

    def _append_log_file(self, line: str) -> None:
        """Mirror the in-app log to disk so failures leave a trace."""
        try:
            path = localappdata_dir() / "log.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                if path.stat().st_size > 1_000_000:
                    path.replace(path.with_name("log.old.txt"))
            except OSError:
                pass
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except Exception:
            pass

    # -------------------------------------------------------- editor location
    def _check_editor_startup(self) -> None:
        if v4_available():
            self._log(f"VOCALOID4：{get_v4_exe()}")
        if v5_available():
            self._log(f"VOCALOID5：{get_v5_exe()}")
        if v4_available() or v5_available():
            return
        answer = messagebox.askyesno(
            "未找到 VOCALOID4/5",
            "没有在默认位置找到 VOCALOID4.exe 或 VOCALOID5.exe。\n\n"
            "生成工程 / 拼音 / 音素本身不依赖编辑器；\n"
            "但“载入 V4/V5”和“安装 V4 插件”需要路径。\n\n"
            "现在设置编辑器路径吗？")
        if answer:
            self.choose_editor_path(startup=True)
        else:
            self._log("已跳过编辑器路径设置；生成 VSQX 仍可用。")

    def choose_v4_path(self, startup: bool = False) -> bool:
        current = Path(get_v4_exe())
        initialdir = str(current.parent) if current.parent.exists() else r"C:\Program Files (x86)"
        path = filedialog.askopenfilename(
            title="选择 VOCALOID4.exe",
            initialdir=initialdir,
            filetypes=[("VOCALOID4", "VOCALOID4.exe"), ("可执行文件", "*.exe")])
        if not path:
            self._log("已取消 V4 路径设置。")
            return False
        try:
            exe = set_v4_exe(path)
        except Exception as exc:
            messagebox.showerror("路径无效", str(exc))
            return False
        self._log(f"VOCALOID4 路径已设置：{exe}")
        if not startup:
            messagebox.showinfo("VOCALOID4 路径",
                                f"已设置：\n{exe}\n\n"
                                "现在可以使用“载入 V4/V5”和“安装 V4 插件”。")
        return True

    def choose_v5_path(self, startup: bool = False) -> bool:
        current = Path(get_v5_exe())
        initialdir = str(current.parent) if current.parent.exists() else r"D:\VOCALOID6SE\Editor"
        path = filedialog.askopenfilename(
            title="选择 VOCALOID5.exe",
            initialdir=initialdir,
            filetypes=[("VOCALOID5", "VOCALOID5.exe"), ("可执行文件", "*.exe")])
        if not path:
            self._log("已取消 V5 路径设置。")
            return False
        try:
            exe = set_v5_exe(path)
        except Exception as exc:
            messagebox.showerror("路径无效", str(exc))
            return False
        self._log(f"VOCALOID5 路径已设置：{exe}")
        if not startup:
            messagebox.showinfo("VOCALOID5 路径",
                                f"已设置：\n{exe}\n\n"
                                "V5 可直接打开本工具生成的 VSQX；\n"
                                "V4 Job Plugin 不适用于 V5。")
        return True

    def choose_editor_path(self, startup: bool = False) -> bool:
        # If both editors exist, ask which path to change; otherwise pick the
        # only installed one.
        if v4_available() and v5_available() and not startup:
            answer = messagebox.askyesnocancel(
                "设置编辑器路径",
                "当前同时检测到 VOCALOID4 和 VOCALOID5。\n\n"
                "是：设置 VOCALOID4 路径\n"
                "否：设置 VOCALOID5 路径\n"
                "取消：不改")
            if answer is None:
                return False
            return self.choose_v4_path() if answer else self.choose_v5_path()
        if v5_available() and not v4_available():
            return self.choose_v5_path(startup)
        if v4_available():
            return self.choose_v4_path(startup)
        answer = messagebox.askyesno(
            "选择编辑器", "设置哪一个？\n\n是：VOCALOID4\n否：VOCALOID5")
        return self.choose_v4_path(startup) if answer else self.choose_v5_path(startup)

    def _bpm(self) -> float:
        try:
            value = float(str(self.bpm_var.get()).strip())
        except Exception:
            value = 120.0
        return max(40.0, min(240.0, value))

    @staticmethod
    def _fmt_num(value: object) -> str:
        try:
            f = float(value)
            return str(int(f)) if abs(f - round(f)) < 0.001 else f"{f:g}"
        except Exception:
            return "120"

    def _meter(self) -> tuple[int, int]:
        try:
            num = int(str(self.num_var.get()).strip())
        except Exception:
            num = 4
        num = max(1, min(16, num))
        try:
            den = int(str(self.den_var.get()).strip())
        except Exception:
            den = 4
        if den not in (2, 4, 8, 16):
            den = 4
        return num, den

    def _mode(self) -> str:
        return "pinyin" if self.mode_var.get() == "拼音输入" else "chinese"

    def _editor_target(self) -> str:
        return "v5" if self.target_var.get().upper().startswith("V5") else "v4"

    def _on_mode_change(self) -> None:
        pinyin = self._mode() == "pinyin"
        content = self.text.get("1.0", "end").strip()
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in content)
        if pinyin:
            self.hint_label.configure(
                text="空格分隔拼音，数字标声调：ni3 hao3 shi4 jie4；可用 ni3|n_i 覆盖音素。")
            if has_chinese:
                self._loading = True
                self.text.delete("1.0", "end")
                self.text.insert("1.0", PINYIN_PRESETS["自然朗读"][1])
                self.text.edit_modified(False)
                self._loading = False
                self.char_count.configure(text=f"{len(PINYIN_PRESETS['自然朗读'][1])} 字")
                self._log("已切换到拼音直输模式，并载入拼音示例。")
            else:
                self._log("已切换到拼音直输模式：不会再经过汉字多音字判断。")
        else:
            self.hint_label.configure(
                text="小提示：逗号停半拍，句号换气；问号会自动抬高句尾。可直接把 .txt 拖进窗口。")
            if content and not has_chinese:
                self._loading = True
                self.text.delete("1.0", "end")
                self.text.insert("1.0", PRESETS["自然朗读"][1])
                self.text.edit_modified(False)
                self._loading = False
                self.char_count.configure(text=f"{len(PRESETS['自然朗读'][1])} 字")
                self._log("已切换到中文文本模式，并载入中文示例。")
            else:
                self._log("已切换到中文文本模式。")

    # ---------------------------------------------------------- txt import
    def import_text_file(self) -> None:
        path = filedialog.askopenfilename(
            title="导入文本到输入框",
            filetypes=[("文本文件", "*.txt *.text *.md"),
                       ("所有文件", "*.*")])
        if path:
            self._load_text_file(path)

    def _on_drop_files(self, paths: list[str]) -> None:
        if not paths:
            return
        path = paths[0]
        suffix = Path(path).suffix.lower()
        if suffix in (".vsqx", ".svip3", ".ustx", ".svip"):
            messagebox.showinfo(
                "这是工程文件",
                f"{Path(path).name} 是已经生成的工程。\n\n"
                "请用对应的编辑器打开它；这里只能导入文本（.txt / .text / .md）。")
            return
        if suffix not in (".txt", ".text", ".md"):
            messagebox.showwarning(
                "不支持的文件",
                f"请拖入 .txt / .text / .md 文件。\n\n{path}")
            return
        if len(paths) > 1:
            self._log(f"拖入了 {len(paths)} 个文件，只读取第一个：{Path(path).name}")
        self._load_text_file(path)

    def _load_text_file(self, path: str) -> None:
        p = Path(path)
        try:
            raw = p.read_bytes()
        except Exception as exc:
            messagebox.showerror("无法读取文件", f"{p}\n\n{exc}")
            return
        text, encoding = decode_text(raw)
        if not text:
            text, encoding = raw.decode("utf-8", errors="replace"), "utf-8 (replace)"
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if len(text) > 200_000:
            text = text[:200_000]
            self._log("文本超过 20 万字符，已截断；建议拆分后再生成。")
        self._loading = True
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)
            self.text.edit_modified(False)
        finally:
            self._loading = False
        self.char_count.configure(text=f"{len(text)} 字")
        self._log(f"已导入文本：{p.name}（{len(text)} 字，编码 {encoding}）")

    def _apply_preset(self, name: str) -> None:
        if self._mode() == "pinyin":
            style, text = PINYIN_PRESETS[name]
        else:
            style, text = PRESETS[name]
        self._loading = True
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.edit_modified(False)
        self._loading = False
        self.char_count.configure(text=f"{len(text)} 字")
        self.style_var.set(STYLE_LABELS[style])
        self._on_style_change(silent=True)
        self._on_option_change()
        self._log(f"已套用预设：{name}")

    def _on_style_change(self, silent: bool = False) -> None:
        style = LABEL_TO_STYLE.get(self.style_var.get(), "read")
        p = STYLE_PRESETS[style]
        for key, val in (("pitch", p["pitch"]), ("tone2", p["tone2"]),
                         ("tone3", p["tone3"]), ("tone4", p["tone4"]),
                         ("tone5", p["tone5"]),
                         ("rate", p["rate"]), ("tone", p["tone"]),
                         ("energy", p["energy"]), ("breath", p["breath"]),
                         ("vibrato", p["vibrato"])):
            if key in self.sliders:
                self.sliders[key][0].set(val)
        if not silent:
            self._on_option_change()

    def _on_option_change(self) -> None:
        for var, lab, fmt in self.sliders.values():
            try:
                lab.configure(text=fmt(var.get()))
            except Exception:
                pass
        # Deliberately no compose/render here: sliders and typing must stay
        # responsive.  A song is built only by "生成 VSQX".
        self._schedule_autosave()

    def _on_text_modified(self, event=None) -> None:
        if self._loading:
            return
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        content = self.text.get("1.0", "end").strip()
        self.char_count.configure(text=f"{len(content)} 字")
        if self.edits.chars and not self.edits.matches(
                self.text.get("1.0", "end-1c")):
            self._log("文本已改动，之前的逐字纠音对不上了，生成时会被忽略。")
        self._schedule_autosave()

    # ------------------------------------------------------ 逐字纠音
    def _text_offset(self, index: str) -> int:
        """把 Tk 的 ``line.col`` 索引换成 0 起算的字符偏移。

        ``Text.count`` 在起止相同时返回 ``None``，这里直接用取子串的方式算，
        简单且在纠音这种低频路径上足够快。
        """
        return len(self.text.get("1.0", index))

    def _selection_offsets(self) -> tuple[int, int]:
        """返回选区的 [起, 止)；没有选区时取光标所在的一个字。"""
        try:
            start = self._text_offset(self.text.index("sel.first"))
            end = self._text_offset(self.text.index("sel.last"))
        except tk.TclError:
            pos = self._text_offset(self.text.index("insert"))
            return pos, pos + 1
        return start, max(start + 1, end)

    def edit_pronunciation(self) -> None:
        """给选中的字逐个改拼音/声调。"""
        content = self.text.get("1.0", "end-1c")
        start, end = self._selection_offsets()
        if start >= len(content):
            messagebox.showinfo("纠音", "请先把光标放到要改的字上，或选中几个字。")
            return
        end = min(end, len(content))
        if end - start > 24:
            if not messagebox.askyesno(
                    "纠音",
                    f"选中了 {end - start} 个字，逐个改太累。\n"
                    "先处理前 24 个，剩下的可以再选一次。继续吗？"):
                return
            end = start + 24
        fragment = content[start:end]
        # 用 char_readings 而不是 syl.src：后者是归一化之后的下标，直接当
        # 原文下标去取会让对话框里每一行的「自动读音」整体错位。
        auto = char_readings(fragment, self.dictionary)
        self._pronunciation_dialog(start, fragment, auto)

    def _pronunciation_dialog(self, start: int, fragment: str,
                              auto: dict[int, tuple[str, int]]) -> None:
        win = tk.Toplevel(self)
        win.title("逐字纠音与修饰")
        win.configure(bg=BG)
        win.transient(self)
        win.resizable(False, False)

        tk.Label(win, text="拼音留空 = 保持自动读音；其余留「自动」= 跟规则走",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=14,
                                                       pady=(12, 8))
        grid = tk.Frame(win, bg=BG)
        grid.pack(fill="both", expand=True, padx=14)
        for col, title in enumerate(("字", "拼音", "声调", "强调", "拉长", "停顿")):
            tk.Label(grid, text=title, bg=BG, fg=MUTED, font=(FONT, 8)).grid(
                row=0, column=col, sticky="w", padx=(0, 8))

        rows = []
        for i, ch in enumerate(fragment):
            offset = start + i
            current = self.edits.get(offset)
            auto_py, auto_tone = auto.get(i, ("", 0))
            py = current.pinyin if current and current.pinyin else auto_py
            tone = current.tone if current and current.tone else auto_tone
            tk.Label(grid, text=ch, bg=BG, fg=TEXT, font=(FONT, 12)).grid(
                row=i + 1, column=0, sticky="w", pady=2)
            py_var = tk.StringVar(value=py)
            tk.Entry(grid, textvariable=py_var, width=9, bg=CARD2, fg=TEXT,
                     insertbackground=ACCENT, relief="flat", font=(FONT, 9),
                     highlightbackground=LINE, highlightthickness=1).grid(
                row=i + 1, column=1, padx=(0, 8), pady=2, ipady=2)
            tone_var = tk.StringVar(
                value="自动" if not tone else ("轻声" if tone == 5 else str(tone)))
            ttk.Combobox(grid, textvariable=tone_var, width=4, state="readonly",
                         values=["自动", "1", "2", "3", "4", "轻声"],
                         font=(FONT, 9)).grid(row=i + 1, column=2,
                                              padx=(0, 8), pady=2)
            stress_var = tk.StringVar(value=choice_label(
                STRESS_CHOICES, current.stress if current else None))
            ttk.Combobox(grid, textvariable=stress_var, width=9, state="readonly",
                         values=[label for label, _ in STRESS_CHOICES],
                         font=(FONT, 9)).grid(row=i + 1, column=3,
                                              padx=(0, 8), pady=2)
            dur_var = tk.StringVar(value=choice_label(
                DUR_CHOICES, current.dur_scale if current else None))
            ttk.Combobox(grid, textvariable=dur_var, width=8, state="readonly",
                         values=[label for label, _ in DUR_CHOICES],
                         font=(FONT, 9)).grid(row=i + 1, column=4,
                                              padx=(0, 8), pady=2)
            pause_var = tk.StringVar(value=choice_label(
                PAUSE_CHOICES, current.pause_ms if current else None))
            ttk.Combobox(grid, textvariable=pause_var, width=7, state="readonly",
                         values=[label for label, _ in PAUSE_CHOICES],
                         font=(FONT, 9)).grid(row=i + 1, column=5, pady=2)
            rows.append((offset, ch, py_var, tone_var, stress_var, dur_var,
                         pause_var, auto_py, auto_tone))

        def apply() -> None:
            changed = 0
            for (offset, ch, py_var, tone_var, stress_var, dur_var, pause_var,
                 auto_py, auto_tone) in rows:
                pinyin = py_var.get().strip().lower()
                label = tone_var.get()
                tone = 0 if label == "自动" else (5 if label == "轻声" else int(label))
                edit = CharEdit(
                    char=ch,
                    pinyin="" if pinyin == auto_py else pinyin,
                    tone=0 if tone in (0, auto_tone) else tone,
                    stress=choice_value(STRESS_CHOICES, stress_var.get()),
                    dur_scale=choice_value(DUR_CHOICES, dur_var.get()),
                    pause_ms=choice_value(PAUSE_CHOICES, pause_var.get()),
                )
                if not edit.is_empty():
                    changed += 1
                self.edits.set(offset, edit)
            self.edits.take_snapshot(self.text.get("1.0", "end-1c"))
            self._log(f"已更新 {len(rows)} 个字，其中 {changed} 个是覆盖")
            win.destroy()

        def reset() -> None:
            for (offset, _ch, py_var, tone_var, stress_var, dur_var,
                 pause_var, _ap, _at) in rows:
                self.edits.set(offset, CharEdit())
                py_var.set("")
                tone_var.set("自动")
                stress_var.set(STRESS_CHOICES[0][0])
                dur_var.set(DUR_CHOICES[0][0])
                pause_var.set(PAUSE_CHOICES[0][0])
            self._log(f"已清除 {len(rows)} 个字的全部人工设置")

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(10, 12))
        self._button(bar, "全部恢复自动", reset, "ghost", 10).pack(side="left")
        self._button(bar, "编辑词典…", self.manage_userdict, "ghost", 9).pack(
            side="left", padx=(8, 0))
        self._button(bar, "确定", apply, "primary", 10).pack(side="right")
        self._button(bar, "取消", win.destroy, "ghost", 8).pack(
            side="right", padx=(0, 6))

    def manage_userdict(self) -> None:
        """用户专名词典：词语 → 带声调拼音，跨项目共享。"""
        win = tk.Toplevel(self)
        win.title("用户词典")
        win.configure(bg=BG)
        win.geometry("520x400")
        win.transient(self)

        tk.Label(win, text="词语 → 带声调的拼音（如 重明 → chong2 ming2）",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", padx=14,
                                                       pady=(12, 6))
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14)
        listbox = tk.Listbox(body, bg=CARD, fg=TEXT, selectbackground=ACCENT,
                             selectforeground="#08211f", font=(FONT, 9),
                             bd=0, highlightthickness=0)
        listbox.pack(fill="both", expand=True)

        def refresh() -> None:
            listbox.delete(0, "end")
            for word in sorted(self.dictionary):
                listbox.insert("end", f"{word}  →  {self.dictionary[word]}")

        def add() -> None:
            word = simpledialog.askstring("添加词条", "词语：", parent=win)
            if not word:
                return
            word = word.strip()
            if not word:
                return
            reading = simpledialog.askstring(
                "添加词条",
                f"「{word}」怎么读？\n每个字一个带声调数字的拼音，如 chong2 ming2：",
                parent=win)
            if not reading:
                return
            parsed = parse_reading(reading)
            if parsed is None or len(parsed) != len(word):
                messagebox.showerror(
                    "格式不对",
                    "每个字都要有一个带声调数字的拼音，数量也要对得上。",
                    parent=win)
                return
            self.dictionary[word] = " ".join(f"{py}{tone}"
                                             for py, tone in parsed)
            self._save_dictionary()
            refresh()

        def remove() -> None:
            sel = listbox.curselection()
            if not sel:
                return
            word = sorted(self.dictionary)[sel[0]]
            self.dictionary.pop(word, None)
            self._save_dictionary()
            refresh()

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(8, 12))
        self._button(bar, "添加", add, "primary", 8).pack(side="left")
        self._button(bar, "删除选中", remove, "ghost", 9).pack(
            side="left", padx=(6, 0))
        self._button(bar, "关闭", win.destroy, "ghost", 8).pack(side="right")
        refresh()

    def _save_dictionary(self) -> None:
        try:
            save_userdict(appdata_dir() / "userdict.json", self.dictionary)
            self._log(f"用户词典已保存：{len(self.dictionary)} 条")
        except Exception as exc:
            self._log(f"用户词典保存失败：{exc}")
            messagebox.showerror("保存失败", str(exc))

    def _active_edits(self, text: str) -> dict[int, CharEdit]:
        """取当前可用的纠音。

        文本改过时不整体放弃，而是把每条交给 _apply_char_edits 逐条校验：它
        要求「偏移处仍然是当初那个字」，对不上的那一条跳过。这样在末尾追加
        一句话不会让前面所有设置失效。
        """
        if not self.edits.chars:
            return {}
        if not self.edits.matches(text):
            self._log("文本与纠音快照不一致，逐字纠音按字符位置重新核对。")
        return dict(self.edits.chars)

    def _voice_options(self) -> VoiceOptions:
        style = LABEL_TO_STYLE.get(self.style_var.get(), "read")
        def val(key, default):
            try:
                return float(self.sliders[key][0].get())
            except Exception:
                return default
        try:
            seed = int(self.seed_var.get().strip() or "20261025")
        except ValueError:
            seed = 20261025
        return VoiceOptions(
            style=style,
            pitch=int(round(val("pitch", 67))),
            tone2_pitch=int(round(val("tone2", 66))),
            tone3_pitch=int(round(val("tone3", 64))),
            tone4_pitch=int(round(val("tone4", 65))),
            tone5_pitch=int(round(val("tone5", 64))),
            rate=val("rate", 1.0),
            tone_strength=val("tone", 1.35),
            energy=val("energy", 1.25),
            pause_scale=val("pause", 1.0),
            breath=int(round(val("breath", 12))),
            vibrato=int(round(val("vibrato", 16))),
            gender=int(round(val("gender", 0))),
            seed=seed,
            flat_notes=True,
            pbs=12,
        )

    def _update_stats(self) -> None:
        song = self.song
        if not song or not song.notes:
            for lab in self.stat_labels.values():
                lab.configure(text="—")
            return
        self.stat_labels["syll"].configure(text=str(len(song.notes)))
        self.stat_labels["dur"].configure(text=f"{song.duration_s:.2f}s")
        span = song.pitch_span
        self.stat_labels["range"].configure(text=f"{span[1]-span[0]:.1f} st")
        # Keep 最高音 consistent with 音域: both include the PIT curve, not
        # just the note anchors.
        self.stat_labels["peak"].configure(text=note_name(int(round(span[1]))))
        n5 = sum(1 for n in song.notes if n.syl.tone == 5)
        self.stat_labels["neutral"].configure(text=str(n5) if n5 else "—")
        self.stat_labels["size"].configure(text="—")

    # ---------------------------------------------------------------- actions
    def _validate(self) -> bool:
        if not self.text.get("1.0", "end").strip():
            messagebox.showwarning("没有文本", "请先输入要演唱的文字。")
            return False
        if not self.voicebanks:
            messagebox.showerror(
                "没有歌姬",
                "没有检测到可用的声库。\n\n"
                "请点「歌姬」右侧的「＋ 添加文件夹」，选择声库根目录"
                "（例如包含 .vvd 的文件夹）后再试。")
            return False
        return True

    @staticmethod
    def _bank_badge_text(vb: Voicebank) -> str:
        name = vb.name.lower()
        if "luo" in name:
            return "  LUO TIANYI · CHN"
        if "yuezheng" in name:
            return "  YUEZHENGLING · V3"
        if "yanhe" in name:
            return "  YANHE · CHN"
        if "xingchen" in name:
            return "  XINGCHEN · CHN"
        return "  " + vb.name.upper()

    def _update_bank_badge(self) -> None:
        if hasattr(self, "bank_pill"):
            bank = self._current_voicebank()
            text = self._bank_badge_text(bank) if bank else "  未检测到声库"
            self.bank_pill.configure(text=text)

    def _refresh_voicebanks(self, select_id: str | None = None,
                            force: bool = False) -> None:
        """重新扫描声库；扫描在后台线程跑，这里立即返回。"""
        self._start_voicebank_scan(select_id=select_id, force=force)

    def _start_voicebank_scan(self, select_id: str | None = None,
                              force: bool = False) -> None:
        if self._scanning:
            self._log("声库扫描还在进行，稍候再试。")
            return
        self._scanning = True
        if hasattr(self, "vb_note"):
            self.vb_note.configure(text="正在扫描声库…")
        self._log("正在扫描声库…")

        def worker() -> None:
            try:
                banks = detect_voicebanks(use_cache=not force)
            except Exception as exc:
                self._post(self._scan_failed, exc)
                return
            self._post(self._scan_finished, banks, select_id)

        threading.Thread(target=worker, daemon=True).start()

    def _scan_failed(self, exc: Exception) -> None:
        self._scanning = False
        if hasattr(self, "vb_note"):
            self.vb_note.configure(text="声库扫描失败；点“＋ 添加文件夹”手动指定")
        self._log(f"声库扫描失败：{exc}")

    def _scan_finished(self, banks: list[Voicebank],
                       select_id: str | None = None) -> None:
        self._scanning = False
        self.voicebanks = banks
        self.vb_combo["values"] = [v.label for v in banks]
        if select_id:
            self._want_bank_id = select_id
        self._restore_voicebank_selection()
        custom = get_voicebank_roots()
        extra = f"，自定义目录 {len(custom)} 个" if custom else ""
        self._log(f"声库扫描：{len(banks)} 个{extra}")
        if hasattr(self, "vb_note"):
            if banks:
                self.vb_note.configure(text="找不到歌姬时，点“＋ 添加文件夹”指定声库目录")
            else:
                self.vb_note.configure(text="没有检测到声库；点“＋ 添加文件夹”指定声库目录")

    def _restore_voicebank_selection(self) -> None:
        """把记住的声库 id（或旧配置里的下标）落到下拉框上。

        启动时扫描还没回来，所以选择要等扫描结束后再恢复一次。
        """
        if not self.voicebanks or not hasattr(self, "vb_combo"):
            return
        idx: int | None = None
        if self._want_bank_id:
            for i, vb in enumerate(self.voicebanks):
                if vb.id == self._want_bank_id:
                    idx = i
                    break
        if idx is None and self._want_bank_index is not None:
            if 0 <= self._want_bank_index < len(self.voicebanks):
                idx = self._want_bank_index
        self.vb_combo.current(0 if idx is None else idx)
        self._update_bank_badge()

    def rescan_voicebanks(self) -> None:
        self._refresh_voicebanks(force=True)

    def add_voicebank_folder(self) -> None:
        if self._scanning:
            self._log("声库扫描还在进行，稍候再添加目录。")
            return
        path = filedialog.askdirectory(
            title="选择歌姬声库文件夹（VOCALOID VoiceDB / 声库根目录）",
            mustexist=True)
        if not path:
            return
        # 和「重扫」共用 _scanning 标志，避免两条扫描线程互相覆盖结果
        self._scanning = True
        self.vb_note.configure(text=f"正在扫描 {Path(path).name}…")
        self._log(f"正在扫描声库目录：{path}")

        def worker() -> None:
            try:
                found = scan_voicebank_folder(path)
            except Exception as exc:
                self._post(self._add_folder_failed, exc)
                return
            self._post(self._add_folder_done, path, found)

        threading.Thread(target=worker, daemon=True).start()

    def _add_folder_failed(self, exc: Exception) -> None:
        self._scanning = False
        self.vb_note.configure(text="扫描失败；可以换个目录再试")
        self._log(f"扫描目录失败：{exc}")
        messagebox.showerror("扫描失败", str(exc))

    def _add_folder_done(self, path: str, found: list[Voicebank]) -> None:
        self._scanning = False
        if not found:
            self.vb_note.configure(text="这个文件夹里没有声库；换一个目录试试")
            messagebox.showwarning(
                "没有发现声库",
                "这个文件夹里没有找到 .vvd 声库文件。\n\n"
                "请选择 VoiceDB、歌姬库根目录，或包含声库的上级文件夹。")
            return
        before = {vb.id for vb in self.voicebanks}
        add_voicebank_root(path)
        new = [vb for vb in found if vb.id not in before]
        self._refresh_voicebanks(select_id=(new[0].id if new else None))
        if new:
            names = "、".join(vb.display for vb in new[:6])
            if len(new) > 6:
                names += f" 等 {len(new)} 个"
            messagebox.showinfo("已添加声库", f"发现并加入：\n{names}")
        else:
            messagebox.showinfo("目录已加入", "这些声库已经扫描到了，目录已保存。")

    def manage_voicebank_roots(self) -> None:
        win = tk.Toplevel(self)
        win.title("声库扫描点位")
        win.configure(bg=BG)
        win.geometry("760x420")
        win.transient(self)

        tk.Label(win, text="已添加的声库目录（双击可编辑 bs/pc）", bg=BG, fg=TEXT,
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=14, pady=(12, 6))

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        scroll = tk.Scrollbar(body)
        scroll.pack(side="right", fill="y")
        listbox = tk.Listbox(body, bg=CARD, fg=TEXT, selectbackground=ACCENT,
                             selectforeground="#08211f", font=(FONT, 9),
                             yscrollcommand=scroll.set, bd=0, highlightthickness=0)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.configure(command=listbox.yview)

        def refresh() -> None:
            listbox.delete(0, "end")
            for root in get_voicebank_roots():
                bits = [root.path]
                if root.bs is not None or root.pc is not None:
                    bits.append(f"bs={root.bs if root.bs is not None else '?'}"
                                f" pc={root.pc if root.pc is not None else '?'}")
                if root.display:
                    bits.append(f"显示={root.display}")
                if not root.enabled:
                    bits.append("（已禁用）")
                listbox.insert("end", "  ·  ".join(bits))

        def selected_root() -> VoicebankRoot | None:
            sel = listbox.curselection()
            if not sel:
                return None
            roots = get_voicebank_roots()
            if sel[0] >= len(roots):
                return None
            return roots[sel[0]]

        def remove() -> None:
            root = selected_root()
            if root is None:
                return
            remove_voicebank_root(root.path)
            refresh()
            self._refresh_voicebanks()
            self._log(f"已移除扫描点位：{root.path}")

        def edit() -> None:
            root = selected_root()
            if root is None:
                return
            current = ""
            if root.bs is not None or root.pc is not None:
                current = f"{root.bs if root.bs is not None else 0}," \
                          f"{root.pc if root.pc is not None else 0}"
            value = simpledialog.askstring(
                "覆盖 bs/pc", "输入 bs,pc（例如 4,0）；留空表示自动推断：",
                initialvalue=current, parent=win)
            if value is None:
                return
            value = value.strip()
            if value:
                try:
                    parts = value.replace("，", ",").split(",")
                    bs, pc = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    messagebox.showerror("格式不对", "请输入 bs,pc，例如 4,0。",
                                         parent=win)
                    return
                add_voicebank_root(root.path, bs=bs, pc=pc)
            else:
                add_voicebank_root(root.path)
            refresh()
            self._refresh_voicebanks()
            self._log(f"已更新点位覆盖：{root.path}")

        def export() -> None:
            path = filedialog.asksaveasfilename(
                parent=win, title="导出扫描点位", defaultextension=".json",
                initialfile="voicebank_roots.json",
                filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
            if not path:
                return
            export_voicebank_roots(path)
            self._log(f"已导出声库点位：{path}")

        def import_() -> None:
            path = filedialog.askopenfilename(
                parent=win, title="导入扫描点位",
                filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
            if not path:
                return
            try:
                import_voicebank_roots(path)
            except ValueError as exc:
                messagebox.showerror("导入失败", str(exc), parent=win)
                return
            refresh()
            self._refresh_voicebanks()
            self._log(f"已导入声库点位：{path}")

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=14, pady=(0, 12))
        for text, command in (("移除选中", remove), ("编辑 bs/pc", edit),
                              ("导入…", import_), ("导出…", export)):
            self._button(bar, text, command, "ghost", 8).pack(side="left", padx=(0, 8))
        listbox.bind("<Double-Button-1>", lambda e: edit())
        refresh()

    def _on_voicebank_change(self) -> None:
        vb = self._current_voicebank()
        self._update_bank_badge()
        if vb is None:
            return
        self._want_bank_id = vb.id
        self._log(f"已选择声库：{vb.label}  (bs={vb.bs}, pc={vb.pc})")

    def _current_voicebank(self) -> Voicebank | None:
        if not self.voicebanks:
            return None
        idx = self.vb_combo.current()
        if idx < 0 or idx >= len(self.voicebanks):
            idx = 0
        return self.voicebanks[idx]

    def generate(self, open_after: bool = False, silent: bool = False,
                 fmt: str | None = None) -> None:
        if getattr(self, "_busy", False):
            self._log("上一次生成还没结束，请稍候。")
            return
        if not self._validate():
            return
        fmt = "vsqx" if open_after else (fmt or self.export_format)
        if fmt not in FORMATS:
            fmt = "vsqx"
        meta = FORMATS[fmt]
        mode = self._mode()
        out_dir = default_output_dir()
        prefix = meta["prefix"]
        if fmt == "vsqx" and mode == "pinyin":
            prefix = "VocaloidTTS_pinyin"
        default = out_dir / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}{meta['extension']}"
        path = filedialog.asksaveasfilename(
            title=f"保存 {meta['short']} 工程",
            initialdir=str(out_dir),
            initialfile=default.name,
            defaultextension=meta["extension"],
            filetypes=[meta["filetype"], ("所有文件", "*.*")],
        )
        if not path:
            return
        bank = self._current_voicebank()
        if fmt == "vsqx" and bank is None:
            messagebox.showerror("没有歌姬", "请先添加声库。")
            return
        # 用 end-1c 而不是 strip()：首部空格被删会让纠音偏移整体错位
        text = self.text.get("1.0", "end-1c")
        edits = self._active_edits(text) if mode == "chinese" else {}
        dictionary = dict(self.dictionary) if mode == "chinese" else {}
        options = self._voice_options()
        bpm = self._bpm()
        numerator, denominator = self._meter()
        stamp = f"{datetime.now():%m-%d %H:%M}"
        title = f"VocaloidTTS Pinyin {stamp}" if mode == "pinyin" else f"VocaloidTTS {stamp}"
        self.export_format = fmt
        self._busy = True
        self._cancel = False
        self.config(cursor="watch")
        self.status.set(f"正在生成 {meta['short']}…")
        self._show_progress()
        self._log(f"开始生成 {meta['short']}：{Path(path).name}")

        # The callback hops back to the main thread; Reporter throttles it to
        # about 20 updates a second, so the queue never piles up.
        reporter = Reporter(
            on_progress=lambda stage, frac: self._post(self._set_progress, frac),
            should_cancel=lambda: self._cancel)

        def worker() -> None:
            try:
                song = compose(text, options, bpm=bpm, numerator=numerator,
                               denominator=denominator, input_mode=mode,
                               reporter=reporter.child(0.0, 0.88),
                               edits=edits, dictionary=dictionary)
                if not song.notes:
                    raise ValueError("没有解析出可演唱的音节")
                reporter.stage("write", 0.90)
                job_path = None
                written = path
                if fmt == "vsqx":
                    written = write_vsqx(song, path, bank, title=title)
                    try:
                        job_path = write_job(song, default_job_path(), title=title)
                    except Exception as exc:
                        self._post(self._log,
                                   f"插件数据写入失败（工程已生成）：{exc}")
                elif fmt == "svip3":
                    written = write_svip3(song, path)
                elif fmt == "ustx":
                    written = write_ustx(song, path)
                else:
                    written = write_svip(song, path)
                reporter.stage("write", 1.0)
                payload = {"song": song, "path": written, "fmt": fmt,
                           "meta": meta, "open_after": open_after,
                           "silent": silent, "job_path": job_path}
                self._post(self._finish_generate, payload)
            except Cancelled:
                self._post(self._finish_generate, None)
            except Exception as exc:
                # 在异常还活着的时候取堆栈：等到主线程的 after 回调里再调
                # traceback.format_exc() 只会拿到 "NoneType: None"。
                detail = traceback.format_exc()
                self._post(self._fail_generate, exc, detail)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_generate(self, payload: dict | None) -> None:
        self._busy = False
        self.config(cursor="")
        self._hide_progress()
        if payload is None:
            self.status.set("已取消")
            self._log("生成已取消。")
            return
        song = payload["song"]
        path = payload["path"]
        fmt = payload["fmt"]
        meta = payload["meta"]
        job_path = payload["job_path"]
        self.song = song
        self.last_path = path
        self.last_job = job_path
        self.path_label.configure(text=Path(path).name, fg=ACCENT)
        self._update_stats()
        try:
            self.stat_labels["size"].configure(
                text=f"{Path(path).stat().st_size/1024:.0f} KB")
        except Exception:
            pass
        try:
            self.info_hint.configure(
                text=f"已生成 {meta['short']}\n\n{Path(path).name}\n\n"
                     f"{len(song.notes)} 音节 · {song.duration_s:.2f}s\n"
                     f"{song.bpm:.0f} BPM · {song.numerator}/{song.denominator}",
                fg=ACCENT)
        except Exception:
            pass
        self.status.set(f"已生成 {meta['short']}")
        self._log(f"已生成 {meta['short']}：{path}")
        self._remember_recent(path)
        if fmt == "vsqx" and job_path:
            self._log(f"插件数据已刷新：{job_path}")
        elif fmt == "svip3":
            self._log("X Studio 歌手：洛天依（临时借用陈水若 ID，可在 X Studio 里改选歌手）")
        elif fmt == "ustx":
            self._log("OpenUTAU 歌手为占位符；打开工程后请选择实际声库。")
        if not payload["silent"]:
            if fmt == "vsqx":
                detail = ("V4 或 V5 中按 Ctrl+O 打开即可试听。\n"
                          "PIT / DYN / BRI 等参数已写入。")
            elif fmt == "svip3":
                detail = ("在 X Studio 3 中打开即可试听。\n"
                          "歌手 ID 临时借用内置女声，轨道名保持“洛天依”。")
            elif fmt == "ustx":
                detail = ("在 OpenUTAU 中打开，选择实际声库后即可试听。\n"
                          "歌手字段是占位符，不会自动绑定声库。")
            else:
                detail = "OpenSVIP JSON 工程，可交给 OpenSVIP 转换器继续处理。"
            messagebox.showinfo(f"生成 {meta['short']} 成功",
                                f"已生成 {meta['short']} 工程：\n{path}\n\n{detail}")
        if payload["open_after"]:
            self._open_in_editor(path)

    def _fail_generate(self, exc: Exception, detail: str = "") -> None:
        self._busy = False
        self.config(cursor="")
        self._hide_progress()
        self.status.set("生成失败")
        # 拼音写错这类是用户输入问题，只显示消息；其它异常把 worker 线程里
        # 抓到的堆栈一并给出来，否则用户只看到一句「PermissionError」。
        if isinstance(exc, ValueError):
            messagebox.showerror("生成失败", str(exc))
        else:
            messagebox.showerror("生成失败", detail or str(exc))
        self._log(f"生成失败：{exc}")
        if detail and not isinstance(exc, ValueError):
            self._log(detail)

    def generate_and_open(self) -> None:
        target = self._editor_target()
        need = v5_available() if target == "v5" else v4_available()
        if not need:
            name = "VOCALOID5.exe" if target == "v5" else "VOCALOID4.exe"
            if messagebox.askyesno(
                    f"未找到 {name}",
                    f"当前没有可用的 {name} 路径。\n\n"
                    "生成 VSQX 不需要编辑器，但“载入”需要。\n"
                    "现在设置路径吗？"):
                ok = self.choose_v5_path() if target == "v5" else self.choose_v4_path()
                if not ok:
                    return
            else:
                return
        self.generate(open_after=True, silent=True, fmt="vsqx")

    def _open_in_editor(self, path: str) -> None:
        from .v4bridge import open_vsqx
        target = self._editor_target()
        label = "VOCALOID5" if target == "v5" else "VOCALOID4"
        self._log(f"正在连接 {label}…")
        self.status.set(f"正在连接 {label}…")

        def worker():
            ok, msg = open_vsqx(path, target=target)
            self._post(self._after_open, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    _open_in_v4 = _open_in_editor

    def _after_open(self, ok: bool, msg: str) -> None:
        if ok:
            self._log(f"已载入编辑器（{msg}），按空格试听；File > Export 可导出 WAV。")
            self.status.set("已载入 VOCALOID4/5")
            return
        self._log(f"载入失败：{msg}")
        self.status.set("载入失败")
        path = self.last_path
        if not path:
            messagebox.showwarning("载入失败", msg)
            return
        folder = Path(path).parent
        if messagebox.askyesno(
                "载入失败",
                f"{msg}\n\n文件位置：\n{folder}\n\n现在打开这个文件夹吗？"):
            try:
                os.startfile(folder)
            except Exception as exc:
                self._log(f"打开文件夹失败：{exc}")

    def install_plugin(self) -> None:
        if not v4_available():
            if v5_available():
                messagebox.showinfo(
                    "V5 不需要 Job Plugin",
                    "检测到 VOCALOID5。\n\n"
                    "V4 的 Job Plugin 不适用于 V5；\n"
                    "V5 可以直接打开本工具生成的 .vsqx（文件 → 打开）。")
                self._log("V5 不使用 V4 Job Plugin；直接打开 VSQX 即可。")
                return
            if messagebox.askyesno(
                    "未找到 VOCALOID4",
                    "安装插件需要 VOCALOID4 的 JobPlugins 目录。\n\n"
                    "现在设置 VOCALOID4.exe 的路径吗？"):
                if not self.choose_v4_path():
                    return
            else:
                return
        src = resource_path("jobplugin/VocaloidTTS.lua")
        if not src.exists():
            messagebox.showerror("插件缺失", f"未找到插件文件：\n{src}")
            return
        dest_dir = Path(get_jobplugin_dir())
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / "VocaloidTTS.lua"
            dest.write_bytes(src.read_bytes())
        except Exception as exc:
            messagebox.showerror("安装失败", f"无法写入插件目录：\n{exc}")
            return
        self._log(f"插件已复制到：{dest}")
        messagebox.showinfo(
            "插件已复制",
            "VocaloidTTS 任务插件已复制到 V4 的 JobPlugins 文件夹。\n\n"
            "首次使用请在 V4 中执行：\n"
            "任务(J) → 管理任务插件(M) → 添加 → 选择：\n"
            f"{dest}\n\n"
            "之后即可在 任务(J) → 任务插件 中运行。",
        )

    def _remember_recent(self, path: str) -> None:
        try:
            resolved = str(Path(path).resolve())
        except Exception:
            resolved = str(path)
        self.recent = [p for p in self.recent if p != resolved]
        self.recent.insert(0, resolved)
        del self.recent[10:]

    def _open_recent(self, path: str) -> None:
        if not Path(path).is_file():
            messagebox.showwarning("文件不存在", f"{path}\n\n可能已被移动或删除。")
            self.recent = [p for p in self.recent if p != path]
            return
        try:
            os.startfile(path)
            self._log(f"已打开最近工程：{path}")
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def open_output_folder(self) -> None:
        path = Path(self.last_path).parent if self.last_path else default_output_dir()
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    # ---------------------------------------------------------------- project
    def _collect_project(self) -> Project:
        numerator, denominator = self._meter()
        return Project(
            text=self.text.get("1.0", "end-1c"),
            mode=self._mode(),
            bpm=self._bpm(),
            numerator=numerator,
            denominator=denominator,
            options=self._voice_options(),
            edits=self.edits,
        )

    def _apply_project(self, project: Project) -> None:
        self._loading = True
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", project.text)
            self.text.edit_modified(False)
        finally:
            self._loading = False
        self.char_count.configure(text=f"{len(project.text.strip())} 字")
        self.mode_var.set("拼音输入" if project.mode == "pinyin" else "中文文本")
        self.bpm_var.set(self._fmt_num(project.bpm))
        self.num_var.set(str(project.numerator))
        self.den_var.set(str(project.denominator))
        self._apply_voice_options(project.options)
        self.edits = project.edits
        self._on_option_change()

    def _apply_voice_options(self, options: VoiceOptions) -> None:
        if options.style in STYLE_LABELS:
            self.style_var.set(STYLE_LABELS[options.style])
        values = {
            "pitch": options.pitch,
            "tone2": options.tone2_pitch,
            "tone3": options.tone3_pitch,
            "tone4": options.tone4_pitch,
            "tone5": options.tone5_pitch,
            "rate": options.rate,
            "tone": options.tone_strength,
            "energy": options.energy,
            "pause": options.pause_scale,
            "breath": options.breath,
            "vibrato": options.vibrato,
            "gender": options.gender,
        }
        for key, value in values.items():
            if key in self.sliders:
                try:
                    self.sliders[key][0].set(value)
                except Exception:
                    pass
        self.seed_var.set(str(options.seed))

    def save_project_dialog(self) -> None:
        project = self._collect_project()
        if not project.text.strip():
            messagebox.showwarning("没有内容", "先写点文字再保存项目。")
            return
        path = filedialog.asksaveasfilename(
            title="保存项目",
            defaultextension=SUFFIX,
            initialfile=f"VocaloidTTS_{datetime.now():%Y%m%d_%H%M%S}{SUFFIX}",
            filetypes=[("VocaloidTTS 项目", f"*{SUFFIX}"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            save_project(Path(path), project)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))
            return
        self.project_path = path
        self._log(f"项目已保存：{path}")

    def open_project_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="打开项目",
            filetypes=[("VocaloidTTS 项目", f"*{SUFFIX}"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            project = load_project(Path(path))
        except ValueError as exc:
            messagebox.showerror("打开失败", str(exc))
            return
        self._apply_project(project)
        self.project_path = path
        self._log(f"已打开项目：{path}（{len(project.text)} 字，"
                  f"{len(project.edits.chars)} 处人工设置）")

    def _autosave_path(self) -> Path:
        return appdata_dir() / "autosave.vttsproj"

    def _schedule_autosave(self) -> None:
        if getattr(self, "_loading", False):
            return
        job = getattr(self, "_autosave_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._autosave_job = self.after(2500, self._autosave_now)

    def _autosave_now(self) -> None:
        self._autosave_job = None
        try:
            save_project(self._autosave_path(), self._collect_project())
        except Exception as exc:
            self._log(f"自动保存失败：{exc}")

    def _restore_autosave(self) -> None:
        path = self._autosave_path()
        if not path.exists():
            return
        try:
            project = load_project(path)
        except ValueError as exc:
            self._log(f"自动恢复失败：{exc}")
            return
        if not project.text.strip():
            return
        current = self.text.get("1.0", "end-1c")
        if project.text == current:
            return
        self._apply_project(project)
        self._log(f"已恢复上次编辑的内容（{len(project.text)} 字，"
                  f"{len(project.edits.chars)} 处人工设置）")

    # --------------------------------------------------------------- settings
    def _settings_path(self) -> Path:
        base = appdata_dir()
        base.mkdir(parents=True, exist_ok=True)
        return base / "settings.json"

    def _load_settings(self) -> dict:
        try:
            with open(self._settings_path(), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self) -> None:
        data = {
            "schema": 10,
            "mode": self.mode_var.get(),
            "style": self.style_var.get(),
            "font": FONT,
            "export_format": self.export_format,
            "bpm": self._bpm(),
            "numerator": self._meter()[0],
            "denominator": self._meter()[1],
            "editor_target": self.target_var.get(),
            "pitch": self.sliders["pitch"][0].get(),
            "tone2": self.sliders["tone2"][0].get(),
            "tone3": self.sliders["tone3"][0].get(),
            "tone4": self.sliders["tone4"][0].get(),
            "tone5": self.sliders["tone5"][0].get(),
            "rate": self.sliders["rate"][0].get(),
            "tone": self.sliders["tone"][0].get(),
            "energy": self.sliders["energy"][0].get(),
            "pause": self.sliders["pause"][0].get(),
            "breath": self.sliders["breath"][0].get(),
            "vibrato": self.sliders["vibrato"][0].get(),
            "gender": self.sliders["gender"][0].get(),
            "seed": self.seed_var.get(),
            "voicebank_id": (bank.id if (bank := self._current_voicebank()) else ""),
            "recent": self.recent[:10],
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _safe_apply(self, label: str, func) -> None:
        try:
            func()
        except Exception as exc:
            self._log(f"设置项 {label} 恢复失败：{exc}")

    def _apply_settings(self) -> None:
        s = self.settings
        if not s:
            return
        recent = s.get("recent")
        if isinstance(recent, list):
            self.recent = [str(p) for p in recent if isinstance(p, str)][:10]
        try:
            schema = int(s.get("schema", 1))
        except (TypeError, ValueError):
            schema = 1
        self._safe_apply("声库", lambda: self._apply_voicebank_setting(s))
        # v1 saved a much flatter tone; start v2 users on the new defaults
        if schema < 2:
            return
        self._safe_apply("风格与速度", lambda: self._apply_transport_setting(s))
        self._safe_apply("滑条", lambda: self._apply_slider_setting(s, schema))
        self._safe_apply("种子", lambda: self._apply_seed_setting(s))
        self._safe_apply("输入模式", lambda: self._apply_mode_setting(s))
        self._safe_apply("界面刷新", self._on_option_change)

    def _apply_voicebank_setting(self, s: dict) -> None:
        vb_id = s.get("voicebank_id")
        if vb_id:
            self._want_bank_id = str(vb_id)
        elif s.get("voicebank") is not None:
            try:
                self._want_bank_index = int(s["voicebank"])
            except (TypeError, ValueError):
                self._want_bank_index = None
        # 扫描是异步的：列表还没回来时这里什么也不做，扫描结束后
        # _scan_finished 会再调一次。
        self._restore_voicebank_selection()

    def _apply_transport_setting(self, s: dict) -> None:
        if s.get("style") in STYLE_LABELS.values():
            self.style_var.set(s["style"])
        if "bpm" in s:
            self.bpm_var.set(self._fmt_num(s["bpm"]))
        if "numerator" in s:
            self.num_var.set(str(s["numerator"]))
        if "denominator" in s:
            self.den_var.set(str(s["denominator"]))
        if s.get("export_format") in FORMATS:
            self.export_format = s["export_format"]
        if s.get("editor_target") in ("V4", "V5"):
            self.target_var.set(s["editor_target"])

    def _apply_slider_setting(self, s: dict, schema: int) -> None:
        for key in ("pitch", "tone2", "tone3", "tone4", "tone5", "rate",
                    "tone", "energy", "pause", "breath", "vibrato", "gender"):
            if key == "pitch" and schema < 4:
                # v1.5 redefines pitch as the first-tone anchor (G3 default)
                continue
            if key in s and key in self.sliders:
                value = float(s[key])
                # v1.8 switches to V4's C3=60 octave labels and raises the
                # old low register by one octave.
                if schema < 6 and key in ("pitch", "tone2", "tone3", "tone4",
                                          "tone5") and value < 64:
                    value += 12
                self.sliders[key][0].set(value)

    def _apply_seed_setting(self, s: dict) -> None:
        if "seed" in s:
            self.seed_var.set(str(s["seed"]))

    def _apply_mode_setting(self, s: dict) -> None:
        if s.get("mode") not in ("中文文本", "拼音输入"):
            return
        self.mode_var.set(s["mode"])
        if self._mode() != "pinyin":
            return
        self.hint_label.configure(
            text="空格分隔拼音，数字标声调：ni3 hao3 shi4 jie4；可用 ni3|n_i 覆盖音素。")
        # text content is not persisted, so start with a valid pinyin sample
        # instead of the Chinese default
        self._loading = True
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", PINYIN_PRESETS["自然朗读"][1])
            self.text.edit_modified(False)
        finally:
            self._loading = False
        self.char_count.configure(text=f"{len(PINYIN_PRESETS['自然朗读'][1])} 字")

    def _on_close(self) -> None:
        if self._quitting:
            self._quit_app()
            return
        try:
            self._save_settings()
        except Exception:
            pass
        if not self._ensure_tray():
            if messagebox.askyesno(
                    "无法创建托盘图标",
                    "系统托盘不可用，无法驻留后台。\n\n"
                    "现在直接退出 VocaloidTTS 吗？"):
                self._quit_app()
            return
        try:
            if getattr(self, "_tray_holder", None) is None:
                self._tray_holder = tk.Toplevel(self)
                self._tray_holder.withdraw()
        except Exception:
            self._tray_holder = None
        self.withdraw()
        self._log("已最小化到系统托盘；右键托盘图标可“退出 VocaloidTTS”。")


ToneTalkApp = VocaloidTTSApp


def main() -> None:
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass
    if "--selftest" in sys.argv:
        tmp = Path(os.getenv("TEMP") or ".")
        try:
            (tmp / "VocaloidTTS_boot.txt").write_text(repr(sys.argv), encoding="utf-8")
        except Exception:
            pass
        try:
            out = tmp / "VocaloidTTS_selftest.vsqx"
            song = compose("你好，世界。今天天气真不错！",
                           VoiceOptions(style="read", seed=42))
            banks = detect_voicebanks()
            bank = banks[0] if banks else Voicebank(
                "BK8H76TAEHXWSKDB", "LuoTianyi", "洛天依 · 中文 Meng", 4, 0)
            write_vsqx(song, out, bank, title="VocaloidTTS Selftest")
            write_job(song, default_job_path(), title="VocaloidTTS Selftest")
            (tmp / "VocaloidTTS_selftest.ok").write_text(
                f"ok {len(song.notes)} notes {out}\n", encoding="utf-8")
        except Exception:
            (tmp / "VocaloidTTS_selftest.err").write_text(
                traceback.format_exc(), encoding="utf-8")
        return
    app = VocaloidTTSApp()
    app.mainloop()
