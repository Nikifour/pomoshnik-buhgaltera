"""Страница «Конструктор»: макет КП из блоков с живым предпросмотром."""
from __future__ import annotations

import copy
import json

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QSizePolicy,
                               QSpinBox, QVBoxLayout, QWidget)

from core.kp_builder import demo_invoice
from core.layout import BLOCKS, CUSTOM_TYPES, block_title, default_layout, make_block, normalize
from core.settings_store import Settings
from ui.preview import PreviewWorker
from ui.widgets import Card, Toggle, ask, button, error, hbox, info, label, open_path, page_header, scroll_area

ROLE_ID = Qt.UserRole


class DesignerPage(QWidget):
    def __init__(self, settings: Settings, on_saved=None):
        super().__init__()
        self.setObjectName("page")
        self.s = settings
        self.on_saved = on_saved
        self.layout_data: list[dict] = []
        self.saved_json = ""
        self.worker: PreviewWorker | None = None
        self.page_pixmaps: list[QPixmap] = []
        self._building = False

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.update_preview)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addWidget(page_header("Конструктор КП",
                                   "Перетаскивайте блоки мышкой, скрывайте ненужные и добавляйте свои — "
                                   "справа сразу видно, как выглядит КП"))

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # --- слева: блоки + настройки
        left = QVBoxLayout()
        left.setSpacing(12)
        blocks = Card("Блоки", "Галочка — показывать блок в КП")
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSpacing(1)
        self.list.setMinimumHeight(240)
        self.list.model().rowsMoved.connect(self._order_changed)
        self.list.itemChanged.connect(self._item_changed)
        self.list.currentRowChanged.connect(lambda _: self._show_props())
        blocks.body.addWidget(self.list, 1)

        self.btn_add = button("＋  Добавить блок", primary=True)
        menu = QMenu(self.btn_add)
        for t in CUSTOM_TYPES:
            menu.addAction(f"{BLOCKS[t]['icon']}  {BLOCKS[t]['title']}", lambda t=t: self.add_block(t))
        self.btn_add.setMenu(menu)
        self.btn_up = button("↑", lambda: self.move(-1))
        self.btn_down = button("↓", lambda: self.move(1))
        self.btn_del = button("🗑", self.delete_block)
        for b, tip in ((self.btn_up, "Выше"), (self.btn_down, "Ниже"), (self.btn_del, "Удалить свой блок")):
            b.setToolTip(tip)
            b.setFixedWidth(44)
        blocks.body.addLayout(hbox(self.btn_add, "stretch", self.btn_up, self.btn_down, self.btn_del))
        left.addWidget(blocks, 3)

        self.props_card = Card("Настройки блока")
        self.props_scroll = scroll_area(QWidget())
        self.props_card.body.addWidget(self.props_scroll, 1)
        left.addWidget(self.props_card, 4)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(380)
        body.addWidget(left_w)

        # --- справа: предпросмотр
        prev = Card()
        self.status = label("", muted=True, small=True)
        prev.body.addLayout(hbox(label("Предпросмотр", name="h2"), self.status, "stretch",
                                 button("Открыть в Excel", self.open_preview_excel)))
        self.pages_host = QWidget()
        self.pages_layout = QVBoxLayout(self.pages_host)
        self.pages_layout.setContentsMargins(0, 0, 0, 0)
        self.pages_layout.setSpacing(12)
        self.pages_scroll = scroll_area(self.pages_host)
        prev.body.addWidget(self.pages_scroll, 1)
        body.addWidget(prev, 1)

        root.addLayout(hbox(button("Сбросить к стандартному", self.reset_layout), "stretch",
                            button("Отменить изменения", self.load_layout),
                            button("Сохранить макет", self.save, primary=True, width=170)))
        self.load_layout()

    # ------------------------------------------------------------ данные
    def load_layout(self):
        self.layout_data = normalize(copy.deepcopy(self.s.values.get("layout")), self.s.values)
        self.saved_json = json.dumps(self.layout_data, sort_keys=True)
        self._fill_list(select=0)
        self.schedule_preview()

    def has_unsaved(self) -> bool:
        return json.dumps(self.layout_data, sort_keys=True) != self.saved_json

    def _block(self, bid: str) -> dict:
        return next(b for b in self.layout_data if b["id"] == bid)

    def _current(self) -> dict | None:
        item = self.list.currentItem()
        return self._block(item.data(ROLE_ID)) if item else None

    def _fill_list(self, select: int | None = None):
        self._building = True
        row = self.list.currentRow() if select is None else select
        self.list.clear()
        for b in self.layout_data:
            item = QListWidgetItem(block_title(b))
            item.setData(ROLE_ID, b["id"])
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
            if not BLOCKS[b["type"]].get("required"):
                flags |= Qt.ItemIsUserCheckable
                item.setCheckState(Qt.Checked if b["visible"] else Qt.Unchecked)
            item.setFlags(flags)
            item.setSizeHint(QSize(0, 34))
            if not BLOCKS[b["type"]]["standard"]:
                item.setToolTip("Свой блок — можно удалить")
            self.list.addItem(item)
        self._building = False
        self.list.setCurrentRow(max(0, min(row, self.list.count() - 1)))
        self._show_props()

    def _order_changed(self, *_):
        order = [self.list.item(i).data(ROLE_ID) for i in range(self.list.count())]
        self.layout_data = [self._block(bid) for bid in order]
        self.schedule_preview()

    def _item_changed(self, item: QListWidgetItem):
        if self._building:
            return
        b = self._block(item.data(ROLE_ID))
        visible = item.checkState() == Qt.Checked
        if b["visible"] != visible:
            b["visible"] = visible
            self.schedule_preview()

    # ------------------------------------------------------------ действия со списком
    def add_block(self, btype: str):
        b = make_block(btype)
        row = self.list.currentRow() + 1 if self.list.currentRow() >= 0 else len(self.layout_data)
        self.layout_data.insert(row, b)
        self._fill_list(select=row)
        self.schedule_preview()

    def move(self, step: int):
        row = self.list.currentRow()
        new = row + step
        if row < 0 or not 0 <= new < len(self.layout_data):
            return
        self.layout_data[row], self.layout_data[new] = self.layout_data[new], self.layout_data[row]
        self._fill_list(select=new)
        self.schedule_preview()

    def delete_block(self):
        b = self._current()
        if not b:
            return
        if BLOCKS[b["type"]]["standard"]:
            info(self, "Стандартный блок нельзя удалить — снимите галочку, чтобы скрыть его.")
            return
        row = self.list.currentRow()
        self.layout_data.remove(b)
        self._fill_list(select=row)
        self.schedule_preview()

    # ------------------------------------------------------------ настройки блока
    def _show_props(self):
        # панель настроек пересоздаётся целиком: старый контейнер со всеми полями удаляется
        host = QWidget()
        self.props_layout = QVBoxLayout(host)
        self.props_layout.setContentsMargins(0, 0, 6, 0)
        old = self.props_scroll.takeWidget()
        self.props_scroll.setWidget(host)
        if old:
            old.deleteLater()
        b = self._current()
        self.btn_del.setEnabled(bool(b) and not BLOCKS[b["type"]]["standard"])
        if not b:
            return
        spec = BLOCKS[b["type"]]
        self.props_card.title_label.setText(f"Настройки: {spec['title']}")
        if spec.get("note"):
            self.props_layout.addWidget(label(spec["note"], muted=True, small=True, wrap=True))
        if not spec["props"]:
            self.props_layout.addWidget(label("У этого блока нет своих настроек.", muted=True, small=True))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, (kind, _default, title, extra) in spec["props"].items():
            w = self._editor(b, key, kind, extra)
            if kind in ("bool",):
                form.addRow(w)
            elif kind in ("multiline", "image"):
                form.addRow(label(title, muted=True))
                form.addRow(w)
            else:
                form.addRow(label(title, muted=True), w)
        self.props_layout.addLayout(form)
        self.props_layout.addStretch(1)

    def _set(self, b: dict, key: str, value, refresh_title=False):
        b["props"][key] = value
        if refresh_title:
            self.list.currentItem().setText(block_title(b))
        self.schedule_preview()

    def _editor(self, b, key, kind, extra) -> QWidget:
        val = b["props"][key]
        if kind == "text":
            w = QLineEdit(val)
            w.textChanged.connect(lambda v: self._set(b, key, v))
        elif kind == "multiline":
            w = QPlainTextEdit(val)
            w.setFixedHeight(96)
            w.textChanged.connect(lambda: self._set(b, key, w.toPlainText(), refresh_title=(b["type"] == "text")))
        elif kind == "int":
            w = QSpinBox()
            w.setRange(*extra)
            w.setValue(val)
            w.setFixedWidth(110)
            w.valueChanged.connect(lambda v: self._set(b, key, v))
        elif kind == "bool":
            w = Toggle(BLOCKS[b["type"]]["props"][key][2])
            w.set_value(val)
            w.toggled.connect(lambda v: self._set(b, key, v))
        elif kind == "choice":
            w = QComboBox()
            for code, text in extra.items():
                w.addItem(text, code)
            w.setCurrentIndex(max(0, list(extra).index(val) if val in extra else 0))
            w.currentIndexChanged.connect(lambda i: self._set(b, key, w.itemData(i)))
        else:  # image
            w = self._image_editor(b, key)
        return w

    def _image_editor(self, b, key) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        thumb = QLabel()
        thumb.setFixedSize(150, 60)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setProperty("muted", True)

        def show():
            name = b["props"][key]
            path = self.s.blocks_dir / name if name else None
            if path and path.exists():
                thumb.setPixmap(QPixmap(str(path)).scaled(150, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setPixmap(QPixmap())
                thumb.setText("нет картинки")

        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Выберите картинку", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
            if not p:
                return
            if QPixmap(p).isNull():
                error(self, "Файл не является изображением.")
                return
            self._set(b, key, self.s.add_block_image(p))
            show()

        def clear():
            self._set(b, key, "")
            show()

        show()
        lay.addWidget(thumb)
        col = QVBoxLayout()
        col.addWidget(button("Выбрать…", pick))
        col.addWidget(button("Убрать", clear))
        lay.addLayout(col)
        lay.addStretch(1)
        return box

    # ------------------------------------------------------------ предпросмотр
    def schedule_preview(self):
        self.status.setText("изменения…")
        self.timer.start()

    def update_preview(self):
        if not self.isVisible():
            return
        if self.worker is None:
            self.worker = PreviewWorker(self)
            self.worker.ready.connect(self._show_pages)
            self.worker.failed.connect(self._preview_failed)
            self.worker.started_job.connect(lambda: self.status.setText("обновляю…"))
        inv, meta = demo_invoice(self.s.values)
        values = {**self.s.values, "layout": self.layout_data}
        self.worker.request(inv, meta, values, self.s.images(), self.s.blocks_dir,
                            self.s.get_state("office_program", "auto"))

    def _show_pages(self, paths: list):
        self.status.setText("")
        self.page_pixmaps = [QPixmap(p) for p in paths]
        while self.pages_layout.count():
            it = self.pages_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for _ in self.page_pixmaps:
            lb = QLabel()
            lb.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            lb.setStyleSheet("background: white; border: 1px solid #D1D5DB;")
            self.pages_layout.addWidget(lb)
        self.pages_layout.addStretch(1)
        self._scale_pages()

    def _scale_pages(self):
        width = max(200, self.pages_scroll.viewport().width() - 8)
        for i, pm in enumerate(self.page_pixmaps):
            item = self.pages_layout.itemAt(i)
            if item and item.widget():
                scaled = pm.scaledToWidth(width, Qt.SmoothTransformation)
                item.widget().setPixmap(scaled)
                item.widget().setFixedHeight(scaled.height())

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._scale_pages()

    def _preview_failed(self, text: str):
        self.status.setText("")
        while self.pages_layout.count():
            it = self.pages_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.page_pixmaps = []
        msg = label(text + "\n\nКнопка «Открыть в Excel» покажет КП без предпросмотра.", muted=True, wrap=True)
        msg.setAlignment(Qt.AlignCenter)
        self.pages_layout.addWidget(msg)

    def open_preview_excel(self):
        """Собрать КП по текущему (даже несохранённому) макету и открыть в Excel."""
        import tempfile
        from datetime import datetime
        from pathlib import Path

        from core.kp_builder import build_kp
        inv, meta = demo_invoice(self.s.values)
        out = Path(tempfile.gettempdir()) / f"КП_макет_{datetime.now():%H%M%S}.xlsx"
        try:
            build_kp(inv, meta, {**self.s.values, "layout": self.layout_data}, self.s.images(), out,
                     self.s.blocks_dir)
        except Exception as e:  # noqa: BLE001
            error(self, f"Ошибка:\n{e}")
            return
        open_path(out, self)

    # ------------------------------------------------------------ сохранение
    def save(self) -> bool:
        if not ask(self, "Сохранить макет? Он применится ко всем будущим КП.\n\n"
                         "Текущие настройки будут сохранены в резервную копию."):
            return False
        self.s.save({"layout": self.layout_data})
        self.s.cleanup_block_images()
        self.saved_json = json.dumps(self.layout_data, sort_keys=True)
        if self.on_saved:
            self.on_saved()
        info(self, "Макет сохранён.")
        return True

    def reset_layout(self):
        if ask(self, "Вернуть стандартный макет? Свои блоки будут убраны.\n"
                     "Изменения применятся только после «Сохранить макет».", warning=True):
            self.layout_data = default_layout(self.s.values)
            self._fill_list(select=0)
            self.schedule_preview()

    def refresh(self):
        """Страница открыта — обновляем предпросмотр (могли поменяться логотипы, цвета, тексты)."""
        if not self.has_unsaved():
            self.load_layout()
        else:
            self.schedule_preview()

    def shutdown(self):
        if self.worker:
            self.worker.stop()
