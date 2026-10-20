"""Главное окно: боковое меню, страницы, баннер и окно обновления."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget,
                               QVBoxLayout, QWidget)

from core import updater
from core.settings_store import APP_NAME, Settings, hash_password, resource_path
from ui import theme as T
from ui.page_history import HistoryPage
from ui.page_designer import DesignerPage
from ui.page_new import NewKPPage
from ui.page_template import TemplatePage
from ui.setup_dialog import LogoSetupDialog
from ui.transfer_actions import import_settings
from ui.widgets import ask_cancel, ask_password, button, error, hbox, info, label, run_in_background, warn
from version import __version__

APPEARANCE = {"Светлая": "light", "Тёмная": "dark", "Как в системе": "system"}
# Рабочее меню — то, чем пользуются каждый день. Настройки вынесены отдельно,
# чтобы шаблон и макет нельзя было случайно поменять в процессе работы.
NAV_WORK = [("new", "＋   Новое КП"), ("history", "🕘   История")]
NAV_SETTINGS = [("template", "🎨   Шаблон КП"), ("designer", "🧩   Конструктор")]
SETTINGS_PAGES = tuple(k for k, _ in NAV_SETTINGS)


class MainWindow(QMainWindow):
    def __init__(self, import_file: str | None = None):
        super().__init__()
        self.settings = Settings()
        T.set_mode(self.settings.get_state("appearance", "light"))
        T.apply_accent(self.settings["accent_color"])
        T.apply()
        QGuiApplication.styleHints().colorSchemeChanged.connect(lambda *_: T.apply())

        self.setWindowTitle(APP_NAME)
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1200, 800)
        self.setMinimumSize(1000, 680)
        self.unlocked = False  # пароль на шаблон введён в этом сеансе
        self.release: updater.Release | None = None

        central = QWidget()
        central.setObjectName("content")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())

        right = QVBoxLayout()
        right.setContentsMargins(32, 20, 32, 24)
        right.setSpacing(14)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.hide()
        right.addWidget(self.banner)
        self.stack = QStackedWidget()
        self.pages = {
            "new": NewKPPage(self.settings, on_created=lambda: self.pages["history"].refresh()),
            "history": HistoryPage(self.settings),
            "template": TemplatePage(self.settings, on_saved=self._on_template_saved),
            "designer": DesignerPage(self.settings, on_saved=self._on_template_saved),
        }
        for p in self.pages.values():
            self.stack.addWidget(p)
        right.addWidget(self.stack, 1)
        row.addLayout(right, 1)
        self.setCentralWidget(central)

        self.current = None
        self.show_page("new")
        QTimer.singleShot(1500, lambda: self.check_updates(silent=True))
        if import_file:
            QTimer.singleShot(400, lambda: self._import_from_file(import_file))
        elif not self.settings.image_path("logo") and not self.settings.get_state("logo_setup_done"):
            QTimer.singleShot(400, self.run_setup_wizard)

    # ------------------------------------------------------------ меню
    def _build_sidebar(self) -> QWidget:
        sb = QFrame()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(240)
        lay = QVBoxLayout(sb)
        lay.setContentsMargins(14, 24, 14, 20)
        lay.setSpacing(4)

        logo = QLabel()
        icon = resource_path("assets/icon.ico")
        if icon.exists():
            logo.setPixmap(QIcon(str(icon)).pixmap(QSize(46, 46)))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = label("Помощник\nБухгалтера")
        t.setStyleSheet("font-size: 12pt; font-weight: 700;")
        titles.addWidget(t)
        self.lbl_company = label(self.settings["company_name"], muted=True, small=True)
        titles.addWidget(self.lbl_company)
        head = hbox(logo, spacing=12, margins=(6, 0, 0, 0))
        head.addLayout(titles, 1)
        lay.addLayout(head)
        lay.addSpacing(26)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}

        def nav_button(key, text):
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda checked=False, k=key: self.show_page(k))
            self.nav.addButton(b)
            self.nav_buttons[key] = b
            return b

        # --- рабочий режим: только основные кнопки
        self.work_box = QWidget()
        wl = QVBoxLayout(self.work_box)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(4)
        for key, text in NAV_WORK:
            wl.addWidget(nav_button(key, text))
        lay.addWidget(self.work_box)

        # --- режим настроек
        self.settings_box = QWidget()
        sl = QVBoxLayout(self.settings_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)
        back = QPushButton("←   Вернуться к работе")
        back.setObjectName("nav")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(lambda: self.exit_settings())
        sl.addWidget(back)
        sl.addSpacing(14)
        sl.addWidget(label("НАСТРОЙКИ", muted=True, small=True))
        for key, text in NAV_SETTINGS:
            sl.addWidget(nav_button(key, text))
        sl.addSpacing(18)
        sl.addWidget(label("Оформление программы", muted=True, small=True))
        self.appearance = QComboBox()
        self.appearance.addItems(list(APPEARANCE))
        current = self.settings.get_state("appearance", "light")
        self.appearance.setCurrentText(next(k for k, v in APPEARANCE.items() if v == current))
        self.appearance.currentTextChanged.connect(self._set_appearance)
        sl.addWidget(self.appearance)
        sl.addSpacing(10)
        upd = QPushButton("Проверить обновления")
        upd.setObjectName("sideButton")
        upd.setCursor(Qt.PointingHandCursor)
        upd.clicked.connect(lambda: self.check_updates(silent=False))
        sl.addWidget(upd)
        self.settings_box.hide()
        lay.addWidget(self.settings_box)
        lay.addStretch(1)

        # --- внизу: вход в настройки (неброско) и версия
        self.btn_settings = QPushButton("⚙   Настройки")
        self.btn_settings.setObjectName("sideButton")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Шаблон КП, конструктор, оформление, обновления")
        self.btn_settings.clicked.connect(lambda: self.enter_settings())
        lay.addWidget(self.btn_settings)
        lay.addSpacing(6)
        lay.addWidget(label(f"Версия {__version__}", muted=True, small=True))
        return sb

    # ------------------------------------------------------------ режимы: работа / настройки
    def in_settings(self) -> bool:
        return self.settings_box.isVisible() or self.current in SETTINGS_PAGES

    def enter_settings(self, page: str = "template") -> bool:
        if not self._unlock_template():
            return False
        self.work_box.hide()
        self.btn_settings.hide()
        self.settings_box.show()
        self._switch(page)
        return True

    def exit_settings(self):
        if not self._leave_designer():
            return
        self.unlocked = False  # пароль спросим снова при следующем входе в настройки
        self.settings_box.hide()
        self.work_box.show()
        self.btn_settings.show()
        self._switch("new")

    def show_page(self, key: str):
        """Открыть страницу; страницы настроек открываются только через режим настроек."""
        if key == self.current:
            return
        if key in SETTINGS_PAGES and not self.settings_box.isVisible():
            if not self.enter_settings(key):
                self.nav_buttons[self.current or "new"].setChecked(True)
            return
        if not self._leave_designer():
            self.nav_buttons[self.current or "new"].setChecked(True)
            return
        self._switch(key)

    def _switch(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.nav_buttons[key].setChecked(True)
        self.current = key
        page = self.pages[key]
        if hasattr(page, "refresh"):
            page.refresh()

    def _leave_designer(self) -> bool:
        """Уходим из конструктора с несохранённым макетом — спрашиваем. False — остаться."""
        d = self.pages["designer"]
        if self.current != "designer" or not d.has_unsaved():
            return True
        answer = ask_cancel(self, "В конструкторе есть несохранённые изменения макета.\n\nСохранить их?")
        if answer is None:
            return False
        if answer:
            return d.save()
        d.load_layout()
        return True

    def closeEvent(self, e):  # noqa: N802
        if not self._leave_designer():
            e.ignore()
            return
        self.pages["designer"].shutdown()
        super().closeEvent(e)

    def _unlock_template(self) -> bool:
        pw_hash = self.settings["editor_password_hash"]
        if not pw_hash or self.unlocked:
            return True
        pw = ask_password(self, "Пароль для изменения шаблона:")
        if pw is None:
            return False
        if hash_password(pw) != pw_hash:
            error(self, "Неверный пароль.")
            return False
        self.unlocked = True
        return True

    def _on_template_saved(self):
        """После сохранения/импорта/сброса шаблона: цвета применяются сразу, без перезапуска."""
        T.apply_accent(self.settings["accent_color"])
        T.apply()
        self.lbl_company.setText(self.settings["company_name"])
        self.pages["new"].refresh()
        self.pages["template"].load_values()

    def _set_appearance(self, text: str):
        mode = APPEARANCE[text]
        self.settings.set_state("appearance", mode)
        T.set_mode(mode)
        T.apply()

    # ------------------------------------------------------------ первый запуск
    def run_setup_wizard(self):
        dlg = LogoSetupDialog(self)
        accepted = dlg.exec() == QDialog.Accepted
        self.pages["template"].load_values()
        self._on_template_saved()
        if dlg.imported:
            self.show_page("new")
        elif accepted and not self.settings["company_name"]:
            self.show_page("template")
            info(self, "Теперь заполните данные компании на вкладке «Компания» и нажмите «Сохранить шаблон».")

    def _import_from_file(self, path: str):
        if import_settings(self, self.settings, path):
            self.pages["template"].load_values()
            self._on_template_saved()
            self.show_page("new")
        elif not self.settings.image_path("logo") and not self.settings.get_state("logo_setup_done"):
            self.run_setup_wizard()

    # ------------------------------------------------------------ обновления
    def check_updates(self, silent: bool):
        run_in_background(updater.check_for_update, lambda rel, err: self._update_checked(rel, err, silent))

    def _update_checked(self, rel, err, silent):
        if err:
            if not silent:
                warn(self, str(err))
            return
        if not rel:
            if not silent:
                info(self, f"У вас последняя версия ({__version__}).")
            return
        self.release = rel
        self._show_banner(rel)
        if not silent:
            UpdateDialog(self, rel).exec()

    def _show_banner(self, rel):
        if self.banner.layout():
            QWidget().setLayout(self.banner.layout())  # убрать старую раскладку
        lay = hbox(label(f"⬆  Доступна новая версия {rel.version}", name="h2"), "stretch",
                   button("Позже", self.banner.hide),
                   button("Обновить", lambda: UpdateDialog(self, rel).exec(), primary=True),
                   margins=(16, 8, 10, 8))
        self.banner.setLayout(lay)
        self.banner.show()


class UpdateDialog(QDialog):
    def __init__(self, app_window: MainWindow, rel: updater.Release):
        super().__init__(app_window)
        self.rel = rel
        self.setWindowTitle("Обновление")
        self.setMinimumSize(560, 420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(8)
        lay.addWidget(label(f"Новая версия {rel.version}", name="h1"))
        lay.addWidget(label(f"Сейчас установлена {__version__}", muted=True))
        notes = QPlainTextEdit(rel.notes or "Исправления и улучшения.")
        notes.setReadOnly(True)
        lay.addWidget(notes, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = label("Программа перезапустится автоматически. Ваши настройки сохранятся.", muted=True,
                            small=True, wrap=True)
        lay.addWidget(self.status)
        self.btn_later = button("Позже", self.reject)
        self.btn = button("Обновить сейчас", self.start, primary=True, width=170)
        lay.addLayout(hbox("stretch", self.btn_later, self.btn))

    def start(self):
        if not updater.is_frozen():
            info(self, "Обновление устанавливается только в собранной программе (.exe).\n"
                       "Сейчас программа запущена из исходного кода.")
            return
        self.btn.setEnabled(False)
        self.btn.setText("Загрузка…")
        self.btn_later.setEnabled(False)
        self.progress.show()
        run_in_background(lambda progress: updater.download(self.rel, progress=progress), self._downloaded,
                          on_progress=lambda p: self.progress.setValue(int(p * 1000)))

    def _downloaded(self, path, err):
        if err:
            self._failed(err)
            return
        self.status.setText("Устанавливаю и перезапускаю…")
        try:
            updater.install_and_restart(path)
        except Exception as e:  # noqa: BLE001
            self._failed(e)
            return
        QTimer.singleShot(300, QApplication.quit)

    def _failed(self, e):
        self.btn.setEnabled(True)
        self.btn.setText("Повторить")
        self.btn_later.setEnabled(True)
        self.status.setText(str(e))
        self.status.setStyleSheet(f"color: {T.colors()['danger']};")
