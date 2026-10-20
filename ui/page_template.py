"""Страница «Шаблон КП»: редактируемые поля шаблона."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFileDialog, QFormLayout, QGridLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from core.colors import PRESETS, logo_palette, readable_accent
from core import richtext
from core.kp_builder import auto_signature, build_kp, demo_invoice, signature_lines
from core.settings_store import DEFAULTS, IMAGE_KINDS, Settings, hash_password
from ui.rich_edit import RichTextEdit
from ui.transfer_actions import export_settings, import_settings
from ui.widgets import (Card, SwatchRow, Toggle, ask, ask_password, button, error, hbox, info, label,
                        open_path, page_header, scroll_area)

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
     "Выделите текст и задайте оформление кнопками сверху. {КОМПАНИЯ}, {ПОКУПАТЕЛЬ}, {МЕНЕДЖЕР} "
     "подставятся автоматически", 100),
    ("conditions", "Условия предложения", "Каждая строка — отдельный пункт списка", 140),
    ("signature_text", "Подпись внизу КП",
     "Выделите текст и задайте оформление кнопками сверху. Кнопка «WhatsApp» ставит значок после номера. "
     "Можно {КОМПАНИЯ}, {МЕНЕДЖЕР}", 130),
    ("from_details", "Строка «От» — под названием компании",
     "Мелким шрифтом под «От: компания», например БИН и адрес. Пусто — строки нет", 60),
    ("footer", "Подвал страницы", "Мелкий текст внизу каждой страницы (реквизиты, ссылки)", 60),
]
RICH = ("greeting", "signature_text")  # поля с кнопками оформления


def _plain_greeting(text: str) -> list:
    return richtext.from_plain(text, lambda i: dict(s=10))


INVOICE_FIELDS = [
    ("fill_number", "Номер КП = номер счёта", "Выключено — программа нумерует КП сама по порядку"),
    ("fill_date", "Дата КП = дата счёта", "Выключено — ставится сегодняшняя дата"),
    ("fill_buyer", "Покупатель («Кому»)", "Название покупателя из счёта"),
    ("fill_buyer_details", "Реквизиты покупателя", "БИН / ИИН и адрес из счёта"),
    ("show_vat", "Строки «Итого» и «В т.ч. НДС»", "Выключено — в КП только итоговая сумма предложения"),
]
IMAGES = [("logo", "Логотип компании"), ("logo2", "Второй логотип (бренд)"), ("stamp", "Печать и подпись")]


def _tab(*widgets) -> QWidget:
    inner = QWidget()
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(16, 12, 16, 16)
    lay.setSpacing(12)
    for w in widgets:
        lay.addWidget(w)
    lay.addStretch(1)
    return scroll_area(inner)


class TemplatePage(QWidget):
    def __init__(self, settings: Settings, on_saved=None):
        super().__init__()
        self.setObjectName("page")
        self.s = settings
        self.on_saved = on_saved
        self.lines: dict[str, QLineEdit] = {}
        self.texts: dict[str, QPlainTextEdit] = {}
        self.rich: dict[str, RichTextEdit] = {}
        self.toggles: dict[str, Toggle] = {}
        self.thumbs: dict[str, QLabel] = {}
        self.accent = self.s["accent_color"]
        self.new_images: dict[str, str | None] = {}
        self._new_pw_hash = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_header("Шаблон КП", "Контакты, тексты, логотипы и печать"))
        root.addWidget(label("⚠  Изменения применяются ко всем будущим КП. Перед сохранением создаётся "
                             "резервная копия.", name="warn"))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_company(), "Компания")
        self.tabs.addTab(self._tab_texts(), "Тексты")
        self.tabs.addTab(self._tab_invoice(), "Из счёта")
        self.tabs.addTab(self._tab_design(), "Оформление")
        self.tabs.addTab(self._tab_other(), "Прочее")
        root.addWidget(self.tabs, 1)

        root.addLayout(hbox(button("👁  Предпросмотр", self.preview), "stretch",
                            button("Отменить изменения", self.load_values),
                            button("Сохранить шаблон", self.save, primary=True, width=180)))
        self.load_values()

    # ------------------------------------------------------------ вкладки
    def _tab_company(self):
        card = Card()
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for key, title in FIELDS:
            self.lines[key] = QLineEdit()
            if key in ("phone", "manager_phone"):
                self.lines[key].setPlaceholderText("например: +7 777 123 45 67 {WhatsApp} — с {WhatsApp} в КП будет значок")
            form.addRow(label(title, muted=True), self.lines[key])
        card.body.addLayout(form)
        return _tab(card)

    def _tab_texts(self):
        card = Card()
        for key, title, hint, h in TEXTS:
            card.body.addWidget(label(title, name="h2"))
            card.body.addWidget(label(hint, muted=True, small=True))
            if key in RICH:
                t = RichTextEdit(h)  # с кнопками оформления: жирный, курсив, цвет, размер
                self.rich[key] = t
            else:
                t = QPlainTextEdit()
                t.setFixedHeight(h)
                self.texts[key] = t
            card.body.addWidget(t)
            card.body.addSpacing(8)
        return _tab(card)

    def _tab_invoice(self):
        card = Card("Что переносить из счёта на оплату в КП",
                    "Выключенные поля в окне «Новое КП» остаются пустыми — их можно заполнить вручную. "
                    "Позиции и суммы переносятся всегда.")
        for key, title, hint in INVOICE_FIELDS:
            texts = QVBoxLayout()
            texts.setSpacing(0)
            texts.addWidget(label(title))
            texts.addWidget(label(hint, muted=True, small=True))
            self.toggles[key] = Toggle()
            row = hbox("stretch", self.toggles[key], margins=(4, 6, 4, 6))
            row.insertLayout(0, texts, 1)
            card.body.addLayout(row)
        return _tab(card)

    def _tab_design(self):
        scheme = Card("Цветовая схема", "Применяется к интерфейсу программы и к коммерческим предложениям")
        self.swatches = SwatchRow(list(PRESETS.values()))
        self.swatches.picked.connect(self.set_color)
        self.current_swatch = QPushButton()
        self.current_swatch.setFixedSize(40, 30)
        self.current_swatch.setCursor(Qt.PointingHandCursor)
        self.current_swatch.clicked.connect(self.pick_color)
        scheme.body.addWidget(self.swatches)
        scheme.body.addLayout(hbox(label("Текущий цвет"), self.current_swatch, button("Свой цвет…", self.pick_color),
                                   button("Подобрать по логотипу", self.color_from_logo), "stretch"))

        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for i, (kind, title) in enumerate(IMAGES):
            card = Card(title)
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setMinimumHeight(96)
            self.thumbs[kind] = thumb
            card.body.addWidget(thumb)
            card.body.addLayout(hbox("stretch", button("Загрузить…", lambda k=kind: self.pick_image(k)),
                                     button("Убрать", lambda k=kind: self.remove_image(k)), "stretch"))
            grid.addWidget(card, i // 2, i % 2)
        opts = QWidget()
        ol = QVBoxLayout(opts)
        ol.setContentsMargins(8, 8, 8, 8)
        self.toggles["show_stamp"] = Toggle("Ставить печать и подпись в КП")
        ol.addWidget(self.toggles["show_stamp"])
        ol.addWidget(label("Логотипы и печать — PNG с прозрачным фоном, от 400 px в ширину.", muted=True,
                           small=True, wrap=True))
        ol.addStretch(1)
        grid.addWidget(opts, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return _tab(scheme, grid_w)

    def _tab_other(self):
        main = Card()
        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.spin_validity = QSpinBox()
        self.spin_validity.setRange(0, 365)
        self.spin_validity.setFixedWidth(90)
        form.addRow(label("Срок действия КП, дней", muted=True),
                    hbox(self.spin_validity, label("0 — не указывать срок", muted=True, small=True), "stretch"))
        self.ed_output = QLineEdit()
        form.addRow(label("Папка для готовых КП", muted=True), hbox(self.ed_output, button("…", self.pick_dir)))
        self.toggles["also_pdf"] = Toggle("По умолчанию сохранять также в PDF")
        form.addRow("", self.toggles["also_pdf"])
        main.body.addLayout(form)

        transfer = Card("Перенос настроек", "Один файл с контактами, текстами, логотипами и цветами — "
                                            "чтобы настроить программу у сотрудника за минуту")
        transfer.body.addLayout(hbox(button("⬆  Экспорт настроек…", lambda: export_settings(self, self.s), primary=True),
                                     button("⬇  Импорт настроек…", self.import_profile), "stretch"))

        sec = Card("Защита")
        self.pw_label = label("")
        sec.body.addLayout(hbox(self.pw_label, "stretch", button("Задать пароль…", self.set_password),
                                button("Снять пароль", self.clear_password)))

        bk = Card("Резервные копии", "Создаются автоматически при каждом сохранении (последние 10)")
        self.backup_combo = QComboBox()
        self.backup_combo.setMinimumWidth(240)
        bk.body.addLayout(hbox(self.backup_combo, button("Восстановить", self.restore_backup), "stretch",
                               button("Сбросить к исходным", self.reset_defaults)))

        self.lbl_dir = label("", muted=True, small=True, wrap=True)
        self.lbl_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # длинный путь без пробелов не должен растягивать страницу вправо
        self.lbl_dir.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return _tab(main, transfer, sec, bk, self.lbl_dir)

    # ------------------------------------------------------------ данные
    def load_values(self):
        """Заполнить форму сохранёнными настройками (сбрасывает несохранённое)."""
        s = self.s
        for k, w in self.lines.items():
            w.setText(str(s[k]))
        for k, t in self.texts.items():
            t.setPlainText(s[k])
        # подпись показываем такой, какой она сейчас печатается (даже если её ещё не настраивали)
        self.rich["signature_text"].set_lines(signature_lines(s.values))
        self.rich["greeting"].set_lines(s["greeting_rich"] if not richtext.is_empty(s["greeting_rich"])
                                        else _plain_greeting(s["greeting"]))
        for k, tg in self.toggles.items():
            tg.set_value(bool(s[k]))
        self.spin_validity.setValue(int(s["validity_days"]))
        self.ed_output.setText(s["output_dir"])
        self.new_images = {k: None for k in IMAGE_KINDS}
        for kind in IMAGE_KINDS:
            self._show_thumb(kind, s.image_path(kind))
        self._new_pw_hash = s["editor_password_hash"]
        self._update_pw_label()
        self.swatches.set_colors(list(PRESETS.values()))
        self.set_color(s["accent_color"])
        self._fill_backups()
        self.lbl_dir.setText(f"Настройки хранятся в: {s.dir}")

    def collect(self) -> dict:
        vals = {k: w.text().strip() for k, w in self.lines.items()}
        vals.update({k: t.toPlainText().strip() for k, t in self.texts.items()})
        # оформленные поля: если оформление не меняли — храним простой текст (КП выглядит как раньше)
        sig = self.rich["signature_text"].lines()
        vals["signature_text"] = richtext.plain(sig).strip()
        legacy_sig = richtext.from_plain(vals["signature_text"] or auto_signature(self.s.values),
                                         lambda i: dict(b=True, s=11) if i == 1 else dict(c="muted", s=10))
        vals["signature_rich"] = [] if sig == legacy_sig else sig
        gr = self.rich["greeting"].lines()
        vals["greeting"] = richtext.plain(gr).strip()
        vals["greeting_rich"] = [] if gr == _plain_greeting(vals["greeting"]) else gr
        vals.update({k: tg.isChecked() for k, tg in self.toggles.items()})
        vals["validity_days"] = self.spin_validity.value()
        vals["output_dir"] = self.ed_output.text().strip() or DEFAULTS["output_dir"]
        vals["accent_color"] = self.accent
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
            lbl.setPixmap(QPixmap())
            lbl.setText("нет картинки")
            lbl.setProperty("muted", True)
            return
        pm = QPixmap(str(path))
        lbl.setText("")
        lbl.setPixmap(pm.scaled(260, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ------------------------------------------------------------ действия
    def pick_image(self, kind):
        p, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "",
                                           "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not p:
            return
        if QPixmap(p).isNull():
            error(self, "Файл не является изображением.")
            return
        self.new_images[kind] = p
        self._show_thumb(kind, p)

    def remove_image(self, kind):
        self.new_images[kind] = ""
        self._show_thumb(kind, None)

    def set_color(self, c: str):
        self.accent = c
        self.current_swatch.setStyleSheet(f"background: {c}; border: none; border-radius: 6px;")
        self.swatches.select(c)

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.accent), self, "Цвет схемы")
        if c.isValid():
            self.set_color(readable_accent(c.name().upper()))

    def color_from_logo(self):
        logo = self._image_for("logo")
        if not logo:
            info(self, "Сначала загрузите логотип компании.")
            return
        palette = [readable_accent(c) for c in logo_palette(logo)]
        if not palette:
            info(self, "Не удалось определить цвета логотипа.")
            return
        # к готовым схемам добавляем цвета логотипа
        extra = [c for c in PRESETS.values() if c not in palette][:8 - len(palette)]
        self.swatches.set_colors(palette + extra)
        self.set_color(palette[0])

    def pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Папка для готовых КП", self.ed_output.text())
        if d:
            self.ed_output.setText(d)

    def _update_pw_label(self):
        self.pw_label.setText("🔒  Пароль на шаблон установлен" if self._new_pw_hash
                              else "🔓  Пароль не задан — шаблон может менять любой")

    def set_password(self):
        a = ask_password(self, "Новый пароль:")
        if not a:
            return
        b = ask_password(self, "Повторите пароль:")
        if a != b:
            error(self, "Пароли не совпадают.")
            return
        self._new_pw_hash = hash_password(a)
        self._update_pw_label()

    def clear_password(self):
        self._new_pw_hash = ""
        self._update_pw_label()

    def _fill_backups(self):
        self.backup_combo.clear()
        for b in self.s.list_backups():
            try:
                text = datetime.strptime(b.stem[:19], "%Y-%m-%d_%H-%M-%S").strftime("%d.%m.%Y  %H:%M:%S")
            except ValueError:
                text = b.stem
            self.backup_combo.addItem(text, str(b))
        if not self.backup_combo.count():
            self.backup_combo.addItem("Копий пока нет", None)

    def preview(self):
        vals = {**self.s.values, **self.collect()}
        inv, meta = demo_invoice(vals)
        out = Path(tempfile.gettempdir()) / f"КП_предпросмотр_{datetime.now():%H%M%S}.xlsx"
        try:
            build_kp(inv, meta, vals, {k: self._image_for(k) for k in IMAGE_KINDS}, out, self.s.blocks_dir)
        except Exception as e:  # noqa: BLE001
            error(self, f"Ошибка предпросмотра:\n{e}")
            return
        open_path(out, self)

    def _changed(self):
        self.load_values()
        if self.on_saved:
            self.on_saved()

    def save(self):
        vals = self.collect()
        if not vals["company_name"]:
            error(self, "Укажите краткое название компании.")
            return
        if not ask(self, "Изменения применятся ко всем будущим коммерческим предложениям.\n\n"
                         "Текущие настройки будут сохранены в резервную копию. Продолжить?", warning=True):
            return
        self.s.save(vals)
        for kind, new in self.new_images.items():
            if new is not None:
                self.s.set_image(kind, new or None)
        self._changed()
        info(self, "Шаблон сохранён.")

    def import_profile(self):
        if import_settings(self, self.s):
            self._changed()

    def restore_backup(self):
        path = self.backup_combo.currentData()
        if not path:
            return
        if ask(self, f"Восстановить шаблон из копии «{self.backup_combo.currentText().strip()}»?\n"
                     "Текущие настройки тоже будут сохранены в копию."):
            self.s.restore(Path(path))
            self._changed()
            info(self, "Шаблон восстановлен.")

    def reset_defaults(self):
        if ask(self, "Очистить контакты и тексты шаблона и вернуть исходные настройки?\n"
                     "Логотипы и печать останутся.\n\n"
                     "Текущие настройки будут сохранены в резервную копию.", warning=True):
            self.s.reset_to_defaults()
            self._changed()
            info(self, "Шаблон сброшен к исходным настройкам.")
