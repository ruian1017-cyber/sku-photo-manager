#!/bin/bash
# 打包为macOS .app应用
cd "$(dirname "$0")"
source venv/bin/activate
pip install -r requirements.txt
pip install Pillow pyinstaller
pyinstaller --onefile --windowed --name "SKU图片管理" \
    --add-data "config.py:." \
    --add-data "database.py:." \
    --add-data "sku_manager.py:." \
    --add-data "api_server.py:." \
    --add-data "ui_app.py:." \
    main.py
echo "打包完成，应用位于 dist/SKU图片管理.app"
