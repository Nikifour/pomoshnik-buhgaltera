"""Первый запуск: выбор логотипа и подбор цветовой схемы под него (или импорт готовых настроек)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QFrame, QLabel, QVBoxLayout

from core.colors import PRESETS, logo_palette, readable_accent
from ui import theme as T
from ui.transfer_actions import import_settings
from ui.widgets import SwatchRow, button, error, hbox, label


class LogoSetupDialog(QDialog):
    def __init__(self, app_window):
        super().__init__(app_window)
        self.app = app_window
        self.setWindowTitle("Настройка оформления")
        self.setMinimumWidth(640)
        self.logo_path: str | None = None
        self.color = app_window.settings["accent_color"]
        self.imported = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(8)
        lay.addWidget(label("Добро пожаловать!", name="h1"))
        lay.addWidget(label("Выберите логотип компании — программа подберёт под него цвета интерфейса "
                            "и коммерческих предложений.", muted=True, wrap=True))
        lay.addSpacing(8)

        self.preview = QFrame()
        self.preview.setObjectName("preview")
        self.preview.setFixedHeight(150)
        pl = QVBoxLayout(self.preview)
        self.logo_label = QLabel("Логотип не выбран")
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setProperty("muted", True)
        pl.addWidget(self.logo_label)
        lay.addWidget(self.preview)
        lay.addSpacing(6)

        lay.addLayout(hbox(button("🖼  Выбрать логотип…", self.pick_logo, primary=True), label("или", muted=True),
                           button("⬇  Импорт настроек из файла…", self.import_profile), "stretch"))
        lay.addSpacing(10)
        lay.addWidget(label("Цветовая схема", name="h2"))
        self.swatches = SwatchRow(list(PRESETS.values()), selected=self.color)
        self.swatches.picked.connect(self.set_color)
        lay.addWidget(self.swatches)
        self.hint = label("Готовые схемы. После выбора логотипа здесь появятся его цвета.", muted=True, small=True)
        lay.addWidget(self.hint)
        lay.addSpacing(16)
        lay.addLayout(hbox(label("Всё это можно изменить позже\nв разделе «Шаблон КП»", muted=True, small=True),
                           "stretch", button("Пропустить", self.reject),
                           button("Применить", self.apply, primary=True, width=130)))

    def pick_logo(self):
        p, _ = QFileDialog.getOpenFileName(self, "Логотип компании", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if not p:
            return
        pm = QPixmap(p)
        if pm.isNull():
            error(self, "Не удалось открыть изображение.")
            return
        self.logo_path = p
        self.logo_label.setPixmap(pm.scaled(440, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        colors = [readable_accent(c) for c in logo_palette(p)] or list(PRESETS.values())
        self.swatches.set_colors(colors, selected=colors[0])
        self.set_color(colors[0])
        self.hint.setText("Цвета из логотипа — первый подобран автоматически, можно выбрать другой.")

    def set_color(self, color: str):
        """Сразу показываем схему на всей программе (сохраняется только по «Применить»)."""
        self.color = color
        T.apply_accent(color)
        T.apply()

    def apply(self):
        s = self.app.settings
        if self.logo_path:
            s.set_image("logo", self.logo_path)
        s.save({"accent_color": self.color})
        s.set_state("logo_setup_done", True)
        self.accept()

    def import_profile(self):
        """Сотруднику прислали файл .pbsettings — сразу получает готовый шаблон компании."""
        if import_settings(self, self.app.settings):
            self.imported = True
            self.accept()

    def reject(self):
        """«Пропустить» или закрытие окна: возвращаем сохранённую схему и больше не спрашиваем."""
        self.app.settings.set_state("logo_setup_done", True)
        T.apply_accent(self.app.settings["accent_color"])
        T.apply()
        super().reject()
