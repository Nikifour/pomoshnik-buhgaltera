"""Главное окно: боковое меню, страницы, баннер обновления."""
from __future__ import annotations

import threading
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from core import updater
from core.settings_store import APP_NAME, Settings, hash_password, resource_path
from ui import theme as T
from ui.page_history import HistoryPage
from ui.page_new import NewKPPage
from ui.page_template import TemplatePage
from ui.setup_dialog import LogoSetupDialog
from ui.transfer_actions import import_settings
from ui.widgets import Dialog, PasswordDialog, primary_button, secondary_button
from version import __version__

APPEARANCE = {"Светлая": "light", "Тёмная": "dark", "Как в системе": "system"}


class MainWindow(ctk.CTk):
    def __init__(self, import_file: str | None = None):
        self.settings = Settings()
        ctk.set_appearance_mode(self.settings.get_state("appearance", "light"))
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x780")
        self.minsize(980, 660)
        self.configure(fg_color=T.BG)
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            self.iconbitmap(str(icon))
        self.unlocked = False  # пароль на шаблон введён в этом сеансе
        self.release: updater.Release | None = None
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_ui("new")
        self.after(1500, lambda: self.check_updates(silent=True))
        if import_file:
            self.after(600, lambda: self._import_from_file(import_file))
        elif not self.settings.image_path("logo") and not self.settings.get_state("logo_setup_done"):
            self.after(600, lambda: LogoSetupDialog(self))

    def _import_from_file(self, path: str):
        if import_settings(self, self.settings, path):
            self.rebuild("new")
        elif not self.settings.image_path("logo") and not self.settings.get_state("logo_setup_done"):
            LogoSetupDialog(self)

    def _build_ui(self, page: str):
        T.apply_accent(self.settings["accent_color"])
        T.style_treeview(self)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(1, weight=1)
        self.banner = ctk.CTkFrame(self.content, fg_color=T.INFO_BG, corner_radius=10)
        self.pages = {
            "new": NewKPPage(self.content, self.settings, on_created=lambda: self.pages["history"].refresh()),
            "history": HistoryPage(self.content, self.settings),
            "template": TemplatePage(self.content, self.settings, on_saved=self._on_template_saved),
        }
        self.current = None
        self.show(page)
        if self.release:
            self._show_banner(self.release)

    def rebuild(self, page: str | None = None):
        """Пересоздать интерфейс — после смены цветовой схемы. Загруженный счёт сохраняется."""
        page = page or self.current or "new"
        invoice = self.pages["new"].invoice
        for w in self.winfo_children():
            if not isinstance(w, ctk.CTkToplevel):
                w.destroy()
        self._build_ui(page)
        if invoice:
            self.pages["new"].load_invoice(invoice.source)

    # ------------------------------------------------------------ меню
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=240)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)
        sb.rowconfigure(5, weight=1)

        head = ctk.CTkFrame(sb, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(26, 30))
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            im = Image.open(icon)
            im.size = (256, 256)  # из .ico берём самый крупный размер
            logo = ctk.CTkImage(light_image=im.convert("RGBA"), size=(46, 46))
            ctk.CTkLabel(head, text="", image=logo).pack(side="left")
        else:
            ctk.CTkLabel(head, text="ПБ", width=46, height=46, corner_radius=10, fg_color=T.BRAND_BRIGHT,
                         text_color="white", font=T.font(16, "bold")).pack(side="left")
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left", padx=12)
        ctk.CTkLabel(titles, text="Помощник\nБухгалтера", justify="left", font=T.font(15, "bold"), text_color="white",
                     anchor="w").pack(anchor="w")
        self.lbl_company = ctk.CTkLabel(titles, text=self.settings["company_name"], font=T.font(11),
                                        text_color=T.SIDEBAR_MUTED, anchor="w")
        self.lbl_company.pack(anchor="w")

        self.nav = {}
        for i, (key, text) in enumerate([("new", "＋   Новое КП"), ("history", "🕘   История"),
                                         ("template", "🎨   Шаблон КП")], start=1):
            b = ctk.CTkButton(sb, text=text, anchor="w", height=44, corner_radius=8, font=T.font(14),
                              fg_color="transparent", hover_color=T.SIDEBAR_HOVER, text_color="white",
                              command=lambda k=key: self.show(k))
            b.grid(row=i, column=0, sticky="ew", padx=12, pady=2)
            self.nav[key] = b

        bottom = ctk.CTkFrame(sb, fg_color="transparent")
        bottom.grid(row=6, column=0, sticky="ew", padx=16, pady=20)
        ctk.CTkLabel(bottom, text="Оформление", font=T.font(11), text_color=T.SIDEBAR_MUTED).pack(anchor="w")
        current = self.settings.get_state("appearance", "light")
        seg = ctk.CTkOptionMenu(bottom, values=list(APPEARANCE), command=self._set_appearance, height=30,
                                fg_color=T.SIDEBAR_ACTIVE, button_color=T.SIDEBAR_ACTIVE,
                                button_hover_color=T.SIDEBAR_HOVER, font=T.font(12))
        seg.set(next(k for k, v in APPEARANCE.items() if v == current))
        seg.pack(fill="x", pady=(4, 14))
        ctk.CTkButton(bottom, text="Проверить обновления", height=30, corner_radius=8, font=T.font(12),
                      fg_color="transparent", border_width=1, border_color=T.SIDEBAR_BORDER, hover_color=T.SIDEBAR_HOVER,
                      text_color="white", command=lambda: self.check_updates(silent=False)).pack(fill="x")
        ctk.CTkLabel(bottom, text=f"Версия {__version__}", font=T.font(11), text_color=T.SIDEBAR_MUTED).pack(
            anchor="w", pady=(8, 0))

    def show(self, key: str):
        if key == "template" and not self._unlock_template():
            return
        if self.current:
            self.pages[self.current].grid_forget()
        self.pages[key].grid(row=1, column=0, sticky="nsew", padx=32, pady=(24, 28))
        for k, b in self.nav.items():
            b.configure(fg_color=T.SIDEBAR_ACTIVE if k == key else "transparent")
        self.current = key
        if hasattr(self.pages[key], "refresh"):
            self.pages[key].refresh()

    def _unlock_template(self) -> bool:
        pw_hash = self.settings["editor_password_hash"]
        if not pw_hash or self.unlocked:
            return True
        pw = PasswordDialog.ask(self, "Пароль для изменения шаблона:")
        if pw is None:
            return False
        if hash_password(pw) != pw_hash:
            messagebox.showerror(APP_NAME, "Неверный пароль.")
            return False
        self.unlocked = True
        return True

    def _on_template_saved(self):
        if T.BRAND != T.readable_accent(self.settings["accent_color"]):
            self.rebuild()  # сменилась цветовая схема
            return
        self.lbl_company.configure(text=self.settings["company_name"])
        self.pages["new"].refresh()

    def _set_appearance(self, label: str):
        mode = APPEARANCE[label]
        ctk.set_appearance_mode(mode)
        self.settings.set_state("appearance", mode)
        self.after(50, lambda: T.style_treeview(self))

    # ------------------------------------------------------------ обновления
    def check_updates(self, silent: bool):
        def worker():
            try:
                rel, err = updater.check_for_update(), None
            except updater.UpdateError as e:
                rel, err = None, e
            self.after(0, self._update_checked, rel, err, silent)
        threading.Thread(target=worker, daemon=True).start()

    def _update_checked(self, rel, err, silent):
        if err:
            if not silent:
                messagebox.showwarning(APP_NAME, str(err))
            return
        if not rel:
            if not silent:
                messagebox.showinfo(APP_NAME, f"У вас последняя версия ({__version__}).")
            return
        self.release = rel
        self._show_banner(rel)
        if not silent:
            UpdateDialog(self, rel)

    def _show_banner(self, rel):
        for w in self.banner.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.banner, text=f"⬆  Доступна новая версия {rel.version}", font=T.font(13, "bold"),
                     text_color=T.TEXT).pack(side="left", padx=16, pady=10)
        primary_button(self.banner, "Обновить", lambda: UpdateDialog(self, rel), width=110, height=32).pack(
            side="right", padx=10)
        secondary_button(self.banner, "Позже", self.banner.grid_forget, width=80, height=32).pack(side="right")
        self.banner.grid(row=0, column=0, sticky="ew", padx=32, pady=(20, 0))


class UpdateDialog(Dialog):
    def __init__(self, master: MainWindow, rel: updater.Release):
        super().__init__(master, "Обновление", 540, 400)
        self.app = master
        self.rel = rel
        ctk.CTkLabel(self, text=f"Новая версия {rel.version}", font=T.font(18, "bold"), text_color=T.TEXT).pack(
            anchor="w", padx=24, pady=(22, 0))
        ctk.CTkLabel(self, text=f"Сейчас установлена {__version__}", font=T.font(12), text_color=T.MUTED).pack(
            anchor="w", padx=24)
        notes = ctk.CTkTextbox(self, height=170, font=T.font(12), border_width=1, border_color=T.BORDER)
        notes.pack(fill="both", expand=True, padx=24, pady=12)
        notes.insert("1.0", rel.notes or "Исправления и улучшения.")
        notes.configure(state="disabled")
        self.progress = ctk.CTkProgressBar(self, progress_color=T.BRAND)
        self.progress.set(0)
        self.status = ctk.CTkLabel(self, text="Программа перезапустится автоматически. Ваши настройки сохранятся.",
                                   font=T.font(11), text_color=T.MUTED)
        self.status.pack(anchor="w", padx=24)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=16)
        self.btn = primary_button(row, "Обновить сейчас", self.start, width=170, height=38)
        self.btn.pack(side="right")
        self.btn_later = secondary_button(row, "Позже", self.destroy, width=90)
        self.btn_later.pack(side="right", padx=8)

    def start(self):
        if not updater.is_frozen():
            messagebox.showinfo(APP_NAME, "Обновление устанавливается только в собранной программе (.exe).\n"
                                          "Сейчас программа запущена из исходного кода.", parent=self)
            return
        self.btn.configure(state="disabled", text="Загрузка…")
        self.btn_later.configure(state="disabled")
        self.progress.pack(fill="x", padx=24, pady=(0, 4), before=self.status)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            path = updater.download(self.rel, progress=lambda p: self.after(0, self.progress.set, p))
            self.after(0, self._install, path)
        except updater.UpdateError as e:
            self.after(0, self._failed, e)

    def _failed(self, e):
        self.btn.configure(state="normal", text="Повторить")
        self.btn_later.configure(state="normal")
        self.status.configure(text=str(e), text_color=T.DANGER)

    def _install(self, path):
        self.status.configure(text="Устанавливаю и перезапускаю…")
        try:
            updater.install_and_restart(path)
        except Exception as e:  # noqa: BLE001
            self._failed(e)
            return
        self.app.after(300, self.app.destroy)
