"""Страница «История»: созданные КП из папки сохранения."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHeaderView, QLineEdit, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from core.settings_store import Settings
from ui.widgets import Card, button, hbox, label, open_path, page_header

MAX_ROWS = 300


class HistoryPage(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.setObjectName("page")
        self.s = settings
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addLayout(hbox(page_header("История", "Коммерческие предложения в папке сохранения"), "stretch",
                            button("⟳  Обновить", self.refresh), button("📁  Открыть папку", self.open_dir)))

        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Поиск по номеру или покупателю…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)

        card = Card()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Коммерческое предложение", "Создано", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setHighlightSections(False)
        self.table.cellDoubleClicked.connect(lambda r, c: self._open_row(r))
        self.empty = label("", muted=True)
        self.empty.setAlignment(Qt.AlignCenter)
        card.body.addWidget(self.empty)
        card.body.addWidget(self.table, 1)
        root.addWidget(card, 1)
        self.files: list[Path] = []

    def open_dir(self):
        d = Path(self.s["output_dir"])
        d.mkdir(parents=True, exist_ok=True)
        open_path(d, self)

    def _open_row(self, r: int):
        if 0 <= r < len(self.files):
            open_path(self.files[r], self)

    def refresh(self):
        d = Path(self.s["output_dir"])
        q = self.search.text().strip().lower()
        files = sorted(d.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []
        self.files = [f for f in files if not f.name.startswith("~$") and (not q or q in f.stem.lower())][:MAX_ROWS]
        self.table.setRowCount(len(self.files))
        for r, f in enumerate(self.files):
            self.table.setItem(r, 0, QTableWidgetItem("📄  " + f.stem))
            created = QTableWidgetItem(f"{datetime.fromtimestamp(f.stat().st_mtime):%d.%m.%Y %H:%M}")
            created.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 1, created)
            cell = QWidget()
            pdf = f.with_suffix(".pdf")
            row = [button("Excel", lambda p=f: open_path(p, self))]
            if pdf.exists():
                row.append(button("PDF", lambda p=pdf: open_path(p, self)))
            cell.setLayout(hbox(*row, spacing=6, margins=(6, 4, 6, 4)))
            self.table.setCellWidget(r, 2, cell)
        self.empty.setText("Ничего не найдено" if q else "Пока пусто — созданные КП появятся здесь")
        self.empty.setVisible(not self.files)
        self.table.setVisible(bool(self.files))
