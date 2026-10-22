"""Живой предпросмотр КП: Excel-файл -> PDF (через Excel) -> картинки страниц.

Работает в отдельном потоке. Excel запускается один раз и остаётся открытым в фоне,
пока жив поток, поэтому повторные обновления занимают около секунды.
Если пришло несколько запросов подряд, рисуется только последний.
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core import office
from core.kp_builder import build_kp


class PreviewWorker(QThread):
    ready = Signal(list)      # пути к PNG страниц
    failed = Signal(str)
    started_job = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self.dir = Path(tempfile.mkdtemp(prefix="pb_preview_"))
        self.xlsx_path: Path | None = None  # последний собранный файл — для «Открыть в Excel»

    def request(self, inv, meta, values: dict, images: dict, blocks_dir: Path, prefer: str = "auto"):
        with self._lock:
            self._job = (inv, meta, dict(values), dict(images), blocks_dir, prefer)
        self._wake.set()
        if not self.isRunning():
            self.start()

    def stop(self):
        self._stop = True
        self._wake.set()
        self.wait(8000)

    def run(self):
        import pythoncom
        pythoncom.CoInitialize()
        excel = None
        n = 0
        try:
            while not self._stop:
                self._wake.wait()
                self._wake.clear()
                if self._stop:
                    break
                with self._lock:
                    job, self._job = self._job, None
                if not job:
                    continue
                self.started_job.emit()
                n += 1
                try:
                    kind = office.backend(job[5])
                    if kind is None:
                        raise office.OfficeError("Для предпросмотра нужна офисная программа: Microsoft Excel, "
                                                 "LibreOffice или Apache OpenOffice.")
                    if kind == "excel" and excel is None:
                        import win32com.client
                        excel = win32com.client.DispatchEx("Excel.Application")
                        excel.Visible = False
                        excel.DisplayAlerts = False
                    if kind != "excel":
                        excel = self._reset_excel(excel) if excel is not None else None
                    pages = self._render(excel if kind == "excel" else None, job, n)
                    self.ready.emit([str(p) for p in pages])
                except Exception as e:  # noqa: BLE001
                    excel = self._reset_excel(excel)
                    self.failed.emit(self._explain(e))
        finally:
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:  # noqa: BLE001
                    pass
            pythoncom.CoUninitialize()

    def _render(self, excel, job, n) -> list[Path]:
        import pypdfium2 as pdfium
        inv, meta, values, images, blocks_dir, prefer = job
        xlsx = self.dir / f"preview_{n}.xlsx"
        pdf = xlsx.with_suffix(".pdf")
        build_kp(inv, meta, values, images, xlsx, blocks_dir)
        if excel is not None:  # Excel уже открыт в фоне — быстро
            wb = excel.Workbooks.Open(str(xlsx), ReadOnly=True)
            try:
                wb.ExportAsFixedFormat(0, str(pdf))
            finally:
                wb.Close(False)
        else:  # LibreOffice / OpenOffice — запуск на каждое обновление, медленнее
            office.to_pdf(xlsx, prefer)
        doc = pdfium.PdfDocument(str(pdf))
        pages = []
        try:
            for i in range(len(doc)):
                png = self.dir / f"preview_{n}_{i + 1}.png"
                doc[i].render(scale=1.6).to_pil().save(png)
                pages.append(png)
        finally:
            doc.close()
        self.xlsx_path = xlsx
        self._cleanup(n)
        return pages

    def _cleanup(self, keep_n: int):
        """Удаляем файлы старых предпросмотров (они могут быть ещё заняты — тогда в другой раз)."""
        for f in self.dir.glob("preview_*"):
            num = f.stem.split("_")[1]
            if num.isdigit() and int(num) < keep_n - 1:
                try:
                    f.unlink()
                except OSError:
                    pass

    @staticmethod
    def _reset_excel(excel):
        try:
            if excel is not None:
                excel.Quit()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
        return None

    @staticmethod
    def _explain(e: Exception) -> str:
        text = str(e)
        if isinstance(e, office.OfficeError):
            return text
        if "Invalid class string" in text or "-2147221005" in text:
            return "Microsoft Excel не запускается. Выберите другую программу: Настройки → Шаблон КП → Прочее."
        return f"Не удалось построить предпросмотр:\n{text}"
