"""Первый запуск: выбор логотипа и подбор цветовой схемы под него."""
from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from core.colors import PRESETS, logo_palette, readable_accent
from core.settings_store import APP_NAME
from ui import theme as T
from ui.transfer_actions import import_settings
from ui.widgets import Dialog, SwatchRow, primary_button, secondary_button


class LogoSetupDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Настройка оформления", 600, 520)
        self.app = app
        self.logo_path: str | None = None
        self.color = app.settings["accent_color"]
        self.protocol("WM_DELETE_WINDOW", self.skip)

        ctk.CTkLabel(self, text="Добро пожаловать!", font=T.font(22, "bold"), text_color=T.TEXT).pack(
            anchor="w", padx=28, pady=(26, 2))
        ctk.CTkLabel(self, text="Выберите логотип компании — программа подберёт под него цвета\n"
                                "интерфейса и коммерческих предложений.",
                     font=T.font(13), text_color=T.MUTED, justify="left").pack(anchor="w", padx=28)

        self.preview = ctk.CTkFrame(self, fg_color=T.CARD, corner_radius=12, border_width=1,
                                    border_color=T.BORDER, height=150)
        self.preview.pack(fill="x", padx=28, pady=18)
        self.preview.pack_propagate(False)
        self.logo_label = ctk.CTkLabel(self.preview, text="Логотип не выбран", font=T.font(13),
                                       text_color=T.MUTED)
        self.logo_label.pack(expand=True)

        picks = ctk.CTkFrame(self, fg_color="transparent")
        picks.pack(fill="x", padx=28)
        self.btn_pick = primary_button(picks, "🖼  Выбрать логотип…", self.pick_logo, width=200)
        self.btn_pick.pack(side="left")
        ctk.CTkLabel(picks, text="или", font=T.font(12), text_color=T.MUTED).pack(side="left", padx=12)
        secondary_button(picks, "⬇  Импорт настроек из файла…", self.import_profile, width=230, height=40).pack(
            side="left")

        ctk.CTkLabel(self, text="Цветовая схема", font=T.font(13, "bold"), text_color=T.TEXT).pack(
            anchor="w", padx=28, pady=(18, 4))
        self.swatches = SwatchRow(self, list(PRESETS.values()), self.set_color, selected=self.color)
        self.swatches.pack(anchor="w", padx=28)
        self.hint = ctk.CTkLabel(self, text="Готовые схемы. После выбора логотипа здесь появятся его цвета.",
                                 font=T.font(11), text_color=T.MUTED)
        self.hint.pack(anchor="w", padx=28, pady=(4, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=28, pady=22)
        self.btn_apply = primary_button(row, "Применить", self.apply, width=140)
        self.btn_apply.pack(side="right")
        secondary_button(row, "Пропустить", self.skip, width=120).pack(side="right", padx=8)
        ctk.CTkLabel(row, text="Всё это можно изменить позже\nв разделе «Шаблон КП»",
                     font=T.font(11), text_color=T.MUTED, justify="left").pack(side="left")

    def pick_logo(self):
        p = filedialog.askopenfilename(parent=self, title="Логотип компании",
                                       filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp")])
        if not p:
            return
        try:
            im = Image.open(p)
            im.load()
            palette = logo_palette(p)
        except Exception:  # noqa: BLE001
            messagebox.showerror(APP_NAME, "Не удалось открыть изображение.", parent=self)
            return
        self.logo_path = p
        im.thumbnail((420, 120))
        img = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        self.logo_label.configure(image=img, text="")
        self.logo_label._kp_img = img
        colors = [readable_accent(c) for c in palette] or list(PRESETS.values())
        self.swatches.set_colors(colors, selected=colors[0])
        self.set_color(colors[0])
        self.hint.configure(text="Цвета из логотипа — первый подобран автоматически, можно выбрать другой.")

    def set_color(self, color: str):
        self.color = color
        for b in (self.btn_apply, self.btn_pick):
            b.configure(fg_color=color, hover_color=color)

    def apply(self):
        s = self.app.settings
        if self.logo_path:
            s.set_image("logo", self.logo_path)
        s.save({"accent_color": self.color})
        s.set_state("logo_setup_done", True)
        self.destroy()
        need_company = not s["company_name"]
        self.app.rebuild("template" if need_company else None)
        if need_company:
            messagebox.showinfo(APP_NAME, "Теперь заполните данные компании на вкладке «Компания» "
                                          "и нажмите «Сохранить шаблон».")

    def import_profile(self):
        """Сотруднику прислали файл .pbsettings — сразу получает готовый шаблон компании."""
        if import_settings(self, self.app.settings):
            self.destroy()
            self.app.rebuild("new")

    def skip(self):
        self.app.settings.set_state("logo_setup_done", True)
        self.destroy()
