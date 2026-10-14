"""Цвета и шрифты интерфейса. Пары (светлая тема, тёмная тема).

Фирменные цвета вычисляются из одного акцентного цвета (настройка «Цветовая схема»,
её же можно подобрать по логотипу) — см. apply_accent().
"""
from tkinter import ttk

import customtkinter as ctk

from core.colors import mix, readable_accent
from core.settings_store import DEFAULT_ACCENT

BG = ("#F3F4F6", "#16171A")
CARD = ("#FFFFFF", "#212226")
BORDER = ("#E2E4E8", "#33353A")
TEXT = ("#1F2937", "#E5E7EB")
MUTED = ("#6B7280", "#9CA3AF")
WARN_BG = ("#FEF3C7", "#3A2F12")
WARN_TEXT = ("#92400E", "#FCD34D")
DANGER = "#B91C1C"

FONT_FAMILY = "Segoe UI"

# Заполняются в apply_accent()
BRAND = BRAND_HOVER = BRAND_BRIGHT = ""
SIDEBAR = SIDEBAR_ACTIVE = SIDEBAR_HOVER = ("", "")
SIDEBAR_MUTED = SIDEBAR_BORDER = ""
INFO_BG = ("", "")


def apply_accent(accent: str):
    """Пересчитать фирменные цвета интерфейса из акцентного цвета."""
    global BRAND, BRAND_HOVER, BRAND_BRIGHT, SIDEBAR, SIDEBAR_ACTIVE, SIDEBAR_HOVER
    global SIDEBAR_MUTED, SIDEBAR_BORDER, INFO_BG
    try:
        BRAND = readable_accent(accent)
    except (ValueError, IndexError):
        BRAND = DEFAULT_ACCENT
    BRAND_HOVER = mix(BRAND, "#000000", 0.25)
    BRAND_BRIGHT = mix(BRAND, "#FFFFFF", 0.25)
    sidebar = mix(BRAND, "#000000", 0.25)
    sidebar_dark = mix(BRAND, "#000000", 0.62)
    SIDEBAR = (sidebar, sidebar_dark)
    SIDEBAR_ACTIVE = (mix(sidebar, "#FFFFFF", 0.14), mix(sidebar_dark, "#FFFFFF", 0.12))
    SIDEBAR_HOVER = (mix(sidebar, "#FFFFFF", 0.07), mix(sidebar_dark, "#FFFFFF", 0.06))
    SIDEBAR_MUTED = mix(sidebar, "#FFFFFF", 0.65)
    SIDEBAR_BORDER = mix(sidebar, "#FFFFFF", 0.3)
    INFO_BG = (mix(BRAND, "#FFFFFF", 0.88), mix(BRAND, "#000000", 0.55))


apply_accent(DEFAULT_ACCENT)


def font(size=13, weight="normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def pick(pair):
    """Цвет из пары для текущей темы (нужно для ttk-виджетов)."""
    return pair[1] if ctk.get_appearance_mode() == "Dark" else pair[0]


def style_treeview(root):
    """ttk.Treeview не умеет темы customtkinter — красим вручную."""
    st = ttk.Style(root)
    st.theme_use("clam")
    bg, fg, border = pick(CARD), pick(TEXT), pick(BORDER)
    st.configure("KP.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                 rowheight=32, borderwidth=0, font=(FONT_FAMILY, 10))
    st.map("KP.Treeview", background=[("selected", BRAND)], foreground=[("selected", "white")])
    st.configure("KP.Treeview.Heading", background=pick(BG), foreground=pick(MUTED),
                 borderwidth=0, relief="flat", font=(FONT_FAMILY, 10, "bold"), padding=(6, 6))
    st.map("KP.Treeview.Heading", background=[("active", border)])
    st.layout("KP.Treeview", [("KP.Treeview.treearea", {"sticky": "nswe"})])
