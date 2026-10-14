"""Генератор коммерческих предложений из счёта на оплату. Точка входа."""
import sys

from core import updater


def main():
    # служебные режимы установки обновления — без интерфейса
    if updater.handle_update_args(sys.argv):
        return
    from ui.main_window import MainWindow
    # двойной щелчок по файлу настроек .pbsettings — программа открывается и предлагает импорт
    import_file = next((a for a in sys.argv[1:] if a.lower().endswith(".pbsettings")), None)
    MainWindow(import_file=import_file).mainloop()


if __name__ == "__main__":
    main()
