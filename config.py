import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_CONFIG = {
    "data_root": "/Volumes/Ryan/详情图管理",
    "db_path": "/Volumes/Ryan/详情图管理/数据库/sku_index.db",
    "sku_folder": "/Volumes/Ryan/详情图管理/SKU图片",
    "warehouse_db_path": "/Volumes/Ryan/仓库货盘/仓库系统数据/sku.db",
    "api_port": 8765,
    "auto_start_api": True,
}


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
            config = DEFAULT_CONFIG.copy()
            config.update(saved)
            return config
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


config = load_config()
