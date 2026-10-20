"""Поле ввода с оформлением: жирный, курсив, цвет, размер — как в Word, без разметки."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QSpinBox, QTextEdit, QToolButton, QVBoxLayout, QWidget

from core.icons import whatsapp_icon
from core.richtext import COLORS, SIZE_RANGE, normalize, run
from ui import theme as T

COLOR_NAMES = {"text": "Обычный", "muted": "Серый", "accent": "Фирменный"}
PROP_COLOR = QTextCharFormat.UserProperty + 1  # код цвета (text/muted/accent) хранится в самом тексте


def _hex(code: str) -> str:
    c = T.colors()
    return {"text": "#1F2937", "muted": "#6B7280", "accent": c["brand"]}[code]


class RichTextEdit(QWidget):
    changed = Signal()

    def __init__(self, height=110, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(4)
        self.btn_b = self._tool("Ж", "Жирный (Ctrl+B)", bold=True)
        self.btn_i = self._tool("К", "Курсив (Ctrl+I)", italic=True)
        self.btn_b.toggled.connect(lambda on: self._apply(b=on))
        self.btn_i.toggled.connect(lambda on: self._apply(i=on))
        self.color = QComboBox()
        for code in COLORS:
            self.color.addItem(COLOR_NAMES[code], code)
        self.color.setToolTip("Цвет текста")
        self.color.activated.connect(lambda idx: self._apply(c=self.color.itemData(idx)))
        self.size = QSpinBox()
        self.size.setRange(*SIZE_RANGE)
        self.size.setSuffix(" pt")
        self.size.setToolTip("Размер шрифта")
        self.size.setFixedWidth(84)
        self.size.valueChanged.connect(lambda v: self._apply(s=v) if not self._syncing else None)
        self.btn_wa = QToolButton()
        self.btn_wa.setText(" WhatsApp")
        self.btn_wa.setIcon(QIcon(str(whatsapp_icon())))
        self.btn_wa.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.btn_wa.setToolTip("Вставить значок WhatsApp в место курсора — например, после номера телефона.\n"
                               "В тексте он выглядит как {WhatsApp}, в КП — как зелёный значок.")
        self.btn_wa.setFixedHeight(30)
        self.btn_wa.setCursor(Qt.PointingHandCursor)
        self.btn_wa.clicked.connect(self._insert_wa)
        for w in (self.btn_b, self.btn_i, self.color, self.size, self.btn_wa):
            bar.addWidget(w)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)  # вставка из буфера — простым текстом, оформление задаём сами
        self.edit.setFixedHeight(height)
        # белый «лист», как в КП, — чтобы цвета выглядели как на бумаге в любой теме
        self.edit.setStyleSheet("QTextEdit { background: white; color: #1F2937; }")
        self.edit.cursorPositionChanged.connect(self._sync_toolbar)
        self.edit.textChanged.connect(self.changed.emit)
        lay.addWidget(self.edit)
        self._syncing = False

    def _tool(self, text, tip, bold=False, italic=False) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(True)
        b.setFixedSize(32, 30)
        f = b.font()
        f.setBold(bold)
        f.setItalic(italic)
        b.setFont(f)
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _insert_wa(self):
        cur = self.edit.textCursor()
        before = cur.block().text()[:cur.positionInBlock()]
        cur.insertText(("" if not before or before.endswith(" ") else " ") + "{WhatsApp}")
        self.edit.setFocus()

    # ---------------------------------------------------------------- оформление выделения
    def _apply(self, b=None, i=None, c=None, s=None):
        if self._syncing:
            return
        fmt = QTextCharFormat()
        if b is not None:
            fmt.setFontWeight(QFont.Bold if b else QFont.Normal)
        if i is not None:
            fmt.setFontItalic(i)
        if c is not None:
            fmt.setForeground(QColor(_hex(c)))
            fmt.setProperty(PROP_COLOR, c)
        if s is not None:
            fmt.setFontPointSize(s)
        cur = self.edit.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.WordUnderCursor)
        cur.mergeCharFormat(fmt)
        self.edit.mergeCurrentCharFormat(fmt)  # и для текста, который будут печатать дальше
        self.edit.setFocus()
        self.changed.emit()

    def _sync_toolbar(self):
        fmt = self.edit.currentCharFormat()
        self._syncing = True
        self.btn_b.setChecked(fmt.fontWeight() >= QFont.Bold)
        self.btn_i.setChecked(fmt.fontItalic())
        code = fmt.property(PROP_COLOR) or "text"
        self.color.setCurrentIndex(max(0, self.color.findData(code)))
        self.size.setValue(int(fmt.fontPointSize() or 10))
        self._syncing = False

    # ---------------------------------------------------------------- данные
    def set_lines(self, lines):
        self.edit.blockSignals(True)
        self.edit.clear()
        cur = self.edit.textCursor()
        for n, line in enumerate(normalize(lines)):
            if n:
                cur.insertBlock()
            for r in line:
                fmt = QTextCharFormat()
                fmt.setFontWeight(QFont.Bold if r["b"] else QFont.Normal)
                fmt.setFontItalic(r["i"])
                fmt.setForeground(QColor(_hex(r["c"])))
                fmt.setProperty(PROP_COLOR, r["c"])
                fmt.setFontPointSize(r["s"])
                cur.insertText(r["t"], fmt)
        self.edit.moveCursor(QTextCursor.Start)
        self.edit.blockSignals(False)
        self._sync_toolbar()

    def lines(self) -> list[list[dict]]:
        out = []
        block = self.edit.document().begin()
        while block.isValid():
            runs = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.text():
                    f = frag.charFormat()
                    runs.append(run(frag.text(), f.fontWeight() >= QFont.Bold, f.fontItalic(),
                                    f.property(PROP_COLOR) or "text", int(f.fontPointSize() or 10)))
                it += 1
            out.append(runs)
            block = block.next()
        while out and not out[-1]:
            out.pop()  # пустые строки в конце не нужны
        return out
