"""Страница «Шаблон КП»: редактируемые поля шаблона."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from core.colors import PRESETS, logo_palette, readable_accent
from core.kp_builder import build_kp, demo_invoice
from core.settings_store import APP_NAME, DEFAULTS, IMAGE_KINDS, Settings, hash_password
from ui import theme as T
from ui.transfer_actions import export_settings, import_settings
from ui.widgets import Card, PasswordDialog, SwatchRow, open_path, page_header, primary_button, secondary_button

FIELDS = [
    ("company_name", "Краткое название"),
    ("company_full_name", "Полное название"),
    ("address", "Адрес"),
    ("phone", "Телефон компании"),
    ("email", "Email"),
    ("website", "Сайт / подпись под контактами"),
    ("manager_name", "ФИО подписанта"),
    ("manager_position", "Должность"),
    ("manager_phone", "Телефон подписанта"),
]
TEXTS = [
    ("greeting", "Текст приветствия",
     "Можно использовать {КОМПАНИЯ}, {ПОКУПАТЕЛЬ}, {МЕНЕДЖЕР} — подставятся автоматически", 90),
    ("conditions", "Условия предложения", "Каждая строка — отдельный пункт списка", 120),
    ("footer", "Подвал страницы", "Мелкий текст внизу каждой страницы (реквизиты, ссылки)", 60),
]
INVOICE_FIELDS = [
    ("fill_number", "Номер КП = номер счёта", "Выключено — программа нумерует КП сама по порядку"),
    ("fill_date", "Дата КП = дата счёта", "Выключено — ставится сегодняшняя дата"),
    ("fill_buyer", "Покупатель («Кому»)", "Название покупателя из счёта"),
    ("fill_buyer_details", "Реквизиты покупателя", "БИН / ИИН и адрес из счёта"),
    ("show_vat", "Строки «Итого» и «В т.ч. НДС»", "Выключено — в КП только итоговая сумма предложения"),
    ("show_amount_words", "Сумма прописью", "«Всего наименований …, на сумму …» и сумма прописью"),
]
IMAGES = [("logo", "Логотип компании"), ("logo2", "Второй логотип (бренд)"), ("stamp", "Печать и подпись")]


class TemplatePage(ctk.CTkFrame):
    def __init__(self, master, settings: Settings, on_saved=None):
        super().__init__(master, fg_color="transparent")
        self.s = settings
        self.on_saved = on_saved
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        page_header(self, "Шаблон КП", "Контакты, тексты, логотипы и печать").grid(
            row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(self, text="⚠  Изменения применяются ко всем будущим КП. Перед сохранением создаётся резервная копия.",
                     fg_color=T.WARN_BG, text_color=T.WARN_TEXT, corner_radius=8, font=T.font(12),
                     anchor="w", height=34).grid(row=1, column=0, sticky="ew", pady=(0, 12), ipadx=12)

        self.tabs = ctk.CTkTabview(self, fg_color=T.CARD, segmented_button_selected_color=T.BRAND,
                                   segmented_button_selected_hover_color=T.BRAND_HOVER,
                                   border_width=1, border_color=T.BORDER, corner_radius=12)
        self.tabs.grid(row=2, column=0, sticky="nsew")
        for name in ("Компания", "Тексты", "Из счёта", "Оформление", "Прочее"):
            self.tabs.add(name)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        secondary_button(bar, "👁  Предпросмотр", self.preview, width=150).pack(side="left")
        primary_button(bar, "Сохранить шаблон", self.save, width=180).pack(side="right")
        secondary_button(bar, "Отменить изменения", self.load_values, width=170).pack(side="right", padx=8)

        self.vars: dict[str, ctk.Variable] = {}
        self.texts: dict[str, ctk.CTkTextbox] = {}
        self.thumbs: dict[str, ctk.CTkLabel] = {}
        self._build_company(self.tabs.tab("Компания"))
        self._build_texts(self.tabs.tab("Тексты"))
        self._build_design(self.tabs.tab("Оформление"))
        self._build_invoice(self.tabs.tab("Из счёта"))
        self._build_other(self.tabs.tab("Прочее"))
        self.load_values()

    # ------------------------------------------------------------ вкладки
    def _build_company(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        for i, (key, label) in enumerate(FIELDS):
            ctk.CTkLabel(f, text=label, font=T.font(13), text_color=T.MUTED, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(8, 16), pady=5)
            self.vars[key] = ctk.StringVar()
            ctk.CTkEntry(f, textvariable=self.vars[key], height=34, font=T.font(13)).grid(
                row=i, column=1, sticky="ew", padx=(0, 8), pady=5)

    def _build_texts(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        r = 0
        for key, label, hint, h in TEXTS:
            ctk.CTkLabel(f, text=label, font=T.font(13, "bold"), text_color=T.TEXT, anchor="w").grid(
                row=r, column=0, sticky="w", padx=8)
            ctk.CTkLabel(f, text=hint, font=T.font(11), text_color=T.MUTED, anchor="w").grid(
                row=r + 1, column=0, sticky="w", padx=8)
            t = ctk.CTkTextbox(f, height=h, font=T.font(13), border_width=1, border_color=T.BORDER, wrap="word")
            t.grid(row=r + 2, column=0, sticky="ew", padx=8, pady=(4, 14))
            self.texts[key] = t
            r += 3

    def _build_design(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.columnconfigure((0, 1), weight=1)
        for i, (kind, title) in enumerate(IMAGES):
            box = Card(f, title)
            box.grid(row=i // 2 + 1, column=i % 2, sticky="nsew", padx=6, pady=6)
            lbl = ctk.CTkLabel(box, text="", height=90)
            lbl.grid(row=box.body_row, column=0, pady=8)
            self.thumbs[kind] = lbl
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.grid(row=box.body_row + 1, column=0, pady=(0, 14))
            secondary_button(row, "Загрузить…", lambda k=kind: self.pick_image(k), width=110, height=32).pack(side="left")
            secondary_button(row, "Убрать", lambda k=kind: self.remove_image(k), width=80, height=32).pack(side="left", padx=6)

        opts = ctk.CTkFrame(f, fg_color="transparent")
        opts.grid(row=2, column=1, sticky="nw", padx=12, pady=12)
        self.vars["show_stamp"] = ctk.BooleanVar()
        ctk.CTkSwitch(opts, text="Ставить печать и подпись в КП", variable=self.vars["show_stamp"],
                      font=T.font(13), progress_color=T.BRAND).pack(anchor="w", pady=(0, 16))
        ctk.CTkLabel(opts, text="Логотипы и печать — PNG с прозрачным фоном,\nот 400 px в ширину.",
                     font=T.font(11), text_color=T.MUTED, justify="left").pack(anchor="w")

        scheme = Card(f, "Цветовая схема", "Применяется к интерфейсу программы и к коммерческим предложениям")
        scheme.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        self.vars["accent_color"] = ctk.StringVar()
        self.scheme_swatches = SwatchRow(scheme, list(PRESETS.values()), self.set_color)
        self.scheme_swatches.grid(row=scheme.body_row, column=0, sticky="w", padx=20, pady=(10, 6))
        crow = ctk.CTkFrame(scheme, fg_color="transparent")
        crow.grid(row=scheme.body_row + 1, column=0, sticky="w", padx=20, pady=(4, 16))
        ctk.CTkLabel(crow, text="Текущий цвет", font=T.font(13), text_color=T.TEXT).pack(side="left")
        self.swatch = ctk.CTkButton(crow, text="", width=36, height=28, corner_radius=6, command=self.pick_color)
        self.swatch.pack(side="left", padx=10)
        secondary_button(crow, "Свой цвет…", self.pick_color, width=110, height=30).pack(side="left")
        secondary_button(crow, "Подобрать по логотипу", self.color_from_logo, width=180, height=30).pack(
            side="left", padx=8)

    def _build_invoice(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text="Что переносить из счёта на оплату в КП", font=T.font(14, "bold"),
                     text_color=T.TEXT, anchor="w").grid(row=0, column=0, sticky="w", padx=8, pady=(4, 0))
        ctk.CTkLabel(f, text="Выключенные поля в окне «Новое КП» остаются пустыми — их можно заполнить вручную. "
                             "Позиции и суммы переносятся всегда.",
                     font=T.font(11), text_color=T.MUTED, anchor="w", wraplength=760, justify="left").grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 10))
        for i, (key, title, hint) in enumerate(INVOICE_FIELDS):
            row = ctk.CTkFrame(f, fg_color=T.BG if i % 2 == 0 else "transparent", corner_radius=8)
            row.grid(row=i + 2, column=0, sticky="ew", padx=4, pady=1)
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=title, font=T.font(13), text_color=T.TEXT, anchor="w").grid(
                row=0, column=0, sticky="w", padx=14, pady=(8, 0))
            ctk.CTkLabel(row, text=hint, font=T.font(11), text_color=T.MUTED, anchor="w").grid(
                row=1, column=0, sticky="w", padx=14, pady=(0, 8))
            self.vars[key] = ctk.BooleanVar()
            ctk.CTkSwitch(row, text="", variable=self.vars[key], progress_color=T.BRAND, width=50).grid(
                row=0, column=1, rowspan=2, padx=14)

    def _build_other(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)

        ctk.CTkLabel(f, text="Срок действия КП, дней", font=T.font(13), text_color=T.MUTED).grid(
            row=0, column=0, sticky="w", padx=8, pady=6)
        self.vars["validity_days"] = ctk.StringVar()
        vrow = ctk.CTkFrame(f, fg_color="transparent")
        vrow.grid(row=0, column=1, sticky="w")
        ctk.CTkEntry(vrow, textvariable=self.vars["validity_days"], width=70, height=34).pack(side="left")
        ctk.CTkLabel(vrow, text="0 — не указывать срок", font=T.font(11), text_color=T.MUTED).pack(side="left", padx=10)

        ctk.CTkLabel(f, text="Папка для готовых КП", font=T.font(13), text_color=T.MUTED).grid(
            row=1, column=0, sticky="w", padx=8, pady=6)
        self.vars["output_dir"] = ctk.StringVar()
        drow = ctk.CTkFrame(f, fg_color="transparent")
        drow.grid(row=1, column=1, sticky="ew", padx=(0, 8))
        drow.columnconfigure(0, weight=1)
        ctk.CTkEntry(drow, textvariable=self.vars["output_dir"], height=34).grid(row=0, column=0, sticky="ew")
        secondary_button(drow, "…", self.pick_dir, width=40, height=34).grid(row=0, column=1, padx=(6, 0))

        self.vars["also_pdf"] = ctk.BooleanVar()
        ctk.CTkSwitch(f, text="По умолчанию сохранять также в PDF", variable=self.vars["also_pdf"],
                      font=T.font(13), progress_color=T.BRAND).grid(row=2, column=1, sticky="w", pady=8)

        sec = Card(f, "Защита")
        sec.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        srow = ctk.CTkFrame(sec, fg_color="transparent")
        srow.grid(row=sec.body_row, column=0, sticky="ew", padx=20, pady=(6, 16))
        self.pw_label = ctk.CTkLabel(srow, text="", font=T.font(13), text_color=T.TEXT)
        self.pw_label.pack(side="left")
        secondary_button(srow, "Снять пароль", self.clear_password, width=130, height=32).pack(side="right")
        secondary_button(srow, "Задать пароль…", self.set_password, width=140, height=32).pack(side="right", padx=8)

        bk = Card(f, "Резервные копии", "Создаются автоматически при каждом сохранении (последние 10)")
        bk.grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        brow = ctk.CTkFrame(bk, fg_color="transparent")
        brow.grid(row=bk.body_row, column=0, sticky="ew", padx=20, pady=(8, 16))
        self.backup_menu = ctk.CTkOptionMenu(brow, values=["—"], width=240, fg_color=T.BRAND,
                                             button_color=T.BRAND_HOVER, button_hover_color=T.BRAND_HOVER)
        self.backup_menu.pack(side="left")
        secondary_button(brow, "Восстановить", self.restore_backup, width=120, height=32).pack(side="left", padx=8)
        secondary_button(brow, "Сбросить к исходным", self.reset_defaults, width=170, height=32).pack(side="right")

        tr = Card(f, "Перенос настроек", "Один файл с контактами, текстами, логотипами и цветами — "
                                         "чтобы настроить программу у сотрудника за минуту")
        tr.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        trow = ctk.CTkFrame(tr, fg_color="transparent")
        trow.grid(row=tr.body_row, column=0, sticky="ew", padx=20, pady=(8, 16))
        primary_button(trow, "⬆  Экспорт настроек…", lambda: export_settings(self, self.s),
                       width=200, height=34).pack(side="left")
        secondary_button(trow, "⬇  Импорт настроек…", self.import_profile, width=200, height=34).pack(
            side="left", padx=8)

        self.lbl_dir = ctk.CTkLabel(f, text="", font=T.font(11), text_color=T.MUTED, anchor="w")
        self.lbl_dir.grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=8)

    # ------------------------------------------------------------ данные
    def load_values(self):
        """Заполнить форму текущими сохранёнными настройками (сбрасывает несохранённое)."""
        for k, v in self.vars.items():
            v.set(self.s[k])
        for k, t in self.texts.items():
            t.delete("1.0", "end")
            t.insert("1.0", self.s[k])
        self.new_images: dict[str, str | None] = {k: None for k in IMAGE_KINDS}
        for kind in IMAGE_KINDS:
            self._show_thumb(kind, self.s.image_path(kind))
        self._new_pw_hash = self.s["editor_password_hash"]
        self._update_pw_label()
        self.scheme_swatches.set_colors(list(PRESETS.values()))
        self.set_color(self.s["accent_color"])
        self._fill_backups()
        self.lbl_dir.configure(text=f"Настройки хранятся в: {self.s.dir}")

    def collect(self) -> dict:
        vals = {k: v.get() for k, v in self.vars.items()}
        try:
            vals["validity_days"] = max(0, int(str(vals["validity_days"]).strip() or 0))
        except ValueError:
            vals["validity_days"] = DEFAULTS["validity_days"]
        vals["company_name"] = vals["company_name"].strip()
        for k, t in self.texts.items():
            vals[k] = t.get("1.0", "end-1c").strip()
        vals["editor_password_hash"] = self._new_pw_hash
        return vals

    def _image_for(self, kind):
        new = self.new_images[kind]
        if new is None:
            return self.s.image_path(kind)
        return Path(new) if new else None

    def _show_thumb(self, kind, path):
        lbl = self.thumbs[kind]
        if not path:
            lbl.configure(image=None, text="нет картинки", text_color=T.MUTED)
            lbl._kp_img = None
            return
        im = Image.open(path)
        im.thumbnail((240, 90))
        img = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
        lbl.configure(image=img, text="")
        lbl._kp_img = img  # держим ссылку, иначе картинку соберёт сборщик мусора

    # ------------------------------------------------------------ действия
    def pick_image(self, kind):
        p = filedialog.askopenfilename(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp")])
        if not p:
            return
        try:
            Image.open(p).verify()
        except Exception:  # noqa: BLE001
            messagebox.showerror(APP_NAME, "Файл не является изображением.")
            return
        self.new_images[kind] = p
        self._show_thumb(kind, p)

    def remove_image(self, kind):
        self.new_images[kind] = ""
        self._show_thumb(kind, None)

    def set_color(self, c: str):
        self.vars["accent_color"].set(c)
        self.swatch.configure(fg_color=c, hover_color=c)
        self.scheme_swatches.select(c)

    def pick_color(self):
        c = colorchooser.askcolor(self.vars["accent_color"].get())[1]
        if c:
            self.set_color(readable_accent(c.upper()))

    def color_from_logo(self):
        logo = self._image_for("logo")
        if not logo:
            messagebox.showinfo(APP_NAME, "Сначала загрузите логотип компании.")
            return
        palette = [readable_accent(c) for c in logo_palette(logo)]
        if not palette:
            messagebox.showinfo(APP_NAME, "Не удалось определить цвета логотипа.")
            return
        # к готовым схемам добавляем цвета логотипа
        self.scheme_swatches.set_colors(palette + [c for c in PRESETS.values() if c not in palette][:8 - len(palette)])
        self.set_color(palette[0])

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.vars["output_dir"].get())
        if d:
            self.vars["output_dir"].set(d)

    def _update_pw_label(self):
        self.pw_label.configure(text="🔒  Пароль на шаблон установлен" if self._new_pw_hash
                                else "🔓  Пароль не задан — шаблон может менять любой")

    def set_password(self):
        a = PasswordDialog.ask(self, "Новый пароль:")
        if not a:
            return
        b = PasswordDialog.ask(self, "Повторите пароль:")
        if a != b:
            messagebox.showerror(APP_NAME, "Пароли не совпадают.")
            return
        self._new_pw_hash = hash_password(a)
        self._update_pw_label()

    def clear_password(self):
        self._new_pw_hash = ""
        self._update_pw_label()

    def _fill_backups(self):
        self._backups = {}
        for b in self.s.list_backups():
            try:
                label = datetime.strptime(b.stem[:19], "%Y-%m-%d_%H-%M-%S").strftime("%d.%m.%Y  %H:%M:%S")
            except ValueError:
                label = b.stem
            while label in self._backups:
                label += " "
            self._backups[label] = b
        values = list(self._backups) or ["Копий пока нет"]
        self.backup_menu.configure(values=values)
        self.backup_menu.set(values[0])

    def preview(self):
        vals = {**self.s.values, **self.collect()}
        inv, meta = demo_invoice()
        out = Path(tempfile.gettempdir()) / f"КП_предпросмотр_{datetime.now():%H%M%S}.xlsx"
        try:
            build_kp(inv, meta, vals, {k: self._image_for(k) for k in IMAGE_KINDS}, out)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(APP_NAME, f"Ошибка предпросмотра:\n{e}")
            return
        open_path(out)

    def save(self):
        vals = self.collect()
        if not vals["company_name"]:
            messagebox.showerror(APP_NAME, "Укажите краткое название компании.")
            return
        if not messagebox.askyesno(APP_NAME, "Изменения применятся ко всем будущим коммерческим предложениям.\n\n"
                                             "Текущие настройки будут сохранены в резервную копию. Продолжить?",
                                   icon="warning"):
            return
        self.s.save(vals)
        for kind, new in self.new_images.items():
            if new is not None:
                self.s.set_image(kind, new or None)
        self.load_values()
        if self.on_saved:
            self.on_saved()
        messagebox.showinfo(APP_NAME, "Шаблон сохранён.")

    def restore_backup(self):
        label = self.backup_menu.get()
        b = self._backups.get(label)
        if not b:
            return
        if messagebox.askyesno(APP_NAME, f"Восстановить шаблон из копии «{label.strip()}»?\n"
                                         "Текущие настройки тоже будут сохранены в копию."):
            self.s.restore(b)
            self.load_values()
            if self.on_saved:
                self.on_saved()
            messagebox.showinfo(APP_NAME, "Шаблон восстановлен.")

    def import_profile(self):
        if import_settings(self, self.s):
            self.load_values()
            if self.on_saved:
                self.on_saved()

    def reset_defaults(self):
        if messagebox.askyesno(APP_NAME, "Очистить контакты и тексты шаблона и вернуть исходные настройки?\n"
                                         "Логотипы и печать останутся.\n\n"
                                         "Текущие настройки будут сохранены в резервную копию.", icon="warning"):
            self.s.reset_to_defaults()
            self.load_values()
            if self.on_saved:
                self.on_saved()
            messagebox.showinfo(APP_NAME, "Шаблон сброшен к исходным настройкам.")
