"""Общие элементы интерфейса."""
from __future__ import annotations

import os
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from core.settings_store import APP_NAME, resource_path
from ui import theme as T


def open_path(p: Path):
    try:
        os.startfile(str(p))  # noqa: S606 — Windows
    except OSError as e:
        messagebox.showerror(APP_NAME, f"Не удалось открыть:\n{p}\n\n{e}")


class Card(ctk.CTkFrame):
    """Белая карточка с заголовком."""

    def __init__(self, master, title: str = "", subtitle: str = "", **kw):
        super().__init__(master, fg_color=T.CARD, corner_radius=12, border_width=1,
                         border_color=T.BORDER, **kw)
        self.columnconfigure(0, weight=1)
        self.body_row = 0
        if title:
            ctk.CTkLabel(self, text=title, font=T.font(15, "bold"), text_color=T.TEXT, anchor="w").grid(
                row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
            self.body_row = 1
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=T.font(12), text_color=T.MUTED, anchor="w").grid(
                row=1, column=0, sticky="ew", padx=20)
            self.body_row = 2


def primary_button(master, text, command, **kw):
    kw.setdefault("height", 40)
    return ctk.CTkButton(master, text=text, command=command, fg_color=T.BRAND, hover_color=T.BRAND_HOVER,
                         font=T.font(13, "bold"), corner_radius=8, **kw)


def secondary_button(master, text, command, **kw):
    kw.setdefault("height", 36)
    return ctk.CTkButton(master, text=text, command=command, fg_color="transparent", border_width=1,
                         border_color=T.BORDER, text_color=T.TEXT, hover_color=T.BORDER,
                         font=T.font(13), corner_radius=8, **kw)


def page_header(master, title: str, subtitle: str = "") -> ctk.CTkFrame:
    f = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(f, text=title, font=T.font(24, "bold"), text_color=T.TEXT, anchor="w").pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(f, text=subtitle, font=T.font(13), text_color=T.MUTED, anchor="w").pack(anchor="w")
    return f


class Dialog(ctk.CTkToplevel):
    """Модальное окно поверх главного."""

    def __init__(self, master, title: str, width=460, height=240):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=T.BG)
        self.transient(master.winfo_toplevel())
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + (master.winfo_height() - height) // 3
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            # customtkinter ставит свою иконку через 200 мс — перебиваем позже
            self.after(250, lambda: self.iconbitmap(str(icon)))
        self.after(100, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except Exception:  # noqa: BLE001 — окно уже закрыто
            pass


class PasswordDialog(Dialog):
    def __init__(self, master, prompt: str):
        super().__init__(master, APP_NAME, 400, 190)
        self.value: str | None = None
        ctk.CTkLabel(self, text=prompt, font=T.font(14), text_color=T.TEXT).pack(padx=24, pady=(24, 10), anchor="w")
        self.entry = ctk.CTkEntry(self, show="•", height=38, font=T.font(14))
        self.entry.pack(fill="x", padx=24)
        self.entry.bind("<Return>", lambda e: self._ok())
        self.after(300, self.entry.focus_set)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=20)
        primary_button(row, "OK", self._ok, width=100, height=36).pack(side="right")
        secondary_button(row, "Отмена", self.destroy, width=100).pack(side="right", padx=8)

    def _ok(self):
        self.value = self.entry.get()
        self.destroy()

    @classmethod
    def ask(cls, master, prompt: str) -> str | None:
        d = cls(master, prompt)
        master.wait_window(d)
        return d.value


class SwatchRow(ctk.CTkFrame):
    """Ряд цветных кнопок для выбора цвета; выбранный цвет обведён."""

    def __init__(self, master, colors: list[str], on_pick, selected: str | None = None, size=34):
        super().__init__(master, fg_color="transparent")
        self.on_pick = on_pick
        self.size = size
        self.set_colors(colors, selected)

    def set_colors(self, colors: list[str], selected: str | None = None):
        for w in self.winfo_children():
            w.destroy()
        self.buttons = {}
        for c in colors:
            b = ctk.CTkButton(self, text="", width=self.size, height=self.size, corner_radius=self.size // 2,
                              fg_color=c, hover_color=c, border_width=0, border_color=T.TEXT,
                              command=lambda col=c: self.select(col, notify=True))
            b.pack(side="left", padx=(0, 8))
            self.buttons[c.upper()] = b
        self.select(selected)

    def select(self, color: str | None, notify=False):
        for c, b in self.buttons.items():
            b.configure(border_width=3 if color and c == color.upper() else 0)
        if notify and color:
            self.on_pick(color)
