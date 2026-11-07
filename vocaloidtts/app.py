"""VocaloidTTS - Tkinter desktop front-end."""
from __future__ import annotations

import json
import math
import os
import subprocess
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
from .paths import appdata_dir
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
        self._set_window_icon()
        self._close_hook = None
        self.bind("<<VocaloidTTSClose>>", lambda e: self._on_close())
        try:
            self._close_hook = CloseHook(self, self._on_close,
                                          on_drop=self._on_drop_files)
        except Exception:
            self._close_hook = None

        self.voicebanks: list[Voicebank] = detect_voicebanks()
        self.vb_index = 0
        self.song: Song | None = None
        self.last_path: str | None = None
        self.last_job: str | None = None
        self.export_format = "vsqx"
        self._loading = False
        self.settings = self._load_settings()

        self._init_style()
        self._build()
        self._apply_settings()
        self._log("VocaloidTTS 已就绪。输入文字后点“生成工程”，选择要导出的格式。")
        self._log("声库扫描：" + "、".join(v.display for v in self.voicebanks))
        custom_roots = get_voicebank_roots()
        if custom_roots:
            self._log("自定义声库目录：" + "；".join(r.path for r in custom_roots))
        if v4_available():
            self._log(f"VOCALOID4：{get_v4_exe()}")
        if v5_available():
            self._log(f"VOCALOID5：{get_v5_exe()}")
        if not v4_available() and not v5_available():
            self._log("未找到 VOCALOID4/5；生成 VSQX 仍可用，但载入编辑器需要路径。")
            self.after(300, self._check_editor_startup)

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
                on_show=lambda: self.after(0, self._show_from_tray),
                on_quit=lambda: self.after(0, self._quit_app),
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
        self.bank_pill = tk.Label(
            pill, text=self._bank_badge_text(self.voicebanks[0]),
            bg="#142321", fg="#79a9a2", font=(FONT, 8), padx=5)
        self.bank_pill.pack(side="left")

        tk.Frame(self, bg=LINE, height=1).pack(fill="x", padx=22, pady=(1, 8))

        self.status = tk.StringVar(value="就绪")
        bar = tk.Frame(self, bg="#0e1117", height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status, bg="#0e1117", fg=MUTED,
                 font=(FONT, 8), anchor="w").pack(side="left", padx=22)
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
        try:
            x = self.btn_generate.winfo_rootx()
            y = self.btn_generate.winfo_rooty() + self.btn_generate.winfo_height() + 2
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _build_preview(self, parent) -> None:
        # Real-time pitch/VSQX rendering was removed on purpose: composing on
        # every keystroke made large texts very laggy.  This card only shows
        # the summary of the last explicit "生成 VSQX" action.
        outer, inner = self._card(parent, pad=12)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.rowconfigure(1, weight=1)
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(0, 4))
        tk.Label(head, text="生成信息", bg=CARD, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="仅在点击“生成工程”后更新", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="left", padx=10)

        body = tk.Frame(inner, bg="#0f1218", highlightbackground="#222936",
                        highlightthickness=1)
        body.pack(fill="both", expand=True, pady=(4, 8))
        self.info_hint = tk.Label(
            body,
            text="实时语调预览已关闭\n\n"
                 "输入文字或调整参数时不会生成工程 / 音高曲线\n"
                 "点击“生成工程”后，这里显示工程统计",
            bg="#0f1218", fg="#66748b", justify="center",
            font=(FONT, 10), wraplength=280)
        self.info_hint.pack(expand=True)

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
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message)

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
        for key, (var, lab, fmt) in self.sliders.items():
            try:
                lab.configure(text=fmt(var.get()))
            except Exception:
                pass
        # Deliberately no compose/render here: sliders and typing must stay
        # responsive.  A song is built only by "生成 VSQX".

    def _on_text_modified(self, event=None) -> None:
        if self._loading:
            return
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        content = self.text.get("1.0", "end").strip()
        self.char_count.configure(text=f"{len(content)} 字")

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
        top = max(song.notes, key=lambda n: n.midi)
        self.stat_labels["peak"].configure(text=note_name(top.midi))
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
        old_id = select_id
        if old_id is None and self.voicebanks:
            try:
                old_id = self._current_voicebank().id
            except Exception:
                old_id = None
        banks = detect_voicebanks(use_cache=not force)
        self.voicebanks = banks
        self.vb_combo["values"] = [v.label for v in banks]
        idx = 0
        if old_id:
            for i, vb in enumerate(banks):
                if vb.id == old_id:
                    idx = i
                    break
        if banks:
            self.vb_combo.current(idx)
        self._update_bank_badge()
        custom = get_voicebank_roots()
        extra = f"，自定义目录 {len(custom)} 个" if custom else ""
        self._log(f"声库扫描：{len(banks)} 个{extra}")

    def rescan_voicebanks(self) -> None:
        self._refresh_voicebanks(force=True)
        self.vb_note.configure(text="已重新扫描；找不到时点“＋ 添加文件夹”指定声库目录")

    def add_voicebank_folder(self) -> None:
        path = filedialog.askdirectory(
            title="选择歌姬声库文件夹（VOCALOID VoiceDB / 声库根目录）",
            mustexist=True)
        if not path:
            return
        try:
            found = scan_voicebank_folder(path)
        except Exception as exc:
            messagebox.showerror("扫描失败", str(exc))
            return
        if not found:
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
        self._log(f"已选择声库：{vb.label}  (bs={vb.bs}, pc={vb.pc})")

    def _current_voicebank(self) -> Voicebank | None:
        if not self.voicebanks:
            return None
        idx = self.vb_combo.current()
        if idx < 0 or idx >= len(self.voicebanks):
            idx = 0
        return self.voicebanks[idx]

    def generate(self, open_after: bool = False, silent: bool = False,
                 fmt: str | None = None) -> str | None:
        if not self._validate():
            return None
        fmt = "vsqx" if open_after else (fmt or self.export_format)
        if fmt not in FORMATS:
            fmt = "vsqx"
        meta = FORMATS[fmt]
        try:
            self.config(cursor="watch")
            self.update_idletasks()
            mode = self._mode()
            song = compose(self.text.get("1.0", "end").strip(),
                           self._voice_options(), bpm=self._bpm(),
                           numerator=self._meter()[0],
                           denominator=self._meter()[1], input_mode=mode)
            if not song.notes:
                raise ValueError("没有解析出可演唱的音节")
            self.song = song
            self.export_format = fmt
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
                return None
            stamp = f"{datetime.now():%m-%d %H:%M}"
            title = f"VocaloidTTS Pinyin {stamp}" if mode == "pinyin" else f"VocaloidTTS {stamp}"
            if fmt == "vsqx":
                bank = self._current_voicebank()
                if bank is None:
                    raise ValueError("没有可用的声库")
                path = write_vsqx(song, path, bank, title=title)
                try:
                    self.last_job = write_job(song, default_job_path(), title=title)
                except Exception as exc:
                    self.last_job = None
                    self._log(f"插件数据写入失败（工程已生成）：{exc}")
            elif fmt == "svip3":
                path = write_svip3(song, path)
                self.last_job = None
            elif fmt == "ustx":
                path = write_ustx(song, path)
                self.last_job = None
            else:
                path = write_svip(song, path)
                self.last_job = None
            self.last_path = path
            self.path_label.configure(text=Path(path).name, fg=ACCENT)
            self._update_stats()
            self.stat_labels["size"].configure(text=f"{Path(path).stat().st_size/1024:.0f} KB")
            try:
                self.info_hint.configure(
                    text=f"已生成 {meta['short']}\n\n{Path(path).name}\n\n"
                         f"{len(song.notes)} 音节 · {song.duration_s:.2f}s\n"
                         f"{song.bpm:.0f} BPM · {song.numerator}/{song.denominator}",
                    fg=ACCENT)
            except Exception:
                pass
            self._log(f"已生成 {meta['short']}：{path}")
            if fmt == "vsqx":
                self._log(f"插件数据已刷新：{self.last_job}")
            elif fmt == "svip3":
                self._log("X Studio 歌手：洛天依（临时借用陈水若 ID，可在 X Studio 里改选歌手）")
            elif fmt == "ustx":
                self._log("OpenUTAU 歌手为占位符；打开工程后请选择实际声库。")
            if not silent:
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
            if open_after:
                self._open_in_v4(path)
            return path
        except Exception as exc:
            messagebox.showerror("生成失败", f"{exc}\n\n{traceback.format_exc()}")
            self._log(f"生成失败：{exc}")
            return None
        finally:
            self.config(cursor="")

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
        path = self.generate(open_after=False, silent=True, fmt="vsqx")
        if path:
            self._open_in_editor(path)

    def _open_in_editor(self, path: str) -> None:
        from .v4bridge import open_vsqx
        target = self._editor_target()
        label = "VOCALOID5" if target == "v5" else "VOCALOID4"
        self._log(f"正在连接 {label}…")
        self.status.set(f"正在连接 {label}…")

        def worker():
            ok, msg = open_vsqx(path, target=target)
            self.after(0, lambda: self._after_open(ok, msg))

        threading.Thread(target=worker, daemon=True).start()

    _open_in_v4 = _open_in_editor

    def _after_open(self, ok: bool, msg: str) -> None:
        if ok:
            self._log(f"已载入编辑器（{msg}），按空格试听；File > Export 可导出 WAV。")
            self.status.set("已载入 VOCALOID4/5")
        else:
            self._log(msg)
            messagebox.showwarning("载入 V4/V5",
                                   f"{msg}\n\n请手动在 V4/V5 中按 Ctrl+O 打开：\n{self.last_path}")

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

    def open_output_folder(self) -> None:
        path = Path(self.last_path).parent if self.last_path else default_output_dir()
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

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
            "voicebank": self.vb_combo.current(),
            "voicebank_id": (bank.id if (bank := self._current_voicebank()) else ""),
        }
        try:
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_settings(self) -> None:
        s = self.settings
        if not s:
            return
        try:
            vb_id = s.get("voicebank_id")
            if vb_id:
                for i, vb in enumerate(self.voicebanks):
                    if vb.id == vb_id:
                        self.vb_combo.current(i)
                        break
            elif s.get("voicebank") is not None and 0 <= int(s["voicebank"]) < len(self.voicebanks):
                self.vb_combo.current(int(s["voicebank"]))
            self._update_bank_badge()
            # v1 saved a much flatter tone; start v2 users on the new defaults
            schema = int(s.get("schema", 1))
            if schema < 2:
                return
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
            for key in ("pitch", "tone2", "tone3", "tone4", "tone5", "rate",
                        "tone", "energy", "pause", "breath", "vibrato", "gender"):
                if key == "pitch" and schema < 4:
                    # v1.5 redefines pitch as the first-tone anchor (G3 default)
                    continue
                if key in s and key in self.sliders:
                    value = float(s[key])
                    # v1.8 switches to V4's C3=60 octave labels and raises
                    # the old low register by one octave.
                    if schema < 6 and key in ("pitch", "tone2", "tone3", "tone4", "tone5") and value < 64:
                        value += 12
                    self.sliders[key][0].set(value)
            if "seed" in s:
                self.seed_var.set(str(s["seed"]))
            if s.get("mode") in ("中文文本", "拼音输入"):
                self.mode_var.set(s["mode"])
                if self._mode() == "pinyin":
                    self.hint_label.configure(
                        text="空格分隔拼音，数字标声调：ni3 hao3 shi4 jie4；可用 ni3|n_i 覆盖音素。")
                    # text content is not persisted, so start with a valid
                    # pinyin sample instead of the Chinese default
                    self._loading = True
                    self.text.delete("1.0", "end")
                    self.text.insert("1.0", PINYIN_PRESETS["自然朗读"][1])
                    self.text.edit_modified(False)
                    self._loading = False
                    self.char_count.configure(text=f"{len(PINYIN_PRESETS['自然朗读'][1])} 字")
            self._on_option_change()
        except Exception:
            pass

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
