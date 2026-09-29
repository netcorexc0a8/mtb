# Точка входа для PyInstaller (относительные импорты в __main__ ему не подходят)
from mtb.main import main

if __name__ == "__main__":
    main()
