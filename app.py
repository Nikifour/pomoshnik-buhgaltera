"""Помощник Бухгалтера. Точка входа."""
import sys

from core import updater


def main():
    # служебные режимы установки обновления — без интерфейса
    if updater.handle_update_args(sys.argv):
        return

    import ctypes

    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtWidgets import QApplication

    # своя иконка на панели задач Windows (иначе показывается иконка Python)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Pomoshnik.Buhgaltera")
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # одинаковый вид на всех версиях Windows, полностью настраивается стилями
    QLocale.setDefault(QLocale(QLocale.Russian, QLocale.Russia))
    translator = QTranslator(app)  # стандартные окна Qt (Да/Нет, выбор файла, календарь) — по-русски
    if translator.load("qtbase_ru", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)

    from ui.main_window import MainWindow
    # двойной щелчок по файлу настроек .pbsettings — программа открывается и предлагает импорт
    import_file = next((a for a in sys.argv[1:] if a.lower().endswith(".pbsettings")), None)
    win = MainWindow(import_file=import_file)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
