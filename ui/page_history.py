"""Страница «История»: созданные КП из папки вывода."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from core.settings_store import Settings
from ui import theme as T
from ui.widgets import Card, open_path, page_header, secondary_button

MAX_ROWS = 200


class HistoryPage(ctk.CTkFrame):
    def __init__(self, master, settings: Settings):
        super().__init__(master, fg_color="transparent")
        self.s = settings
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        page_header(head, "История", "Коммерческие предложения в папке сохранения").pack(side="left")
        secondary_button(head, "📁  Открыть папку", self.open_dir, width=160).pack(side="right")
        secondary_button(head, "⟳  Обновить", self.refresh, width=120).pack(side="right", padx=8)

        # без textvariable — иначе customtkinter не показывает подсказку в пустом поле
        self.search = ctk.CTkEntry(self, height=38, font=T.font(13),
                                   placeholder_text="🔍  Поиск по номеру или покупателю…")
        self.search.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.search.bind("<KeyRelease>", lambda e: self.refresh())

        self.card = Card(self)
        self.card.grid(row=2, column=0, sticky="nsew")
        self.card.rowconfigure(0, weight=1)
        self.list = ctk.CTkScrollableFrame(self.card, fg_color="transparent")
        self.list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.list.columnconfigure(0, weight=1)

    def open_dir(self):
        d = Path(self.s["output_dir"])
        d.mkdir(parents=True, exist_ok=True)
        open_path(d)

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        d = Path(self.s["output_dir"])
        q = self.search.get().strip().lower()
        files = sorted(d.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []
        files = [f for f in files if not f.name.startswith("~$") and (not q or q in f.stem.lower())][:MAX_ROWS]
        if not files:
            ctk.CTkLabel(self.list, text="Пока пусто — созданные КП появятся здесь" if not q else "Ничего не найдено",
                         font=T.font(13), text_color=T.MUTED).grid(row=0, column=0, pady=40)
            return
        for i, f in enumerate(files):
            row = ctk.CTkFrame(self.list, fg_color=T.BG if i % 2 else "transparent", corner_radius=8)
            row.grid(row=i, column=0, sticky="ew", pady=1)
            row.columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="📄", font=T.font(18)).grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=6)
            ctk.CTkLabel(row, text=f.stem, font=T.font(13, "bold"), text_color=T.TEXT, anchor="w").grid(
                row=0, column=1, sticky="ew", pady=(6, 0))
            ctk.CTkLabel(row, text=f"{datetime.fromtimestamp(f.stat().st_mtime):%d.%m.%Y %H:%M}",
                         font=T.font(11), text_color=T.MUTED, anchor="w").grid(row=1, column=1, sticky="ew", pady=(0, 6))
            pdf = f.with_suffix(".pdf")
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=0, column=2, rowspan=2, padx=12)
            secondary_button(btns, "Excel", lambda p=f: open_path(p), width=70, height=30).pack(side="left")
            if pdf.exists():
                secondary_button(btns, "PDF", lambda p=pdf: open_path(p), width=60, height=30).pack(side="left", padx=6)
