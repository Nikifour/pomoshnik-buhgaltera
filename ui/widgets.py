"""Общие элементы интерфейса на Qt."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from PySide6.QtCore import (Property, QEasingCurve, QObject, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from core.settings_store import APP_NAME
from ui import theme as T


# ---------------------------------------------------------------- простые элементы
def label(text: str = "", *, name: str | None = None, muted=False, small=False, wrap=False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if muted:
        lb.setProperty("muted", True)
    if small:
        lb.setProperty("small", True)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, slot: Callable | None = None, *, primary=False, large=False,
           width: int | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if primary:
        b.setProperty("kind", "primary")
    if large:
        b.setProperty("size", "large")
    if width:
        b.setMinimumWidth(width)
    if slot:
        b.clicked.connect(lambda checked=False: slot())
    return b


def hbox(*widgets, spacing=8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    """Горизонтальный ряд: виджеты, "stretch" — растяжка, число — отступ."""
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if isinstance(w, str) and w == "stretch":
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
    return lay


def repolish(w: QWidget):
    """После смены динамического свойства (setProperty) Qt нужно перечитать стиль."""
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


class Card(QFrame):
    """Карточка с необязательным заголовком; содержимое добавляется в card.body."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 18)
        outer.setSpacing(4)
        self.title_label = label(title, name="h2")
        if title:
            outer.addWidget(self.title_label)
        if subtitle:
            outer.addWidget(label(subtitle, muted=True, small=True, wrap=True))
        if title or subtitle:
            outer.addSpacing(8)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)


def page_header(title: str, subtitle: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(label(title, name="h1"))
    if subtitle:
        lay.addWidget(label(subtitle, muted=True))
    return w


def scroll_area(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa


# ---------------------------------------------------------------- переключатель
class Toggle(QAbstractButton):
    """Переключатель в стиле Windows 11 с плавной анимацией."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(text)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_value(self, on: bool):
        """Установить без анимации (при загрузке настроек)."""
        self.blockSignals(True)
        self.setChecked(bool(on))
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def sizeHint(self):  # noqa: N802
        w = 46 + (self.fontMetrics().horizontalAdvance(self.text()) + 12 if self.text() else 0)
        return QSize(w, 28)

    def paintEvent(self, _):  # noqa: N802
        c = T.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, (self.height() - 22) / 2, 42, 22)
        on = QColor(c["brand"])
        off = QColor("#4B4D55" if T.is_dark() else "#C9CDD3")
        t = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * t),
                     int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(track, 11, 11)
        p.setBrush(QColor("white"))
        x = track.left() + 3 + t * (track.width() - 22)
        p.drawEllipse(QRectF(x, track.top() + 3, 16, 16))
        if self.text():
            p.setPen(QColor(c["text"]))
            p.drawText(QRectF(54, 0, self.width() - 54, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


# ---------------------------------------------------------------- выбор цвета
class Swatch(QAbstractButton):
    """Цветной кружок; выбранный обведён кольцом."""

    def __init__(self, color: str, size: int):
        super().__init__()
        self.color = color
        self.selected = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(color.upper())

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self.selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(T.colors()["text"]))
            p.drawEllipse(r)
            r = r.adjusted(3, 3, -3, -3)
            p.setBrush(QColor(T.colors()["card"]))
            p.drawEllipse(r)
            r = r.adjusted(2, 2, -2, -2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(r)
        p.end()


class SwatchRow(QWidget):
    picked = Signal(str)

    def __init__(self, colors: list[str], selected: str | None = None, size=34, parent=None):
        super().__init__(parent)
        self.size = size
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(8)
        self.buttons: dict[str, Swatch] = {}
        self.set_colors(colors, selected)

    def set_colors(self, colors: list[str], selected: str | None = None):
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.buttons = {}
        for col in colors:
            b = Swatch(col, self.size)
            b.clicked.connect(lambda checked=False, c=col: (self.select(c), self.picked.emit(c)))
            self.lay.addWidget(b)
            self.buttons[col.upper()] = b
        self.lay.addStretch(1)
        self.select(selected)

    def select(self, color: str | None):
        for c, b in self.buttons.items():
            b.selected = bool(color) and c == color.upper()
            b.update()


# ---------------------------------------------------------------- диалоги
def _box(parent, icon, text, buttons, default=None):
    box = QMessageBox(icon, APP_NAME, text, buttons, parent)
    if default:
        box.setDefaultButton(default)
    return box.exec()


def info(parent, text: str):
    _box(parent, QMessageBox.Information, text, QMessageBox.Ok)


def warn(parent, text: str):
    _box(parent, QMessageBox.Warning, text, QMessageBox.Ok)


def error(parent, text: str):
    _box(parent, QMessageBox.Critical, text, QMessageBox.Ok)


def ask(parent, text: str, warning=False) -> bool:
    icon = QMessageBox.Warning if warning else QMessageBox.Question
    return _box(parent, icon, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes


def ask_cancel(parent, text: str) -> bool | None:
    """Да / Нет / Отмена → True / False / None."""
    r = _box(parent, QMessageBox.Question, text, QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
    return None if r == QMessageBox.Cancel else r == QMessageBox.Yes


def ask_password(parent, prompt: str) -> str | None:
    text, ok = QInputDialog.getText(parent, APP_NAME, prompt, QLineEdit.Password)
    return text if ok else None


def open_path(p: Path, parent=None):
    try:
        os.startfile(str(p))  # noqa: S606 — Windows
    except OSError as e:
        error(parent, f"Не удалось открыть:\n{p}\n\n{e}")


# ---------------------------------------------------------------- фоновые задачи
class _Bridge(QObject):
    done = Signal(object, object)
    progress = Signal(float)


_running: set = set()


def run_in_background(fn: Callable, on_done: Callable, on_progress: Callable | None = None):
    """Выполнить fn в отдельном потоке; результат приходит в интерфейс через сигнал Qt.

    on_done(результат, ошибка). Если передан on_progress, fn получает функцию progress(0..1).
    """
    bridge = _Bridge()
    _running.add(bridge)

    def finished(res, err):
        _running.discard(bridge)
        on_done(res, err)

    bridge.done.connect(finished)
    if on_progress:
        bridge.progress.connect(on_progress)

    def worker():
        try:
            res = fn(bridge.progress.emit) if on_progress else fn()
            bridge.done.emit(res, None)
        except Exception as e:  # noqa: BLE001
            bridge.done.emit(None, e)

    threading.Thread(target=worker, daemon=True).start()
