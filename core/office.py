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
# Программы, которые в этом сеансе уже не справились (например, Excel висит на окне активации):
# к ним больше не обращаемся до перезапуска программы.
_broken: set[str] = set()


def has_excel() -> bool:
    """Excel зарегистрирован в Windows и его EXCEL.EXE реально есть на диске."""
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Excel.Application\CLSID") as k:
            clsid = winreg.QueryValue(k, None)
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\LocalServer32") as k:
            server = winreg.QueryValue(k, None)
    except OSError:
        return False
    exe = server.strip().strip('"').split('"')[0].split(" /")[0].strip()
    return exe.lower().endswith(".exe") and Path(exe).exists()


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


def candidates(prefer: str = "auto") -> list[str]:
    """Порядок попыток: выбранная программа первой, затем остальные установленные;
    программы, уже не справившиеся в этом сеансе, — в самом конце."""
    have = installed()
    order = ([prefer] if prefer in have else []) + [k for k in have if k != prefer]
    return [k for k in order if k not in _broken] + [k for k in order if k in _broken]


def backend(prefer: str = "auto") -> str | None:
    """Чем будет делаться PDF. prefer — выбор пользователя ('auto' | 'excel' | 'libreoffice' | 'openoffice');
    если выбранной программы нет или она не справилась — следующая по порядку Excel → LibreOffice → OpenOffice."""
    order = candidates(prefer)
    return order[0] if order else None


def backend_name(prefer: str = "auto") -> str:
    return NAMES.get(backend(prefer) or "", "нет")


# ---------------------------------------------------------------- PDF
def to_pdf(xlsx: Path, prefer: str = "auto", skip: tuple[str, ...] = ()) -> Path:
    """xlsx -> pdf рядом с ним. Бросает OfficeError, если подходящей программы нет."""
    xlsx = Path(xlsx).resolve()
    pdf = xlsx.with_suffix(".pdf")
    order = [k for k in candidates(prefer) if k not in skip]
    if not order:
        raise OfficeError("Для PDF нужна офисная программа: Microsoft Excel, LibreOffice или Apache OpenOffice. "
                          "КП в Excel создано и без неё.")
    problems = []
    for kind in order:  # не справилась одна программа — пробуем следующую
        try:
            if kind == "excel":
                return _excel_pdf(xlsx, pdf)
            soffice = find_all_soffice()[kind]
            if kind == "libreoffice":
                return _libreoffice_pdf(soffice, xlsx, pdf)
            return _openoffice_pdf(soffice, xlsx, pdf)
        except Exception as e:  # noqa: BLE001
            _broken.add(kind)
            problems.append(f"{NAMES[kind]}: {explain(e)}")
    raise OfficeError("Не удалось сохранить PDF.\n" + "\n".join(problems))


def explain(e: Exception) -> str:
    """Понятный текст вместо кодов ошибок COM."""
    text = str(e)
    if "-2147418111" in text or "отклонен" in text.lower() or "rejected" in text.lower():
        return ("Excel не отвечает — возможно, он не активирован или открыто окно входа/активации. "
                "Выберите другую программу: Настройки → Шаблон КП → Прочее.")
    if "-2147221005" in text or "Invalid class string" in text:
        return "Excel не установлен или установлен не полностью."
    return text


def excel_pid(excel) -> int | None:
    """Номер процесса запущенного нами Excel — чтобы закрыть его, если он завис."""
    try:
        import win32process
        return win32process.GetWindowThreadProcessId(excel.Hwnd)[1]
    except Exception:  # noqa: BLE001
        return None


def kill_excel(excel, pid: int | None):
    try:
        excel.Quit()
    except Exception:  # noqa: BLE001
        pass
    if pid:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW,
                       check=False)


def _excel_pdf(xlsx: Path, pdf: Path) -> Path:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    excel, pid = None, None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        pid = excel_pid(excel)
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(xlsx), ReadOnly=True)
        wb.ExportAsFixedFormat(0, str(pdf))
        wb.Close(False)
        excel.Quit()
        excel = None
    except Exception:
        if excel is not None:
            kill_excel(excel, pid)  # не оставляем висящий Excel (например, на окне активации)
        raise
    finally:
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
# Только латиница: Python 2.7 без объявления кодировки не читает файл с русскими буквами.
_UNO_SCRIPT = r'''# -*- coding: utf-8 -*-
import os, sys, time, subprocess
# uno module lives in the OpenOffice "program" folder - add it to the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[1])))
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


def _ascii_workdir() -> Path:
    """Папка с путём только из латиницы: Python 2.7 внутри OpenOffice плохо понимает русские буквы
    в путях (имя пользователя, «Коммерческие предложения», «КП № …»)."""
    options = [Path(tempfile.gettempdir()), Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Documents",
               Path(os.environ.get("SystemDrive", "C:") + "\\")]
    for base in options:
        try:
            if not str(base).isascii():
                continue
            d = base / "pomoshnik-oo"
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".w"
            probe.write_text("ok")
            probe.unlink()
            return d
        except OSError:
            continue
    raise OfficeError("Не нашлась папка без русских букв в пути для работы OpenOffice.")


def _oo_python(soffice: Path) -> Path | None:
    prog = soffice.parent
    for p in [prog / "python.exe", *sorted(prog.glob("python-core-*/bin/python.exe"), reverse=True)]:
        if p.exists():
            return p
    return None


def _openoffice_pdf(soffice: Path, xlsx: Path, pdf: Path) -> Path:
    py = _oo_python(soffice)
    if not py:
        raise OfficeError("В Apache OpenOffice не найден встроенный Python — PDF сделать не получится.")
    prog = soffice.parent
    work = _ascii_workdir()
    src, dst = work / "kp.xlsx", work / "kp.pdf"
    script = work / "to_pdf.py"
    profile = work / "profile"
    profile.mkdir(exist_ok=True)
    shutil.copy2(xlsx, src)
    dst.unlink(missing_ok=True)
    script.write_text(_UNO_SCRIPT, encoding="utf-8")

    # окружение как у самого OpenOffice: его папка в PATH, загрузчик моста UNO; переменные Python
    # нашей программы убираем, чтобы они не сбили встроенный Python OpenOffice
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    env["PATH"] = str(prog) + os.pathsep + env.get("PATH", "")
    fundamental = prog / "fundamental.ini"
    if fundamental.exists():
        env["URE_BOOTSTRAP"] = "vnd.sun.star.pathname:" + str(fundamental)
    cmd = [str(py), str(script), str(soffice), profile.as_uri(), str(src), str(dst), f"pb_{os.getpid()}"]
    try:
        r = subprocess.run(cmd, timeout=TIMEOUT, capture_output=True, creationflags=NO_WINDOW, check=False,
                           cwd=str(prog), env=env)
    except subprocess.TimeoutExpired as e:
        raise OfficeError("OpenOffice не ответил вовремя.") from e
    if not dst.exists():
        lines = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        detail = " | ".join(line.strip() for line in lines[-3:]) or f"код выхода {r.returncode}"
        raise OfficeError(f"OpenOffice не смог сохранить PDF. {detail}")
    pdf.unlink(missing_ok=True)
    shutil.move(str(dst), pdf)
    src.unlink(missing_ok=True)
    return pdf
