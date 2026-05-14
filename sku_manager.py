import os
import shutil
from database import Database
from config import config


class SKUManager:
    def __init__(self):
        self.db = Database(config["db_path"])
        self.sku_folder = config["sku_folder"]
        os.makedirs(self.sku_folder, exist_ok=True)

    def create_sku(self, sku_no):
        if self.db.sku_exists(sku_no):
            return {"success": False, "message": f"货号 {sku_no} 已存在"}
        folder_path = os.path.join(self.sku_folder, sku_no)
        os.makedirs(folder_path, exist_ok=True)
        self.db.create_sku(sku_no, folder_path)
        return {"success": True, "folder_path": folder_path}

    def append_images(self, sku_no, image_paths):
        if not self.db.sku_exists(sku_no):
            return {"success": False, "message": f"货号 {sku_no} 不存在"}
        sku = self.db.get_sku(sku_no)
        folder_path = sku["folder_path"]
        max_seq = self.db.get_max_seq(sku_no)
        added = []
        for i, img_path in enumerate(image_paths):
            seq = max_seq + i + 1
            ext = os.path.splitext(img_path)[1]
            new_name = f"{sku_no}-{seq}{ext}"
            new_path = os.path.join(folder_path, new_name)
            shutil.copy2(img_path, new_path)
            self.db.add_image(sku_no, new_name, seq, new_path)
            added.append(new_name)
        return {"success": True, "added": added}

    def create_and_add_images(self, sku_no, image_paths):
        if self.db.sku_exists(sku_no):
            return self.append_images(sku_no, image_paths)
        result = self.create_sku(sku_no)
        if not result["success"]:
            return result
        return self.append_images(sku_no, image_paths)

    def append_images_with_color(self, sku_no, color, image_paths):
        """添加带颜色标记的图片，命名规则：{sku_no}-{颜色}-{seq}.ext"""
        # 确保SKU存在
        if not self.db.sku_exists(sku_no):
            result = self.create_sku(sku_no)
            if not result["success"]:
                return result
        sku = self.db.get_sku(sku_no)
        folder_path = sku["folder_path"]
        max_seq = self.db.get_max_seq(sku_no)
        added = []
        for i, img_path in enumerate(image_paths):
            seq = max_seq + i + 1
            ext = os.path.splitext(img_path)[1]
            # 命名规则：{sku_no}-{颜色}-{seq}.ext
            new_name = f"{sku_no}-{color}-{seq}{ext}"
            new_path = os.path.join(folder_path, new_name)
            shutil.copy2(img_path, new_path)
            self.db.add_image(sku_no, new_name, seq, new_path)
            added.append(new_name)
        return {"success": True, "added": added}

    def get_sku_info(self, sku_no):
        sku = self.db.get_sku(sku_no)
        if not sku:
            return None
        images = self.db.get_images(sku_no)
        sku["images"] = images
        return sku

    def list_skus(self, date=None):
        return self.db.get_all_skus(date)

    def search_skus(self, keyword):
        return self.db.search_skus(keyword)

    def delete_image(self, sku_no, file_name):
        images = self.db.get_images(sku_no)
        target = None
        for img in images:
            if img["file_name"] == file_name:
                target = img
                break
        if not target:
            return {"success": False, "message": "图片不存在"}
        if os.path.exists(target["file_path"]):
            os.remove(target["file_path"])
        self.db.delete_image(sku_no, file_name)
        return {"success": True}

    def delete_sku(self, sku_no):
        sku = self.db.get_sku(sku_no)
        if not sku:
            return {"success": False, "message": f"货号 {sku_no} 不存在"}
        folder_path = sku["folder_path"]
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        self.db.delete_sku(sku_no)
        return {"success": True}

    def export_by_date(self, date, output_path):
        skus = self.db.get_all_skus(date)
        if not skus:
            return {"success": False, "message": "该日期无SKU数据"}
        import zipfile
        zip_name = f"SKU导出_{date}.zip"
        zip_path = os.path.join(output_path, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for sku in skus:
                folder = sku["folder_path"]
                if os.path.exists(folder):
                    for fname in os.listdir(folder):
                        fpath = os.path.join(folder, fname)
                        arcname = os.path.join(sku["sku_no"], fname)
                        zf.write(fpath, arcname)
        return {"success": True, "path": zip_path}
