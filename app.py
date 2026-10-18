#!/usr/bin/env python3
"""旁白稿批次轉 MP3 + SRT（ElevenLabs）桌面應用程式。

轉換邏輯與 txt2mp3srt.py 共用，這裡只負責視窗介面。
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from types import SimpleNamespace

import txt2mp3srt as core

APP_NAME = "旁白稿轉 MP3 + SRT"
CONFIG = Path.home() / ".txt2mp3srt.json"
MODELS = [
    ("eleven_v4_turbo", "Eleven v4 Turbo"),
    ("eleven_v4", "Eleven v4（最擬真）"),
    ("eleven_v3", "Eleven v3"),
    ("eleven_multilingual_v2", "Multilingual v2"),
    ("eleven_flash_v2_5", "Flash v2.5（快速、較便宜）"),
]
FORMATS = [
    ("mp3_44100_128", "MP3 44.1kHz 128kbps（建議）"),
    ("mp3_44100_192", "MP3 44.1kHz 192kbps（需較高方案）"),
    ("mp3_44100_64", "MP3 44.1kHz 64kbps（較小檔）"),
]
LABEL = {"wait": "等待中", "run": "轉換中…", "done": "✔ 完成", "skip": "略過（已存在）", "err": "✘ 失敗"}


def load_config():
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def open_path(path):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App:
    def __init__(self, root):
        self.root = root
        self.files = []        # Path
        self.status = {}       # Path -> 狀態
        self.q = queue.Queue()  # 背景執行緒 → 介面
        self.worker = None
        self.stop_flag = False
        cfg = load_config()

        root.title(APP_NAME)
        root.minsize(900, 560)
        main = ttk.Frame(root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        # 左欄：設定與聲音；右欄：檔案與轉換
        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        # ① ElevenLabs 設定
        box = ttk.LabelFrame(left, text="① ElevenLabs 設定", padding=10)
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        self.key = tk.StringVar(value=cfg.get("api_key", ""))
        self.remember = tk.BooleanVar(value=bool(cfg.get("api_key")))
        self.voice = tk.StringVar(value=cfg.get("voice") or core.DEFAULT_VOICE)
        self.voice_pick = tk.StringVar(value="填入 API Key 後載入音色清單")
        self.voice_map = {}  # 顯示名稱 -> Voice ID
        self.model = tk.StringVar(value=self._label(MODELS, cfg.get("model", "eleven_v4_turbo")))
        self.fmt = tk.StringVar(value=self._label(FORMATS, cfg.get("format", "mp3_44100_128")))
        ttk.Label(box, text="API Key").grid(row=0, column=0, sticky="w")
        key_entry = ttk.Entry(box, textvariable=self.key, show="•")
        key_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Checkbutton(box, text="記住在這台電腦", variable=self.remember).grid(row=1, column=1, sticky="w", padx=(6, 0))
        ttk.Label(box, text="音色").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.voice_box = ttk.Combobox(box, textvariable=self.voice_pick, state="readonly")
        self.voice_box.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        self.voice_box.bind("<<ComboboxSelected>>", self.on_voice_pick)
        ttk.Label(box, text="Voice ID").grid(row=3, column=0, sticky="w", pady=(6, 0))
        voice_entry = ttk.Entry(box, textvariable=self.voice)
        voice_entry.grid(row=3, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        voice_entry.bind("<FocusOut>", lambda e: self.on_voice_id())
        voice_entry.bind("<Return>", lambda e: self.on_voice_id())
        ttk.Label(box, text="模型").grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(box, textvariable=self.model, values=[l for _, l in MODELS], state="readonly") \
            .grid(row=4, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        ttk.Label(box, text="輸出品質").grid(row=5, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(box, textvariable=self.fmt, values=[l for _, l in FORMATS], state="readonly") \
            .grid(row=5, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
        self.quota = None
        self.quota_text = tk.StringVar(value="填入 API Key 後顯示剩餘額度")
        ttk.Label(box, text="額度").grid(row=6, column=0, sticky="nw", pady=(8, 0))
        ttk.Label(box, textvariable=self.quota_text, wraplength=280).grid(row=6, column=1, sticky="w", padx=(6, 0), pady=(8, 0))
        ttk.Button(box, text="重新整理", command=self.refresh_quota).grid(row=7, column=1, sticky="e", pady=(4, 0))
        key_entry.bind("<FocusOut>", lambda e: self.on_key())
        key_entry.bind("<Return>", lambda e: self.on_key())

        # ② 聲音調整與試聽
        box = ttk.LabelFrame(left, text="② 聲音調整與試聽", padding=10)
        box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(1, weight=1)
        self.vs = {k: tk.DoubleVar(value=v) for k, v in core.DEFAULT_VOICE_SETTINGS.items()}
        self.vs_text = {k: tk.StringVar(value=f"{v:.2f}") for k, v in core.DEFAULT_VOICE_SETTINGS.items()}
        self.vs_modified = False
        for r, (k, label, lo, hi) in enumerate([("speed", "語速", 0.7, 1.2), ("stability", "穩定度", 0, 1),
                                                ("similarity_boost", "相似度", 0, 1), ("style", "風格強度", 0, 1)]):
            ttk.Label(box, text=label).grid(row=r, column=0, sticky="w", pady=2)
            ttk.Scale(box, from_=lo, to=hi, variable=self.vs[k], command=lambda v, k=k: self.on_vs(k)) \
                .grid(row=r, column=1, sticky="ew", padx=6, pady=2)
            ttk.Label(box, textvariable=self.vs_text[k], width=5).grid(row=r, column=2, sticky="e")
        self.vs_note = tk.StringVar(value="使用音色在 ElevenLabs 上的設定")
        vrow = ttk.Frame(box)
        vrow.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(2, 0))
        ttk.Label(vrow, textvariable=self.vs_note, foreground="gray").pack(side="left")
        ttk.Button(vrow, text="重設", command=self.reset_vs).pack(side="right")
        ttk.Label(box, text="試聽文字（選檔後自動帶入開頭一兩句，可自行修改）", foreground="gray") \
            .grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 2))
        self.pv_text = tk.Text(box, height=3, width=36, wrap="char")
        self.pv_text.grid(row=6, column=0, columnspan=3, sticky="ew")
        self.pv_text.bind("<KeyRelease>", lambda e: setattr(self, "pv_auto", not self.pv_text.get("1.0", "end").strip()))
        self.pv_auto = True
        prow = ttk.Frame(box)
        prow.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.pv_btn = ttk.Button(prow, text="🔊 試聽", command=self.preview)
        self.pv_btn.pack(side="left")
        self.pv_note = tk.StringVar(value="只轉這一小段，用系統播放器播放")
        ttk.Label(prow, textvariable=self.pv_note, foreground="gray").pack(side="left", padx=(8, 0))
        saved_vs = cfg.get("voice_settings") or {}
        if saved_vs.get("voice") == self.voice.get():
            self.show_vs(saved_vs)
            self.set_vs_modified(True)

        # ③ 選擇旁白稿
        box = ttk.LabelFrame(right, text="③ 選擇旁白稿", padding=10)
        box.grid(row=0, column=0, sticky="nsew")
        box.columnconfigure(0, weight=1)
        box.rowconfigure(1, weight=1)
        btns = ttk.Frame(box)
        btns.grid(row=0, column=0, sticky="ew")
        self.input_btns = [
            ttk.Button(btns, text="📁 選擇資料夾", command=self.pick_folder),
            ttk.Button(btns, text="📄 選擇多個 txt", command=self.pick_files),
            ttk.Button(btns, text="清空", command=self.clear),
        ]
        for b in self.input_btns:
            b.pack(side="left", padx=(0, 6))

        cols = ("num", "name", "chars", "status")
        self.tree = ttk.Treeview(box, columns=cols, show="headings", height=8)
        for c, t, w, a in [("num", "#", 40, "e"), ("name", "檔名", 240, "w"),
                           ("chars", "字數", 60, "e"), ("status", "狀態", 160, "w")]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor=a, stretch=(c in ("name", "status")))
        self.tree.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.tree.configure(yscrollcommand=sb.set)
        self.total = ttk.Label(box, text="尚未選擇檔案", foreground="gray")
        self.total.grid(row=2, column=0, sticky="w", pady=(4, 0))

        out = ttk.Frame(box)
        out.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        out.columnconfigure(1, weight=1)
        self.out_dir = tk.StringVar(value=cfg.get("out_dir", ""))
        ttk.Label(out, text="輸出資料夾").grid(row=0, column=0, sticky="w")
        ttk.Entry(out, textvariable=self.out_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(out, text="選擇…", command=self.pick_out).grid(row=0, column=2)
        ttk.Button(out, text="開啟", command=self.open_out).grid(row=0, column=3, padx=(6, 0))
        ttk.Label(out, text="空白＝存在 txt 旁邊", foreground="gray").grid(row=1, column=1, sticky="w", padx=6)

        # ④ 字幕與轉換
        box = ttk.LabelFrame(right, text="④ 字幕與轉換", padding=10)
        box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        box.columnconfigure(0, weight=1)
        srt = ttk.Frame(box)
        srt.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.make_srt = tk.BooleanVar(value=cfg.get("make_srt", True))
        self.max_len = tk.IntVar(value=cfg.get("max_len", 18))
        self.keep_punct = tk.BooleanVar(value=cfg.get("keep_punct", False))
        ttk.Checkbutton(srt, text="同時產生 SRT 字幕", variable=self.make_srt).pack(side="left")
        ttk.Label(srt, text="每行最多字數").pack(side="left", padx=(20, 4))
        ttk.Spinbox(srt, from_=6, to=80, textvariable=self.max_len, width=5).pack(side="left")
        ttk.Checkbutton(srt, text="保留原文標點", variable=self.keep_punct).pack(side="left", padx=(20, 0))
        btns = ttk.Frame(box)
        btns.grid(row=1, column=0, sticky="w")
        self.start_btn = ttk.Button(btns, text="開始轉換", command=self.start)
        self.stop_btn = ttk.Button(btns, text="停止", command=self.stop, state="disabled")
        self.srt_btn = ttk.Button(btns, text="只重做字幕（不扣額度）", command=self.redo_srt)
        self.force = tk.BooleanVar(value=False)
        for b in (self.start_btn, self.stop_btn, self.srt_btn):
            b.pack(side="left", padx=(0, 6))
        ttk.Checkbutton(btns, text="已存在的 MP3 也重轉", variable=self.force).pack(side="left", padx=(6, 0))
        self.prog = ttk.Progressbar(box, mode="determinate")
        self.prog.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.log = tk.Text(box, height=4, width=50, wrap="word", state="disabled")
        self.log.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        ttk.Label(main, text="API Key 只會從這台電腦直接送到 ElevenLabs。已存在的 MP3 預設會跳過。",
                  foreground="gray").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # 視窗高度不超過螢幕；空間不夠時由檔案清單（可捲動）讓出高度
        root.update_idletasks()
        if root.winfo_reqheight() > root.winfo_screenheight() - 80:
            root.geometry(f"{root.winfo_reqwidth()}x{root.winfo_screenheight() - 80}")

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.key.get().strip():
            self.on_key()
        self.root.after(100, self.poll)

    # ---------- 設定 ----------
    @staticmethod
    def _label(pairs, value):
        return next((l for v, l in pairs if v == value), pairs[0][1])

    @staticmethod
    def _value(pairs, label):
        return next((v for v, l in pairs if l == label), pairs[0][0])

    def max_len_value(self):
        try:
            return max(6, int(self.max_len.get()))
        except (tk.TclError, ValueError):
            return 18

    def save_config(self):
        cfg = {
            "api_key": self.key.get().strip() if self.remember.get() else "",
            "voice": self.voice.get().strip(),
            "model": self._value(MODELS, self.model.get()),
            "format": self._value(FORMATS, self.fmt.get()),
            "make_srt": self.make_srt.get(),
            "max_len": self.max_len_value(),
            "keep_punct": self.keep_punct.get(),
            "out_dir": self.out_dir.get().strip(),
            "voice_settings": {"voice": self.voice.get().strip(), **self.current_vs()} if self.vs_modified else None,
        }
        try:
            CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            if os.name == "posix":
                os.chmod(CONFIG, 0o600)
        except OSError:
            pass

    def make_args(self):
        return SimpleNamespace(
            voice=self.voice.get().strip(),
            model=self._value(MODELS, self.model.get()),
            format=self._value(FORMATS, self.fmt.get()),
            no_srt=not self.make_srt.get(),
            max_len=self.max_len_value(),
            keep_punct=self.keep_punct.get(),
            voice_settings=self.current_vs() if self.vs_modified else None,
        )

    # ---------- 選檔 ----------
    def pick_folder(self):
        d = filedialog.askdirectory(title="選擇含有 txt 的資料夾")
        if d:
            self.add_files([d])

    def pick_files(self):
        fs = filedialog.askopenfilenames(title="選擇 txt", filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")])
        if fs:
            self.add_files(fs)

    def add_files(self, paths):
        known = {f.resolve() for f in self.files}
        for f in core.collect_files(paths):
            if f.resolve() not in known:
                self.files.append(f)
                self.status[f] = "wait"
        self.refresh()
        if self.pv_auto and self.files:
            self.pv_text.delete("1.0", "end")
            self.pv_text.insert("1.0", core.preview_text(core.read_text(self.files[0])))

    def clear(self):
        self.files, self.status = [], {}
        self.refresh()

    def pick_out(self):
        d = filedialog.askdirectory(title="選擇輸出資料夾")
        if d:
            self.out_dir.set(d)

    def open_out(self):
        d = self.out_dir.get().strip() or (str(self.files[0].parent) if self.files else "")
        if d and Path(d).is_dir():
            open_path(d)

    def out_for(self, f):
        d = Path(self.out_dir.get().strip()) if self.out_dir.get().strip() else f.parent
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ---------- 顯示 ----------
    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        total = 0
        for i, f in enumerate(self.files):
            n = len(core.read_text(f))
            total += n
            st = self.status[f]
            label = LABEL.get(st, f"✘ 失敗（{st}）")
            self.tree.insert("", "end", iid=str(i), values=(i + 1, f.name, n, label))
        self.total.config(text=f"共 {len(self.files)} 個檔案、約 {total:,} 字元（會依字元數扣 ElevenLabs 額度）"
                          if self.files else "尚未選擇檔案")
        self.update_progress()

    def set_status(self, f, st):
        self.status[f] = st
        i = self.files.index(f)
        vals = list(self.tree.item(str(i), "values"))
        vals[3] = LABEL.get(st, f"✘ 失敗（{st}）")
        self.tree.item(str(i), values=vals)
        self.tree.see(str(i))
        self.update_progress()

    def update_progress(self):
        done = sum(1 for s in self.status.values() if s in ("done", "skip"))
        self.prog.config(maximum=max(1, len(self.files)), value=done)

    def write_log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def set_running(self, running):
        st = "disabled" if running else "normal"
        for b in self.input_btns + [self.start_btn, self.srt_btn]:
            b.config(state=st)
        self.stop_btn.config(state="normal" if running else "disabled")

    def poll(self):
        try:
            while True:
                kind, *data = self.q.get_nowait()
                if kind == "log":
                    self.write_log(data[0])
                elif kind == "status":
                    self.set_status(*data)
                elif kind == "end":
                    self.set_running(False)
                    self.write_log(data[0])
                elif kind == "voices":
                    self.show_voices(data[0])
                elif kind == "vs":
                    voice, settings = data
                    if voice == self.voice.get().strip() and not self.vs_modified:
                        self.show_vs(settings)
                elif kind == "preview":
                    path, msg = data
                    self.pv_btn.config(state="normal")
                    self.pv_note.set(msg)
                    if path:
                        open_path(path)
                        self.refresh_quota()
                elif kind == "quota":
                    self.quota, text = data
                    self.quota_text.set(text)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ---------- 剩餘額度 ----------
    def fetch_quota(self, key):
        """在背景執行緒查詢額度，結果送回介面。"""
        try:
            q = core.get_quota(key)
            self.q.put(("quota", q, core.format_quota(q)))
        except Exception as e:
            self.q.put(("quota", None, str(e).split(" ", 1)[-1]))

    def on_key(self):
        self.refresh_quota()
        self.load_voices()
        self.load_vs()

    # ---------- 音色 ----------
    def load_voices(self):
        key = self.key.get().strip()
        if not key:
            return
        self.voice_pick.set("載入音色清單中…")

        def work():
            try:
                self.q.put(("voices", core.list_voices(key)))
            except Exception as e:
                self.q.put(("voices", str(e).split(" ", 1)[-1]))
        threading.Thread(target=work, daemon=True).start()

    def show_voices(self, voices):
        if isinstance(voices, str):
            self.voice_map = {}
            self.voice_box.config(values=[])
            self.voice_pick.set(f"無法載入音色清單（{voices}），請直接輸入 ID")
            return
        self.voice_map = {v["name"] + (f"（{v['category']}）" if v["category"] else ""): v["id"] for v in voices}
        self.voice_box.config(values=list(self.voice_map))
        self.sync_voice_pick()

    def sync_voice_pick(self):
        vid = self.voice.get().strip()
        name = next((n for n, i in self.voice_map.items() if i == vid), None)
        self.voice_pick.set(name or ("— 從帳號選擇音色 —" if self.voice_map else self.voice_pick.get()))

    def on_voice_pick(self, _=None):
        vid = self.voice_map.get(self.voice_pick.get())
        if vid and vid != self.voice.get().strip():
            self.voice.set(vid)
            self.set_vs_modified(False)
            self.load_vs()

    def on_voice_id(self):
        self.sync_voice_pick()
        if self.vs_modified and self.vs_voice != self.voice.get().strip():
            self.set_vs_modified(False)  # 調整值只屬於原本那個音色
        self.load_vs()

    # ---------- 聲音調整 ----------
    def show_vs(self, settings):
        for k in core.VOICE_SETTING_KEYS:
            v = float(settings.get(k, core.DEFAULT_VOICE_SETTINGS[k]))
            self.vs[k].set(v)
            self.vs_text[k].set(f"{v:.2f}")

    def current_vs(self):
        return {k: round(self.vs[k].get() * 20) / 20 for k in core.VOICE_SETTING_KEYS}

    def set_vs_modified(self, modified):
        self.vs_modified = modified
        self.vs_voice = self.voice.get().strip() if modified else None
        self.vs_note.set("已調整：轉換與試聽都會套用" if modified else "使用音色在 ElevenLabs 上的設定")

    def on_vs(self, k):
        v = round(self.vs[k].get() * 20) / 20  # 以 0.05 為單位
        self.vs_text[k].set(f"{v:.2f}")
        self.set_vs_modified(True)

    def load_vs(self):
        """讀取音色在 ElevenLabs 上的設定，顯示在滑桿上（已手動調整時不覆蓋）。"""
        key, voice = self.key.get().strip(), self.voice.get().strip()
        if self.vs_modified:
            return
        self.show_vs(core.DEFAULT_VOICE_SETTINGS)
        if not key or not voice:
            return

        def work():
            try:
                self.q.put(("vs", voice, core.get_voice_settings(key, voice)))
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def reset_vs(self):
        self.set_vs_modified(False)
        self.load_vs()

    # ---------- 試聽 ----------
    def preview(self):
        key, voice = self.key.get().strip(), self.voice.get().strip()
        text = self.pv_text.get("1.0", "end").strip()
        if not key or not voice:
            self.pv_note.set("請先填入 API Key 與音色")
            return
        if not text:
            self.pv_note.set("請先輸入試聽文字，或選擇旁白稿")
            return
        self.save_config()
        args = self.make_args()
        self.pv_btn.config(state="disabled")
        self.pv_note.set(f"產生中…（{len(text)} 字）")

        def work():
            try:
                audio, _ = core.tts(text, voice, key, args.model, args.format, False, args.voice_settings)
                path = Path(tempfile.gettempdir()) / f"txt2mp3srt_試聽_{int(time.time())}.mp3"
                path.write_bytes(audio)
                self.q.put(("preview", str(path), f"已產生試聽（扣約 {len(text)} 字額度）"))
            except Exception as e:
                self.q.put(("preview", None, f"試聽失敗：{e}"))
        threading.Thread(target=work, daemon=True).start()

    def refresh_quota(self):
        key = self.key.get().strip()
        if not key:
            self.quota = None
            self.quota_text.set("填入 API Key 後顯示剩餘額度")
            return
        self.quota_text.set("查詢額度中…")
        threading.Thread(target=self.fetch_quota, args=(key,), daemon=True).start()

    def pending_chars(self, force):
        n = 0
        for f in self.files:
            if self.status.get(f) == "done":
                continue
            out = Path(self.out_dir.get().strip()) if self.out_dir.get().strip() else f.parent
            if force or not (out / f"{f.stem}.mp3").exists():
                n += len(core.read_text(f))
        return n

    # ---------- 轉換 ----------
    def start(self):
        key = self.key.get().strip()
        args = self.make_args()
        if not key or not args.voice:
            messagebox.showwarning(APP_NAME, "請先填入 API Key 與 Voice ID")
            return
        if not self.files:
            messagebox.showwarning(APP_NAME, "請先選擇旁白稿")
            return
        self.save_config()
        try:  # 開始前確認額度夠不夠
            self.root.config(cursor="watch")
            self.root.update()
            q = core.get_quota(key)
            self.quota = q
            self.quota_text.set(core.format_quota(q))
            need = self.pending_chars(self.force.get())
            if need > q["left"] and not messagebox.askyesno(
                    APP_NAME, f"這批約需 {need:,} 字元，剩餘額度只有 {q['left']:,}。\n"
                              "（部分模型每字扣的額度較少，實際可能足夠）\n\n仍要開始轉換嗎？"):
                return
        except Exception as e:  # 查不到額度不影響轉換
            self.quota_text.set(str(e).split(" ", 1)[-1] if isinstance(e, core.ApiError) else "無法查詢額度")
        finally:
            self.root.config(cursor="")
        self.stop_flag = False
        self.set_running(True)
        self.worker = threading.Thread(target=self.run, args=(key, args, self.force.get()), daemon=True)
        self.worker.start()

    def run(self, key, args, force):
        log = lambda m: self.q.put(("log", m))
        done = skipped = failed = 0
        for f in list(self.files):
            if self.stop_flag:
                break
            if self.status.get(f) == "done":
                continue
            try:
                out = self.out_for(f)
                if not force and (out / f"{f.stem}.mp3").exists():
                    self.q.put(("status", f, "skip"))
                    skipped += 1
                    continue
                self.q.put(("status", f, "run"))
                log(f"轉換中：{f.name}")
                core.convert(f, out, key, args, log=log, should_stop=lambda: self.stop_flag)
                self.q.put(("status", f, "done"))
                self.fetch_quota(key)
                done += 1
            except core.Stopped:
                self.q.put(("status", f, "wait"))
                break
            except Exception as e:
                failed += 1
                self.q.put(("status", f, str(e)))
                log(f"✘ {f.name}：{e}")
                if isinstance(e, core.ApiError) and e.status == 401:
                    log("API Key 無效，停止。")
                    break
        stopped = "（已停止）" if self.stop_flag else ""
        self.q.put(("end", f"完成 {done}、略過 {skipped}、失敗 {failed}{stopped}"))

    def stop(self):
        self.stop_flag = True
        self.write_log("停止中…（目前這一段完成後停止）")

    def redo_srt(self):
        if not self.files:
            messagebox.showwarning(APP_NAME, "請先選擇旁白稿")
            return
        self.save_config()
        args = self.make_args()
        ok = 0
        for f in self.files:
            out = self.out_for(f)
            j = out / core.ALIGN_DIR / f"{f.stem}.json"
            if not j.exists():
                self.write_log(f"✘ {f.name}：沒有時間軸（請先轉換）")
                continue
            core.write_srt(out / f"{f.stem}.srt", json.loads(j.read_text(encoding="utf-8")), args)
            ok += 1
        self.write_log(f"已重做 {ok} 個字幕檔")

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel(APP_NAME, "還在轉換中，確定要關閉嗎？"):
                return
        self.save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform.startswith("win") else
                              "aqua" if sys.platform == "darwin" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
