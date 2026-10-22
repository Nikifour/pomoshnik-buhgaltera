"""Офисная программа для превращения КП (Excel-файла) в PDF.

По порядку пробуем: Microsoft Excel → LibreOffice → Apache OpenOffice.
- Excel — через COM (как раньше);
- LibreOffice — командой `soffice --headless --convert-to pdf`;
- Apache OpenOffice не умеет --convert-to, поэтому запускаем его собственный Python с UNO:
  он открывает файл невидимо и сохраняет PDF.
LibreOffice/OpenOffice запускаются с отдельным временным профилем — так они не мешают
офису, который пользователь уже держит открытым.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import winreg
from pathlib import Path

TIMEOUT = 180
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class OfficeError(Exception):
    pass


# ---------------------------------------------------------------- поиск программ
def has_excel() -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID"))
        return True
    except OSError:
        return False


def _app_path(exe: str) -> Path | None:
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                p = Path(winreg.QueryValue(k, None))
                if p.exists():
                    return p
        except OSError:
            pass
    return None


def find_all_soffice() -> dict[str, Path]:
    """Все найденные LibreOffice / Apache OpenOffice: {'libreoffice': путь, 'openoffice': путь}."""
    pf = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    candidates = []
    for base in filter(None, pf):
        candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.exe")
    for base in filter(None, pf):
        for name in ("OpenOffice 4", "OpenOffice.org 3", "OpenOffice"):
            candidates.append(Path(base) / name / "program" / "soffice.exe")
    reg = _app_path("soffice.exe")
    if reg:
        candidates.insert(0, reg)
    found: dict[str, Path] = {}
    for p in candidates:
        if p.exists():
            kind = "libreoffice" if "libreoffice" in str(p).lower() else "openoffice"
            found.setdefault(kind, p)
    return found


NAMES = {"excel": "Microsoft Excel", "libreoffice": "LibreOffice", "openoffice": "Apache OpenOffice"}
ORDER = ("excel", "libreoffice", "openoffice")


def installed() -> list[str]:
    """Какие из программ есть на этом компьютере, в порядке предпочтения."""
    soff = find_all_soffice()
    return [k for k in ORDER if (k == "excel" and has_excel()) or k in soff]


def backend(prefer: str = "auto") -> str | None:
    """Чем будет делаться PDF. prefer — выбор пользователя ('auto' | 'excel' | 'libreoffice' | 'openoffice');
    если выбранной программы нет — автоматически по порядку Excel → LibreOffice → OpenOffice."""
    have = installed()
    if prefer in have:
        return prefer
    return have[0] if have else None


def backend_name(prefer: str = "auto") -> str:
    return NAMES.get(backend(prefer) or "", "нет")


# ---------------------------------------------------------------- PDF
def to_pdf(xlsx: Path, prefer: str = "auto") -> Path:
    """xlsx -> pdf рядом с ним. Бросает OfficeError, если подходящей программы нет."""
    xlsx = Path(xlsx).resolve()
    pdf = xlsx.with_suffix(".pdf")
    kind = backend(prefer)
    if kind is None:
        raise OfficeError("Для PDF нужна офисная программа: Microsoft Excel, LibreOffice или Apache OpenOffice. "
                          "КП в Excel создано и без неё.")
    if kind == "excel":
        return _excel_pdf(xlsx, pdf)
    soffice = find_all_soffice()[kind]
    if kind == "libreoffice":
        return _libreoffice_pdf(soffice, xlsx, pdf)
    return _openoffice_pdf(soffice, xlsx, pdf)


def _excel_pdf(xlsx: Path, pdf: Path) -> Path:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        wb = excel.Workbooks.Open(str(xlsx), ReadOnly=True)
        wb.ExportAsFixedFormat(0, str(pdf))
        wb.Close(False)
    finally:
        excel.Quit()
        pythoncom.CoUninitialize()
    return pdf


def _profile_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "pomoshnik-buhgaltera-office-profile"
    d.mkdir(exist_ok=True)
    return d


def _libreoffice_pdf(soffice: Path, xlsx: Path, pdf: Path) -> Path:
    outdir = Path(tempfile.mkdtemp(prefix="pb_pdf_"))
    cmd = [str(soffice), f"-env:UserInstallation={_profile_dir().as_uri()}", "--headless", "--norestore",
           "--nolockcheck", "--convert-to", "pdf", "--outdir", str(outdir), str(xlsx)]
    try:
        subprocess.run(cmd, timeout=TIMEOUT, capture_output=True, creationflags=NO_WINDOW, check=False)
    except subprocess.TimeoutExpired as e:
        raise OfficeError("LibreOffice не ответил вовремя.") from e
    made = outdir / (xlsx.stem + ".pdf")
    if not made.exists():
        raise OfficeError("LibreOffice не смог сохранить PDF.")
    shutil.move(str(made), pdf)
    shutil.rmtree(outdir, ignore_errors=True)
    return pdf


# Скрипт для Python, встроенного в Apache OpenOffice (там Python 2.7 — пишем совместимо).
_UNO_SCRIPT = r'''
import os, sys, time, subprocess
import uno
from com.sun.star.beans import PropertyValue

def prop(name, value):
    p = PropertyValue(); p.Name = name; p.Value = value; return p

soffice, profile, src, dst, pipe = sys.argv[1:6]
proc = subprocess.Popen([soffice, "-env:UserInstallation=" + profile, "-headless", "-invisible", "-nologo",
                         "-norestore", "-nofirststartwizard", "-nodefault",
                         "-accept=pipe,name=%s;urp;StarOffice.ComponentContext" % pipe])
local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
ctx = None
for i in range(120):
    try:
        ctx = resolver.resolve("uno:pipe,name=%s;urp;StarOffice.ComponentContext" % pipe)
        break
    except Exception:
        time.sleep(0.5)
if ctx is None:
    proc.kill(); sys.exit(2)
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(src), "_blank", 0, (prop("Hidden", True),))
doc.storeToURL(uno.systemPathToFileUrl(dst), (prop("FilterName", "calc_pdf_Export"),))
doc.close(True)
try:
    desktop.terminate()
except Exception:
    pass
for i in range(20):
    if proc.poll() is not None:
        break
    time.sleep(0.25)
if proc.poll() is None:
    proc.kill()
'''


def _openoffice_pdf(soffice: Path, xlsx: Path, pdf: Path) -> Path:
    py = soffice.parent / "python.exe"
    if not py.exists():
        raise OfficeError("В Apache OpenOffice не найден встроенный Python — PDF сделать не получится.")
    script = Path(tempfile.gettempdir()) / "pomoshnik_oo_pdf.py"
    script.write_text(_UNO_SCRIPT, encoding="utf-8")
    pdf.unlink(missing_ok=True)
    cmd = [str(py), str(script), str(soffice), _profile_dir().as_uri(), str(xlsx), str(pdf),
           f"pb_{os.getpid()}"]
    try:
        r = subprocess.run(cmd, timeout=TIMEOUT, capture_output=True, creationflags=NO_WINDOW, check=False,
                           cwd=str(soffice.parent))
    except subprocess.TimeoutExpired as e:
        raise OfficeError("OpenOffice не ответил вовремя.") from e
    if not pdf.exists():
        detail = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise OfficeError(f"OpenOffice не смог сохранить PDF. {detail[0]}")
    return pdf
