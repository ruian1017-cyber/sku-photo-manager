import os
import sys
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QGridLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QMessageBox, QDialog,
    QCheckBox, QStatusBar, QFrame, QScrollArea, QListWidget, QListWidgetItem,
    QGroupBox, QComboBox
)
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtCore import Qt, QSize
from sku_manager import SKUManager
from warehouse_sync import WarehouseSync
from api_server import APIServer
from config import config, save_config


class ImagePreview(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFixedSize(160, 190)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        self.img_label = QLabel()
        self.img_label.setFixedSize(150, 150)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setStyleSheet("background: #f5f5f5;")
        layout.addWidget(self.img_label)
        self.name_label = QLabel()
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.name_label)
        self.del_btn = QPushButton("删除")
        self.del_btn.setFixedHeight(22)
        layout.addWidget(self.del_btn)

    def set_image(self, file_path, file_name, sku_no, on_delete):
        self.name_label.setText(file_name)
        try:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(148, 148, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                self.img_label.setPixmap(scaled)
            else:
                self.img_label.setText("[无法加载]")
        except Exception:
            self.img_label.setText("[错误]")
        self.del_btn.clicked.connect(lambda: on_delete(sku_no, file_name))


class NewSKUDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建SKU")
        self.setFixedSize(420, 280)
        self.selected_files = []
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("输入货号:"))
        self.sku_input = QLineEdit()
        self.sku_input.setPlaceholderText("例如: A1001")
        layout.addWidget(self.sku_input)
        self.file_btn = QPushButton("选择图片")
        self.file_btn.clicked.connect(self.choose_files)
        layout.addWidget(self.file_btn)
        self.file_label = QLabel("未选择图片")
        layout.addWidget(self.file_label)
        self.confirm_btn = QPushButton("确认创建")
        self.confirm_btn.clicked.connect(self.accept)
        layout.addWidget(self.confirm_btn)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if files:
            self.selected_files = files
            self.file_label.setText(f"已选择 {len(files)} 张图片")

    def get_data(self):
        return self.sku_input.text().strip(), self.selected_files


class WarehouseImportDialog(QDialog):
    """从仓库系统导入SKU的对话框"""
    def __init__(self, warehouse_sync, sku_manager, parent=None):
        super().__init__(parent)
        self.warehouse = warehouse_sync
        self.manager = sku_manager
        self.setWindowTitle("从仓库系统导入SKU")
        self.setMinimumSize(700, 500)
        self.selected_sku = None
        self.selected_color = None
        self._build_ui()
        self._load_skus()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 步骤1：选择SKU
        step1 = QGroupBox("步骤1：选择SKU货号")
        s1_layout = QVBoxLayout(step1)
        self.sku_list = QListWidget()
        self.sku_list.currentItemChanged.connect(self._on_sku_select)
        s1_layout.addWidget(self.sku_list)
        layout.addWidget(step1)

        # 步骤2：选择颜色
        step2 = QGroupBox("步骤2：选择颜色")
        s2_layout = QVBoxLayout(step2)
        self.color_combo = QComboBox()
        self.color_combo.setPlaceholderText("-- 请先选择SKU --")
        s2_layout.addWidget(self.color_combo)
        self.color_info = QLabel("当前选中：无")
        s2_layout.addWidget(self.color_info)
        layout.addWidget(step2)

        # 步骤3：拍照/选择照片
        step3 = QGroupBox("步骤3：上传照片")
        s3_layout = QVBoxLayout(step3)
        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("选择照片文件")
        self.select_btn.clicked.connect(self._select_photos)
        self.select_btn.setEnabled(False)
        btn_layout.addWidget(self.select_btn)
        s3_layout.addLayout(btn_layout)
        self.file_label = QLabel("未选择照片")
        s3_layout.addWidget(self.file_label)
        layout.addWidget(step3)

        # 状态
        self.status_label = QLabel("就绪")
        layout.addWidget(self.status_label)

        # 按钮
        btn_box = QHBoxLayout()
        self.import_btn = QPushButton("确认导入")
        self.import_btn.clicked.connect(self._do_import)
        self.import_btn.setEnabled(False)
        btn_box.addWidget(self.import_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

        self.selected_files = []

    def _load_skus(self):
        try:
            skus = self.warehouse.get_draft_skus()
            for sku in skus:
                text = f"{sku['货号']}  |  {sku['供应商代码']}  |  {sku['颜色'] or '无颜色'}  |  {sku['码数段'] or ''}"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, sku)
                self.sku_list.addItem(item)
            self.status_label.setText(f"已加载 {len(skus)} 个暂存SKU")
        except Exception as e:
            self.status_label.setText(f"加载失败: {e}")

    def _on_sku_select(self, current, previous):
        if not current:
            return
        sku = current.data(Qt.ItemDataRole.UserRole)
        self.selected_sku = sku
        self.color_combo.clear()
        colors = self.warehouse.parse_colors(sku.get('颜色', ''))
        if colors:
            self.color_combo.addItems(colors)
            self.color_combo.setPlaceholderText("-- 请选择颜色 --")
            self.select_btn.setEnabled(True)
        else:
            self.color_combo.setPlaceholderText("-- 该SKU无颜色信息 --")
            self.select_btn.setEnabled(False)
        self.color_info.setText(f"当前SKU: {sku['货号']}")

    def _select_photos(self):
        if not self.selected_sku:
            QMessageBox.warning(self, "提示", "请先选择SKU")
            return
        color = self.color_combo.currentText()
        if not color:
            QMessageBox.warning(self, "提示", "请先选择颜色")
            return
        self.selected_color = color
        files, _ = QFileDialog.getOpenFileNames(
            self, f"为 {self.selected_sku['货号']} - {color} 选择照片",
            "", "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if files:
            self.selected_files = files
            self.file_label.setText(f"已选择 {len(files)} 张照片")
            self.import_btn.setEnabled(True)

    def _do_import(self):
        if not self.selected_sku or not self.selected_color or not self.selected_files:
            return
        sku_no = self.selected_sku['货号']
        color = self.selected_color
        self.status_label.setText(f"正在导入 {sku_no} - {color}...")
        QApplication.processEvents()
        result = self.manager.append_images_with_color(sku_no, color, self.selected_files)
        if result["success"]:
            count = len(result['added'])
            QMessageBox.information(self, "导入成功",
                f"已为 {sku_no} - {color} 导入 {count} 张照片\n"
                f"命名示例: {result['added'][0] if result['added'] else ''}")
            self.selected_files = []
            self.file_label.setText("未选择照片")
            self.import_btn.setEnabled(False)
            self.status_label.setText(f"导入完成: {sku_no} - {color} ({count}张)")
        else:
            QMessageBox.critical(self, "导入失败", result["message"])
            self.status_label.setText("导入失败")


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(420, 250)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("归档根目录:"))
        dir_layout = QHBoxLayout()
        self.dir_input = QLineEdit(config["sku_folder"])
        dir_layout.addWidget(self.dir_input)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.browse)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)
        layout.addWidget(QLabel("API端口:"))
        self.port_input = QLineEdit(str(config["api_port"]))
        self.port_input.setFixedWidth(80)
        layout.addWidget(self.port_input)
        self.auto_check = QCheckBox("开机自启API服务")
        self.auto_check.setChecked(config["auto_start_api"])
        layout.addWidget(self.auto_check)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择归档目录")
        if d:
            self.dir_input.setText(d)

    def save(self):
        config["sku_folder"] = self.dir_input.text()
        config["api_port"] = int(self.port_input.text())
        config["auto_start_api"] = self.auto_check.isChecked()
        save_config(config)
        QMessageBox.information(self, "保存", "设置已保存，重启后生效")
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI电商图片SKU自动归类工具")
        self.setGeometry(100, 100, 950, 650)
        self.manager = SKUManager()
        self.warehouse = WarehouseSync(config["warehouse_db_path"])
        self.api_server = APIServer()
        self._build_ui()
        if config["auto_start_api"]:
            self.api_server.start()
        self._update_api_status()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        toolbar = QHBoxLayout()
        new_btn = QPushButton("新建SKU")
        new_btn.clicked.connect(self.new_sku)
        toolbar.addWidget(new_btn)
        # 同步仓库按钮
        sync_btn = QPushButton("同步仓库暂存")
        sync_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        sync_btn.clicked.connect(self.sync_warehouse)
        toolbar.addWidget(sync_btn)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入货号搜索...")
        self.search_input.setFixedWidth(180)
        self.search_input.returnPressed.connect(self.search)
        toolbar.addWidget(self.search_input)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.search)
        toolbar.addWidget(search_btn)
        date_btn = QPushButton("按日期筛选")
        date_btn.clicked.connect(self.filter_by_date)
        toolbar.addWidget(date_btn)
        export_btn = QPushButton("导出ZIP")
        export_btn.clicked.connect(self.export_zip)
        toolbar.addWidget(export_btn)
        del_btn = QPushButton("删除SKU")
        del_btn.clicked.connect(self.delete_sku)
        toolbar.addWidget(del_btn)
        toolbar.addStretch()
        settings_btn = QPushButton("设置")
        settings_btn.clicked.connect(self.show_settings)
        toolbar.addWidget(settings_btn)
        main_layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.sku_tree = QTreeWidget()
        self.sku_tree.setHeaderLabels(["货号", "颜色/图片数", "创建时间"])
        self.sku_tree.setColumnWidth(0, 150)
        self.sku_tree.setColumnWidth(1, 150)
        self.sku_tree.currentItemChanged.connect(self.on_sku_select)
        splitter.addWidget(self.sku_tree)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_widget = QWidget()
        self.preview_layout = QGridLayout(self.preview_widget)
        self.preview_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.preview_scroll.setWidget(self.preview_widget)
        splitter.addWidget(self.preview_scroll)
        splitter.setSizes([300, 650])
        main_layout.addWidget(splitter)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        self.api_label = QLabel()
        self.api_toggle = QPushButton()
        self.api_toggle.clicked.connect(self.toggle_api)
        self.status_bar.addPermanentWidget(self.api_label)
        self.status_bar.addPermanentWidget(self.api_toggle)
        self.refresh_list()

    def _update_api_status(self):
        if self.api_server.is_running():
            self.api_label.setText(f"API: 运行中 端口{config['api_port']}")
            self.api_label.setStyleSheet("color: green;")
            self.api_toggle.setText("停止API")
        else:
            self.api_label.setText("API: 已停止")
            self.api_label.setStyleSheet("color: gray;")
            self.api_toggle.setText("启动API")

    def toggle_api(self):
        if self.api_server.is_running():
            self.api_server.stop()
        else:
            self.api_server.start()
        self._update_api_status()

    def refresh_list(self, skus=None):
        self.sku_tree.clear()
        if skus is None:
            skus = self.manager.list_skus()
        for sku in skus:
            item = QTreeWidgetItem([sku["sku_no"], str(sku["image_count"]), sku["created_at"]])
            self.sku_tree.addTopLevelItem(item)

    def sync_warehouse(self):
        """从仓库系统同步暂存货盘SKU列表"""
        try:
            self.status_label.setText("正在同步仓库暂存...")
            QApplication.processEvents()
            skus = self.warehouse.get_draft_skus()
            # 更新列表显示
            self.sku_tree.clear()
            for sku in skus:
                sku_no = sku['货号']
                color = sku.get('颜色', '') or '无颜色'
                # 检查本地是否已有该SKU及图片数
                local_info = self.manager.get_sku_info(sku_no)
                img_count = len(local_info.get('images', [])) if local_info else 0
                # 显示格式：货号 | 颜色 | 本地图片数
                item = QTreeWidgetItem([
                    sku_no,
                    f"{color} | {img_count}张",
                    sku.get('供应商代码', '')
                ])
                # 存储完整SKU信息用于后续操作
                item.setData(0, Qt.ItemDataRole.UserRole, sku)
                self.sku_tree.addTopLevelItem(item)
            self.status_label.setText(f"已同步 {len(skus)} 个仓库暂存SKU")
        except Exception as e:
            QMessageBox.critical(self, "同步失败", f"无法连接仓库系统:\n{e}")
            self.status_label.setText("同步失败")

    def on_sku_select(self, current, previous):
        if not current:
            return
        sku_no = current.text(0)
        # 检查是否是仓库同步模式（有 UserRole 数据）
        warehouse_data = current.data(0, Qt.ItemDataRole.UserRole)
        if warehouse_data:
            self.show_warehouse_preview(warehouse_data)
        else:
            self.show_preview(sku_no)

    def show_warehouse_preview(self, sku_data):
        """显示仓库SKU的颜色选择和拍照上传界面"""
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sku_no = sku_data['货号']
        colors = self.warehouse.parse_colors(sku_data.get('颜色', ''))

        # SKU信息显示
        info_label = QLabel(f"货号: {sku_no}\n供应商: {sku_data.get('供应商代码', '')}\n颜色: {', '.join(colors) if colors else '无'}")
        info_label.setStyleSheet("font-size: 14px; padding: 10px; background: #e3f2fd; border-radius: 5px;")
        self.preview_layout.addWidget(info_label, 0, 0, 1, 4)

        # 已导入的图片显示
        local_info = self.manager.get_sku_info(sku_no)
        existing_images = local_info.get('images', []) if local_info else []
        if existing_images:
            img_label = QLabel(f"已导入 {len(existing_images)} 张图片:")
            self.preview_layout.addWidget(img_label, 1, 0, 1, 4)
            cols = 4
            for i, img in enumerate(existing_images[:8]):  # 最多显示8张预览
                row, col = divmod(i, cols)
                preview = ImagePreview()
                preview.set_image(img["file_path"], img["file_name"], sku_no, self.delete_image)
                self.preview_layout.addWidget(preview, 2 + row, col)

        # 颜色选择区域
        if colors:
            color_label = QLabel("选择颜色后拍照上传:")
            color_label.setStyleSheet("font-size: 13px; font-weight: bold; margin-top: 10px;")
            start_row = 3 + (len(existing_images[:8]) // 4)
            self.preview_layout.addWidget(color_label, start_row, 0, 1, 4)

            for i, color in enumerate(colors):
                btn = QPushButton(f"📷 {color}")
                btn.setFixedHeight(40)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {'#2196F3' if i % 2 == 0 else '#FF9800'};
                        color: white;
                        font-size: 13px;
                        border-radius: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {'#1976D2' if i % 2 == 0 else '#F57C00'};
                    }}
                """)
                btn.clicked.connect(lambda checked, c=color: self.upload_color_photos(sku_no, c))
                self.preview_layout.addWidget(btn, start_row + 1 + i // 4, i % 4)

        self.status_label.setText(f"仓库SKU: {sku_no} | 已导入: {len(existing_images)}张")

    def upload_color_photos(self, sku_no, color):
        """为指定颜色拍照/选择照片上传"""
        files, _ = QFileDialog.getOpenFileNames(
            self, f"为 {sku_no} - {color} 选择照片",
            "", "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if not files:
            return
        result = self.manager.append_images_with_color(sku_no, color, files)
        if result["success"]:
            count = len(result['added'])
            QMessageBox.information(self, "上传成功",
                f"已为 {sku_no} - {color} 上传 {count} 张照片\n"
                f"命名示例: {result['added'][0] if result['added'] else ''}")
            # 刷新显示
            current = self.sku_tree.currentItem()
            if current:
                warehouse_data = current.data(0, Qt.ItemDataRole.UserRole)
                if warehouse_data:
                    self.show_warehouse_preview(warehouse_data)
        else:
            QMessageBox.critical(self, "上传失败", result["message"])

    def show_preview(self, sku_no):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        info = self.manager.get_sku_info(sku_no)
        if not info:
            return
        images = info.get("images", [])
        cols = 4
        for i, img in enumerate(images):
            row, col = divmod(i, cols)
            preview = ImagePreview()
            preview.set_image(img["file_path"], img["file_name"], sku_no, self.delete_image)
            self.preview_layout.addWidget(preview, row, col)
        # 添加图片按钮
        add_row, add_col = divmod(len(images), cols)
        add_btn = QPushButton("+ 添加图片")
        add_btn.setFixedSize(160, 190)
        add_btn.setStyleSheet("font-size: 16px; border: 2px dashed #aaa; background: #fafafa;")
        add_btn.clicked.connect(lambda: self.add_images_to_sku(sku_no))
        self.preview_layout.addWidget(add_btn, add_row, add_col)
        self.status_label.setText(f"当前SKU: {sku_no} | 图片数: {len(images)}")

    def add_images_to_sku(self, sku_no):
        files, _ = QFileDialog.getOpenFileNames(
            self, f"为 {sku_no} 添加图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if not files:
            return
        result = self.manager.append_images(sku_no, files)
        if result["success"]:
            self.show_preview(sku_no)
            self.refresh_list()
            self.status_label.setText(f"已为 {sku_no} 添加 {len(result['added'])} 张图片")
        else:
            QMessageBox.critical(self, "错误", result["message"])

    def new_sku(self):
        dialog = NewSKUDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            sku_no, files = dialog.get_data()
            if not sku_no:
                QMessageBox.warning(self, "提示", "请输入货号")
                return
            if not files:
                QMessageBox.warning(self, "提示", "请选择图片")
                return
            result = self.manager.create_and_add_images(sku_no, files)
            if result["success"]:
                QMessageBox.information(self, "完成",
                    f"已创建 {sku_no}，添加 {len(result['added'])} 张图片")
                self.refresh_list()
            else:
                QMessageBox.critical(self, "错误", result["message"])

    def search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            self.refresh_list()
            return
        skus = self.manager.search_skus(keyword)
        self.refresh_list(skus)
        self.status_label.setText(f"搜索 \"{keyword}\" 找到 {len(skus)} 个结果")

    def filter_by_date(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("按日期筛选")
        dialog.setFixedSize(320, 180)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("选择日期:"))
        date_input = QLineEdit()
        date_input.setPlaceholderText("YYYY-MM-DD")
        layout.addWidget(date_input)
        quick_layout = QHBoxLayout()
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        for text, val in [("今天", today), ("昨天", yesterday)]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda checked, v=val: date_input.setText(v))
            quick_layout.addWidget(btn)
        layout.addLayout(quick_layout)
        confirm_btn = QPushButton("筛选")
        def apply():
            date = date_input.text().strip()
            if date:
                skus = self.manager.list_skus(date)
                self.refresh_list(skus)
                self.status_label.setText(f"日期 {date} 共 {len(skus)} 个SKU")
                dialog.accept()
        confirm_btn.clicked.connect(apply)
        layout.addWidget(confirm_btn)
        dialog.exec()

    def export_zip(self):
        date, ok = QFileDialog.getText(self, "导出", "输入日期 (YYYY-MM-DD):")
        if not ok or not date:
            return
        output_dir = QFileDialog.getExistingDirectory(self, "选择导出位置")
        if not output_dir:
            return
        result = self.manager.export_by_date(date, output_dir)
        if result["success"]:
            QMessageBox.information(self, "导出成功", f"已导出到:\n{result['path']}")
        else:
            QMessageBox.warning(self, "导出失败", result["message"])

    def delete_image(self, sku_no, file_name):
        reply = QMessageBox.question(self, "确认", f"删除 {file_name}？",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            result = self.manager.delete_image(sku_no, file_name)
            if result["success"]:
                self.show_preview(sku_no)
                self.refresh_list()
            else:
                QMessageBox.critical(self, "错误", result["message"])

    def delete_sku(self):
        current = self.sku_tree.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择要删除的SKU")
            return
        sku_no = current.text(0)
        reply = QMessageBox.question(self, "确认删除",
            f"确定删除货号 {sku_no} 及其所有图片？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            result = self.manager.delete_sku(sku_no)
            if result["success"]:
                self.refresh_list()
                self.clear_preview()
                self.status_label.setText(f"已删除 {sku_no}")
            else:
                QMessageBox.critical(self, "错误", result["message"])

    def clear_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def show_settings(self):
        SettingsDialog(self).exec()


def run():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
