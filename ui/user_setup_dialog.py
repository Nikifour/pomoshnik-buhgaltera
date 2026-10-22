"""Окно при запуске, пока на этом компьютере не указано имя сотрудника:
имя для статистики, включение синхронизации с Google Таблицей, ссылка на неё и инструкция."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QTextBrowser, QVBoxLayout, QWidget

from core import stats
from core.settings_store import Settings, resource_path
from ui.widgets import Toggle, button, error, hbox, label, run_in_background, warn


def show_instructions(parent):
    """Инструкция «Как подключить свою Google Таблицу» — из docs/google-sheets.md внутри программы."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Как подключить свою Google Таблицу")
    dlg.resize(760, 680)
    lay = QVBoxLayout(dlg)
    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    view.document().setDefaultStyleSheet("a { color: #1F4E79; text-decoration: underline; }")
    path = resource_path("docs/google-sheets.md")
    try:
        view.setMarkdown(path.read_text(encoding="utf-8"))
    except OSError:
        view.setPlainText("Инструкция не найдена в этой сборке программы.")
    view.setStyleSheet("QTextBrowser { background: white; color: #1F2937; padding: 12px; }")
    lay.addWidget(view, 1)
    lay.addLayout(hbox("stretch", button("Закрыть", dlg.accept, primary=True)))
    dlg.exec()


class UserSetupDialog(QDialog):
    def __init__(self, parent, settings: Settings):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Добро пожаловать")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(8)
        lay.addWidget(label("Давайте познакомимся", name="h1"))
        lay.addWidget(label("Под этим именем ваши коммерческие предложения попадают в статистику. "
                            "Имя хранится только на этом компьютере.", muted=True, wrap=True))
        lay.addSpacing(6)

        self.ed_name = QLineEdit(stats.employee(settings))
        self.ed_name.setPlaceholderText("Например: Анна Иванова")
        if not self.ed_name.text():
            self.ed_name.setText(stats.default_employee())
            self.ed_name.selectAll()
        lay.addLayout(hbox(label("Ваше имя", muted=True), self.ed_name))
        lay.addSpacing(14)

        lay.addWidget(label("Статистика в Google Таблице", name="h2"))
        self.tg = Toggle("Отправлять статистику КП в Google Таблицу")
        self.tg.set_value(bool(settings["stats_enabled"]))
        self.tg.toggled.connect(self._sync)
        lay.addWidget(self.tg)

        # таблица уже подключена (например, пришла с файлом настроек) — просто показываем её
        self.connected = QWidget()
        cl = QVBoxLayout(self.connected)
        cl.setContentsMargins(0, 4, 0, 0)
        cl.addLayout(hbox(label("✔  Таблица подключена"), "stretch",
                          button("Открыть таблицу", self._open_sheet)))
        lay.addWidget(self.connected)

        # не подключена — поля для своей таблицы
        self.fields = QWidget()
        form = QFormLayout(self.fields)
        form.setContentsMargins(0, 4, 0, 0)
        form.setVerticalSpacing(8)
        self.ed_sheet = QLineEdit(settings["stats_sheet_url"])
        self.ed_sheet.setPlaceholderText("https://docs.google.com/spreadsheets/d/…/edit")
        self.ed_url = QLineEdit(settings["stats_url"])
        self.ed_url.setPlaceholderText("https://script.google.com/macros/s/…/exec")
        self.ed_token = QLineEdit(settings["stats_token"])
        form.addRow(label("Ссылка на таблицу", muted=True), self.ed_sheet)
        form.addRow(label("Ссылка веб-приложения", muted=True), self.ed_url)
        form.addRow(label("Секретный ключ", muted=True), self.ed_token)
        lay.addWidget(self.fields)
        lay.addWidget(label("Нет таблицы? Её можно подключить за 10 минут — по инструкции. "
                            "Или попросите у руководителя файл настроек.", muted=True, small=True, wrap=True))

        lay.addSpacing(14)
        lay.addLayout(hbox(button("📖  Инструкция", lambda: show_instructions(self)), "stretch",
                           button("Позже", self.reject),
                           button("Сохранить", self.save, primary=True, width=130)))
        self._sync()

    def _configured(self) -> bool:
        return bool(self.s["stats_url"].strip() and self.s["stats_token"].strip())

    def _sync(self, *_):
        on = self.tg.isChecked()
        self.connected.setVisible(on and self._configured())
        self.fields.setVisible(on and not self._configured())
        self.adjustSize()

    def _open_sheet(self):
        sid = stats.sheet_id(self.s["stats_sheet_url"])
        if sid:
            QDesktopServices.openUrl(QUrl(f"https://docs.google.com/spreadsheets/d/{sid}/edit"))
        else:
            warn(self, "Адрес таблицы не указан в настройках. Спросите ссылку у руководителя.")

    def save(self):
        name = self.ed_name.text().strip()
        if not name:
            error(self, "Впишите ваше имя.")
            return
        self.s.set_state("employee_name", name)
        changes = {}
        if bool(self.s["stats_enabled"]) != self.tg.isChecked():
            changes["stats_enabled"] = self.tg.isChecked()
        if self.fields.isVisible():
            url, token = self.ed_url.text().strip(), self.ed_token.text().strip()
            if not url or not token:
                error(self, "Чтобы включить статистику, укажите ссылку веб-приложения и секретный ключ "
                            "(или нажмите «Инструкция»).")
                return
            changes.update(stats_url=url, stats_token=token, stats_sheet_url=self.ed_sheet.text().strip())
        if changes:
            self.s.save(changes)  # с резервной копией, как и любые изменения шаблона
        if self.s["stats_enabled"] and self._configured():
            # проверяем связь и сразу досылаем накопившиеся записи — в фоне, окно не ждёт
            run_in_background(lambda: stats.ping(self.s["stats_url"], self.s["stats_token"]), lambda *_: None)
            stats.flush_in_background(self.s)
        self.accept()
