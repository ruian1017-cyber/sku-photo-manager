import os
import threading
from datetime import datetime
from flask import Flask, jsonify, send_file, request
from database import Database
from warehouse_sync import WarehouseSync
from sku_manager import SKUManager
from config import config


app = Flask(__name__)
db = None
warehouse = None
manager = None


def init_db():
    global db, warehouse, manager
    db = Database(config["db_path"])
    warehouse = WarehouseSync(config["warehouse_db_path"])
    manager = SKUManager()


@app.route("/api/v1/skus", methods=["GET"])
def get_skus():
    date = request.args.get("date")
    skus = db.get_all_skus(date)
    return jsonify({"success": True, "data": skus})


@app.route("/api/v1/skus/<sku_no>/exists", methods=["GET"])
def sku_exists(sku_no):
    exists = db.sku_exists(sku_no)
    return jsonify({"success": True, "exists": exists})


@app.route("/api/v1/skus/<sku_no>/images", methods=["GET"])
def get_images(sku_no):
    if not db.sku_exists(sku_no):
        return jsonify({"success": False, "message": "货号不存在"}), 404
    images = db.get_images(sku_no)
    for img in images:
        img["url"] = f"http://{request.host}/api/v1/skus/{sku_no}/images/{img['file_name']}"
    return jsonify({"success": True, "data": images})


@app.route("/api/v1/skus/<sku_no>/images/<filename>", methods=["GET"])
def get_image(sku_no, filename):
    images = db.get_images(sku_no)
    target = None
    for img in images:
        if img["file_name"] == filename:
            target = img
            break
    if not target or not os.path.exists(target["file_path"]):
        return jsonify({"success": False, "message": "图片不存在"}), 404
    return send_file(target["file_path"])


@app.route("/api/v1/skus/<sku_no>/images/<filename>/thumb", methods=["GET"])
def get_thumb(sku_no, filename):
    """返回缩略图（宽度400px），用于列表展示"""
    images = db.get_images(sku_no)
    target = None
    for img in images:
        if img["file_name"] == filename:
            target = img
            break
    if not target or not os.path.exists(target["file_path"]):
        return jsonify({"success": False, "message": "图片不存在"}), 404

    # 缓存缩略图
    thumb_dir = os.path.join(config.get("data_root", "/tmp"), "thumbs")
    os.makedirs(thumb_dir, exist_ok=True)
    thumb_path = os.path.join(thumb_dir, filename)

    if not os.path.exists(thumb_path):
        try:
            from PIL import Image as PILImage
            img = PILImage.open(target["file_path"])
            w, h = img.size
            if w > 400:
                h = int(h * 400 / w)
                w = 400
            img = img.resize((w, h), PILImage.LANCZOS)
            img.save(thumb_path, quality=70)
        except ImportError:
            # 没有Pillow就返回原图
            return send_file(target["file_path"])

    return send_file(thumb_path)


# ============ 图片同步接口（Mac拉取用） ============

@app.route("/api/v1/sync/images", methods=["GET"])
def list_all_images():
    """列出所有SKU的图片，供Mac同步"""
    conn = db._get_conn()
    rows = conn.execute(
        "SELECT si.sku_no, si.file_name, si.file_path, si.seq_no "
        "FROM sku_images si ORDER BY si.sku_no, si.seq_no"
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        sku_no = r[0]
        if sku_no not in result:
            result[sku_no] = []
        result[sku_no].append({
            "file_name": r[1],
            "file_path": r[2],
            "seq_no": r[3]
        })
    return jsonify({"success": True, "data": result})


@app.route("/api/v1/sync/images/<sku_no>/<filename>", methods=["GET"])
def download_image_for_sync(sku_no, filename):
    """供Mac下载单张图片"""
    images = db.get_images(sku_no)
    for img in images:
        if img["file_name"] == filename and os.path.exists(img["file_path"]):
            return send_file(img["file_path"])
    return jsonify({"success": False, "message": "不存在"}), 404


@app.route("/api/v1/sync/new-skus", methods=["GET"])
def list_new_skus():
    """列出手机端创建的、不在仓库系统中的SKU"""
    conn = db._get_conn()
    # 获取所有本地创建的SKU
    local_rows = conn.execute(
        "SELECT sku_no, color FROM sku_index"
    ).fetchall()
    conn.close()

    # 获取仓库系统中的货号
    warehouse_nos = set()
    try:
        wh_skus = warehouse.get_draft_skus()
        warehouse_nos = {s["货号"] for s in wh_skus}
    except Exception:
        pass

    # 筛选出不在仓库中的SKU
    new_skus = []
    for r in local_rows:
        if r[0] not in warehouse_nos:
            new_skus.append({"货号": r[0], "颜色": r[1] or ""})

    return jsonify({"success": True, "data": new_skus})


# ============ 仓库同步接口 ============

@app.route("/api/v1/warehouse/drafts", methods=["GET"])
def get_warehouse_drafts():
    """获取仓库暂存货盘列表 + 本地手动添加的SKU"""
    try:
        skus = warehouse.get_draft_skus()
    except Exception:
        skus = []

    # 标记来源
    for s in skus:
        s["_source"] = "warehouse"

    # 合并本地数据库中的SKU
    local_skus = db.get_all_skus()
    local_map = {ls["sku_no"]: ls for ls in local_skus}
    warehouse_nos = {s["货号"] for s in skus}

    # 给仓库SKU补上本地的 updated_at 和 image_count
    for s in skus:
        local = local_map.get(s["货号"])
        if local:
            s["_updated_at"] = local.get("updated_at", "")
            s["_image_count"] = local.get("image_count", 0)

    for ls in local_skus:
        if ls["sku_no"] not in warehouse_nos:
            skus.append({
                "货号": ls["sku_no"],
                "颜色": ls.get("color", ""),
                "供应商代码": "",
                "码数段": "",
                "_source": "local",
                "_image_count": ls.get("image_count", 0),
                "_updated_at": ls.get("updated_at", ""),
            })

    return jsonify({"success": True, "data": skus})


@app.route("/api/v1/warehouse/skus/<int:sku_id>", methods=["GET"])
def get_warehouse_sku(sku_id):
    """获取仓库SKU详情"""
    try:
        sku = warehouse.get_sku_by_id(sku_id)
        if sku:
            return jsonify({"success": True, "data": sku})
        return jsonify({"success": False, "message": "SKU不存在"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============ 删除SKU ============

@app.route("/api/v1/skus/<sku_no>/delete", methods=["POST"])
def delete_sku(sku_no):
    """删除SKU及其所有图片"""
    if not db.sku_exists(sku_no):
        return jsonify({"success": False, "message": "SKU不存在"}), 404
    # 删除文件
    images = db.get_images(sku_no)
    for img in images:
        try:
            os.remove(img["file_path"])
        except Exception:
            pass
    # 删除文件夹
    sku = db.get_sku(sku_no)
    if sku and sku.get("folder_path") and os.path.exists(sku["folder_path"]):
        import shutil
        shutil.rmtree(sku["folder_path"], ignore_errors=True)
    # 删除数据库记录
    db.delete_sku(sku_no)
    return jsonify({"success": True})


# ============ 仓库同步 ============

SYNC_REQUEST_FILE = os.path.join(os.path.dirname(config["warehouse_db_path"]), ".sync_request")

@app.route("/api/v1/warehouse/push", methods=["POST"])
def push_warehouse_db():
    """Mac端推送 sku.db 到服务器"""
    file = request.files.get("db_file")
    if not file or not file.filename.endswith(".db"):
        return jsonify({"success": False, "message": "无效文件"}), 400

    db_path = config["warehouse_db_path"]
    if os.path.exists(db_path):
        import shutil
        shutil.copy2(db_path, db_path + ".bak")

    file.save(db_path)
    global warehouse
    warehouse = WarehouseSync(db_path)

    # 清除同步请求标记
    if os.path.exists(SYNC_REQUEST_FILE):
        os.remove(SYNC_REQUEST_FILE)

    return jsonify({"success": True})


@app.route("/api/v1/warehouse/sync-request", methods=["POST"])
def create_sync_request():
    """手机端触发：标记需要同步"""
    with open(SYNC_REQUEST_FILE, "w") as f:
        f.write(str(datetime.now().timestamp()))
    return jsonify({"success": True})


@app.route("/api/v1/warehouse/check-sync", methods=["GET"])
def check_sync_request():
    """Mac端轮询：检查是否有同步请求"""
    pending = os.path.exists(SYNC_REQUEST_FILE)
    return jsonify({"success": True, "pending": pending})


# ============ 手动添加SKU ============

@app.route("/api/v1/skus/create", methods=["POST"])
def create_sku():
    """手动创建SKU"""
    data = request.json or {}
    sku_no = data.get("sku_no", "").strip()
    color = data.get("color", "").strip()
    if not sku_no:
        return jsonify({"success": False, "message": "货号不能为空"}), 400
    if db.sku_exists(sku_no):
        # 已存在则追加颜色
        if color:
            sku = db.get_sku(sku_no)
            if sku:
                existing = sku.get("color", "")
                if color not in existing:
                    new_color = (existing + "，" + color) if existing else color
                    db.update_color(sku_no, new_color)
        return jsonify({"success": True, "message": "SKU已存在", "sku_no": sku_no})
    folder_path = os.path.join(config["sku_folder"], sku_no)
    os.makedirs(folder_path, exist_ok=True)
    db.create_sku(sku_no, folder_path, color)
    return jsonify({"success": True, "sku_no": sku_no})


# ============ 图片上传接口 ============

@app.route("/api/v1/skus/<sku_no>/upload", methods=["POST"])
def upload_images(sku_no):
    """上传图片到指定SKU（支持带颜色）"""
    color = request.form.get("color", "")
    files = request.files.getlist("images")

    if not files:
        return jsonify({"success": False, "message": "没有选择图片"}), 400

    # 保存到临时目录
    temp_dir = os.path.join(config.get("data_root", "/tmp"), "temp_uploads")
    os.makedirs(temp_dir, exist_ok=True)

    temp_paths = []
    for f in files:
        if f.filename:
            temp_path = os.path.join(temp_dir, f.filename)
            f.save(temp_path)
            temp_paths.append(temp_path)

    if not temp_paths:
        return jsonify({"success": False, "message": "没有有效图片"}), 400

    # 调用管理器添加图片
    if color:
        result = manager.append_images_with_color(sku_no, color, temp_paths)
    else:
        result = manager.append_images(sku_no, temp_paths)

    # 清理临时文件
    for path in temp_paths:
        try:
            os.remove(path)
        except:
            pass

    if result["success"]:
        return jsonify({
            "success": True,
            "added": result["added"],
            "count": len(result["added"])
        })
    else:
        return jsonify(result), 400


# ============ Web页面 ============

@app.route("/app")
def index():
    """移动端Web页面 - iOS风格设计"""
    from flask import make_response
    resp = make_response('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>SKU拍照上传</title>
    <style>
        :root {
            --primary-start: #667eea;
            --primary-end: #764ba2;
            --success: #34C759;
            --warning: #FF9500;
            --error: #FF3B30;
            --info: #007AFF;
            --bg: #F2F2F7;
            --card: #FFFFFF;
            --text-primary: #1C1C1E;
            --text-secondary: #8E8E93;
            --separator: #C6C6C8;
            --radius-card: 16px;
            --radius-btn: 14px;
            --radius-pill: 20px;
            --safe-top: env(safe-area-inset-top, 12px);
            --safe-bottom: env(safe-area-inset-bottom, 0px);
            --safe-left: env(safe-area-inset-left, 0px);
            --safe-right: env(safe-area-inset-right, 0px);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
        }

        html, body {
            width: 100%;
            overflow-x: hidden;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "PingFang SC", "HUAWEI Sans", sans-serif;
            background: var(--bg);
            color: var(--text-primary);
            padding-top: calc(56px + var(--safe-top));
            padding-left: var(--safe-left);
            padding-right: var(--safe-right);
            padding-bottom: calc(40px + var(--safe-bottom));
            -webkit-font-smoothing: antialiased;
        }

        /* 导航栏 */
        .navbar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: calc(56px + var(--safe-top));
            padding-top: var(--safe-top);
            background: rgba(255,255,255,0.85);
            backdrop-filter: saturate(180%) blur(20px);
            -webkit-backdrop-filter: saturate(180%) blur(20px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            border-bottom: 0.5px solid rgba(0,0,0,0.1);
        }

        .navbar-title {
            font-size: 18px;
            font-weight: 600;
        }

        .navbar-actions {
            position: absolute;
            right: 16px;
            top: 0;
            bottom: 0;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .nav-icon-btn {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: none;
            background: rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
        }
        .nav-icon-btn:active {
            background: rgba(0,0,0,0.1);
            transform: scale(0.92);
        }
        .nav-icon-btn svg {
            width: 20px;
            height: 20px;
            color: var(--text-primary);
        }
        .nav-icon-btn.syncing svg {
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }

        /* 同步提示条 */
        .sync-bar {
            position: fixed;
            top: calc(56px + var(--safe-top));
            left: 0;
            right: 0;
            background: rgba(52,199,89,0.95);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            color: white;
            padding: 10px 20px;
            font-size: 14px;
            font-weight: 500;
            text-align: center;
            z-index: 999;
            transform: translateY(-100%);
            transition: transform 0.3s ease;
        }
        .sync-bar.show { transform: translateY(0); }
        .sync-bar.error { background: rgba(255,59,48,0.95); }

        /* 区域标题 */
        .section-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 20px 10px;
        }

        .section-title {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .section-count {
            font-size: 13px;
            color: var(--text-secondary);
        }

        /* 搜索栏 - 独立浮动 */
        .search-bar-wrap {
            padding: 12px 20px;
        }
        .search-bar {
            display: flex;
            align-items: center;
            background: var(--card);
            border-radius: 22px;
            height: 44px;
            padding: 0 14px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            gap: 8px;
        }
        .search-bar svg {
            flex-shrink: 0;
            opacity: 0.4;
        }
        .search-bar input {
            flex: 1;
            height: 100%;
            border: none;
            background: none;
            font-size: 15px;
            outline: none;
            color: var(--text-primary);
        }
        .search-bar input::placeholder { color: var(--text-secondary); }
        .search-bar .search-clear {
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #D1D1D6;
            color: white;
            border: none;
            font-size: 12px;
            display: none;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }
        .search-bar .search-clear.show { display: flex; }

        /* 卡片容器 */
        .card {
            background: var(--card);
            border-radius: var(--radius-card);
            margin: 0 20px 16px;
            overflow: hidden;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
        }

        /* 手动输入区 */
        .manual-input-row {
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .manual-input-top {
            display: flex;
            gap: 10px;
        }

        .manual-input-top input {
            height: 48px;
            border: 1.5px solid #E5E5EA;
            border-radius: 12px;
            padding: 0 16px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.2s;
            width: 0;
        }

        .manual-input-top input:focus {
            border-color: var(--primary-start);
        }

        .manual-input-top input:first-child {
            flex: 1;
        }

        .manual-input-top input:nth-child(2) {
            flex: 0 0 100px;
        }

        .manual-input-top button {
            height: 48px;
            padding: 0 20px;
            background: linear-gradient(135deg, var(--primary-start), var(--primary-end));
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            white-space: nowrap;
            flex-shrink: 0;
        }

        /* SKU列表 */
        .sku-list {
            max-height: 50vh;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
        }

        .sku-item {
            display: flex;
            align-items: center;
            padding: 14px 20px;
            border-bottom: 0.5px solid var(--separator);
            cursor: pointer;
            transition: background 0.15s;
            position: relative;
        }

        .sku-item:last-child {
            border-bottom: none;
        }

        .sku-item:active {
            background: #E5E5EA;
        }

        .sku-item.selected {
            background: #F0F0FF;
        }

        .sku-item.selected::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 4px;
            background: linear-gradient(180deg, var(--primary-start), var(--primary-end));
            border-radius: 0 2px 2px 0;
        }

        .sku-icon {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: linear-gradient(135deg, var(--primary-start), var(--primary-end));
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 18px;
            font-weight: 600;
            margin-right: 14px;
            flex-shrink: 0;
        }

        .sku-info {
            flex: 1;
            min-width: 0;
        }

        .sku-no {
            font-size: 16px;
            font-weight: 600;
        }

        .sku-meta {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 4px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .sku-time {
            font-size: 11px;
            color: var(--text-secondary);
            opacity: 0.5;
            margin-left: 6px;
        }

        .sku-arrow {
            color: var(--text-secondary);
            font-size: 18px;
            margin-left: 8px;
            flex-shrink: 0;
        }

        .sku-count {
            font-size: 12px;
            color: var(--primary-start);
            font-weight: 500;
            flex-shrink: 0;
        }

        /* 颜色标签 - 横向滚动 */
        .color-tabs-wrap {
            padding: 0 20px 12px;
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }
        .color-tabs-wrap::-webkit-scrollbar { display: none; }

        .color-tab {
            flex-shrink: 0;
            padding: 8px 18px;
            border: 1.5px solid #E5E5EA;
            background: white;
            color: var(--text-primary);
            border-radius: var(--radius-pill);
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s;
        }
        .color-tab:active { transform: scale(0.96); }
        .color-tab.selected {
            background: linear-gradient(135deg, var(--primary-start), var(--primary-end));
            color: white;
            border-color: transparent;
            box-shadow: 0 3px 10px rgba(102,126,234,0.35);
        }
        .color-tab-add {
            flex-shrink: 0;
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: 1.5px dashed var(--primary-start);
            background: none;
            color: var(--primary-start);
            font-size: 18px;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }

        /* 颜色追加行 */
        .add-color-row {
            display: flex;
            gap: 10px;
            padding: 0 20px 16px;
        }

        .add-color-row input {
            flex: 1;
            height: 42px;
            border: 1.5px solid #E5E5EA;
            border-radius: 12px;
            padding: 0 14px;
            font-size: 15px;
            outline: none;
        }

        .add-color-row input:focus {
            border-color: var(--primary-start);
        }

        .add-color-row button {
            height: 42px;
            padding: 0 16px;
            border: 2px solid var(--success);
            background: white;
            color: var(--success);
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            white-space: nowrap;
        }

        /* 图片信息行 */
        .color-info-row {
            padding: 0 20px 8px;
            font-size: 13px;
            color: var(--text-secondary);
        }
        .color-info-row strong {
            color: var(--primary-start);
            font-weight: 600;
        }

        /* 拍照按钮 */
        .upload-section {
            padding: 16px 20px;
        }

        .upload-btn {
            width: 100%;
            height: 56px;
            background: linear-gradient(135deg, var(--primary-start), var(--primary-end));
            color: white;
            border: none;
            border-radius: var(--radius-btn);
            font-size: 17px;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 16px rgba(102,126,234,0.4);
        }

        .upload-btn:active {
            transform: scale(0.97);
        }

        .upload-btn:disabled {
            background: #C6C6C8;
            box-shadow: none;
        }

        /* 图片网格 */
        .image-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            padding: 12px 20px 16px;
        }

        .image-cell {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .image-item {
            aspect-ratio: 1;
            border-radius: 12px;
            overflow: hidden;
            position: relative;
            background: #F2F2F7;
            cursor: pointer;
        }

        .image-item img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .image-item .image-name {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 8px 4px 4px;
            background: linear-gradient(transparent, rgba(0,0,0,0.6));
            color: white;
            font-size: 10px;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .image-color-label {
            font-size: 11px;
            color: var(--text-secondary);
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            padding: 0 2px;
        }

        /* Toast */
        .toast {
            position: fixed;
            top: calc(80px + var(--safe-top));
            left: 50%;
            transform: translateX(-50%) translateY(-20px);
            background: rgba(0,0,0,0.8);
            backdrop-filter: blur(10px);
            color: white;
            padding: 12px 24px;
            border-radius: var(--radius-pill);
            font-size: 15px;
            font-weight: 500;
            z-index: 2000;
            opacity: 0;
            transition: all 0.3s ease;
            pointer-events: none;
            max-width: 80vw;
            text-align: center;
        }

        .toast.show {
            opacity: 1;
            transform: translateX(-50%) translateY(0);
        }

        .toast.success { background: rgba(52,199,89,0.9); }
        .toast.error { background: rgba(255,59,48,0.9); }

        /* 空状态 */
        .empty-state {
            padding: 32px 20px;
            text-align: center;
            color: var(--text-secondary);
        }

        .empty-state .icon { font-size: 40px; margin-bottom: 8px; }
        .empty-state .text { font-size: 14px; }

        /* 隐藏文件输入 */
        #file-input { display: none; }

        /* 侧滑删除 */
        .sku-swipe-wrap {
            position: relative;
            overflow: hidden;
        }
        .sku-swipe-content {
            position: relative;
            z-index: 1;
            background: var(--card);
            transition: transform 0.25s ease;
        }
        .sku-swipe-actions {
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 80px;
            z-index: 0;
        }
        .btn-delete {
            width: 80px;
            height: 100%;
            background: #FF3B30;
            color: white;
            border: none;
            font-size: 15px;
            font-weight: 600;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* 图片全屏预览 */
        .img-preview-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.95);
            z-index: 3000;
            display: none;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.25s;
        }
        .img-preview-overlay.show {
            display: flex;
            opacity: 1;
        }
        .img-preview-overlay img {
            max-width: 95vw;
            max-height: 90vh;
            object-fit: contain;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <!-- 导航栏 -->
    <div class="navbar">
        <span class="navbar-title">SKU拍照上传</span>
        <div class="navbar-actions">
            <button class="nav-icon-btn" id="sync-btn" onclick="triggerSync()" title="同步仓库数据">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                    <path d="M3 3v5h5"/>
                    <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                    <path d="M16 16h5v5"/>
                </svg>
            </button>
        </div>
    </div>

    <!-- 同步提示条 -->
    <div class="sync-bar" id="sync-bar"></div>

    <!-- 调试状态 -->
    <div id="debug-status" style="background:#FFF3CD;color:#856404;padding:8px 16px;font-size:12px;text-align:center;border-bottom:1px solid #FFEAA7;">页面加载中...</div>

    <!-- 手动输入SKU -->
    <div class="section-header">
        <span class="section-title">快速添加</span>
    </div>
    <div class="card">
        <div class="manual-input-row">
            <div class="manual-input-top">
                <input type="text" id="manual-sku" placeholder="输入货号" inputmode="text">
                <input type="text" id="manual-color" placeholder="颜色" inputmode="text">
                <button onclick="createAndSelect()">添加</button>
            </div>
        </div>
    </div>

    <!-- 搜索栏 - 独立浮动 -->
    <div class="search-bar-wrap">
        <div class="search-bar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8E8E93" stroke-width="2.5" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="7"/><line x1="16" y1="16" x2="22" y2="22"/></svg>
            <input type="text" id="sku-search" placeholder="搜索货号..." inputmode="search" oninput="filterSkuList()">
            <button class="search-clear" id="search-clear" onclick="clearSearch()">&times;</button>
        </div>
    </div>

    <!-- SKU列表 -->
    <div class="section-header">
        <span class="section-title">暂存货盘</span>
        <span class="section-count" id="sku-count">加载中...</span>
    </div>
    <div class="card">
        <div class="sku-list" id="sku-list">
            <div class="empty-state">
                <div class="icon">📦</div>
                <div class="text">正在加载SKU列表...</div>
            </div>
        </div>
    </div>

    <!-- 颜色选择 - 横向标签 -->
    <div id="color-section" style="display:none;">
        <div class="section-header">
            <span class="section-title">颜色</span>
            <span class="section-count" id="selected-sku-name"></span>
        </div>
        <div class="card" style="padding-top:12px;">
            <div class="color-tabs-wrap" id="color-tabs"></div>
            <div class="add-color-row" id="add-color-row" style="display:none;">
                <input type="text" id="new-color-input" placeholder="输入新颜色" inputmode="text">
                <button onclick="addColorToSku()">+ 追加</button>
            </div>
        </div>
    </div>

    <!-- 拍照上传 -->
    <div id="upload-section" style="display:none;">
        <div class="section-header">
            <span class="section-title">拍照上传</span>
            <span class="color-info-row" id="color-info"></span>
        </div>
        <div class="card">
            <div class="upload-section">
                <input type="file" id="file-input" accept="image/*" capture="environment" multiple>
                <button class="upload-btn" id="upload-btn" onclick="document.getElementById('file-input').click()">
                    拍照 / 选择照片
                </button>
            </div>
            <div class="image-grid" id="preview-grid"></div>
        </div>
    </div>

    <!-- 已上传图片 -->
    <div id="existing-section" style="display:none;">
        <div class="section-header">
            <span class="section-title">已上传图片</span>
            <span class="section-count" id="existing-count">0</span>
        </div>
        <div class="card">
            <div class="image-grid" id="existing-grid"></div>
        </div>
    </div>

    <!-- 图片全屏预览 -->
    <div class="img-preview-overlay" id="img-preview" onclick="closePreview()">
        <img id="preview-img" src="" alt="">
    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <script>
        var API_BASE = window.location.origin;
        var skus = [];
        var selectedSku = null;
        var selectedColor = null;
        var selectedFiles = [];

        // 加载仓库暂存
        function loadDrafts() {
            document.getElementById('sku-count').textContent = '正在加载...';
            document.getElementById('debug-status').textContent = 'JS已执行，正在请求API...';
            fetch(API_BASE + '/api/v1/warehouse/drafts?_t=' + Date.now())
                .then(function(res) {
                    document.getElementById('debug-status').textContent = 'API响应: ' + res.status + ', 大小: ' + res.headers.get('content-length');
                    return res.json();
                })
                .then(function(data) {
                    if (data.success && data.data.length > 0) {
                        skus = data.data;
                        renderSkuList();
                        document.getElementById('sku-count').textContent = skus.length + ' 个SKU';
                        document.getElementById('debug-status').textContent = '加载成功: ' + skus.length + ' 个SKU';
                    setTimeout(function() { document.getElementById('debug-status').style.display = 'none'; }, 3000);
                    } else {
                        document.getElementById('sku-count').textContent = '暂无数据';
                        document.getElementById('debug-status').textContent = 'API返回空数据: ' + JSON.stringify(data);
                        renderSkuList();
                    }
                })
                .catch(function(e) {
                    document.getElementById('sku-count').textContent = '加载失败';
                    document.getElementById('debug-status').textContent = '错误: ' + e.message;
                    renderSkuList();
                });
        }

        // 手动创建并选中SKU
        function createAndSelect() {
            var skuNo = document.getElementById('manual-sku').value.trim();
            var color = document.getElementById('manual-color').value.trim();
            if (!skuNo) { showToast('请输入货号', 'error'); return; }
            fetch(API_BASE + '/api/v1/skus/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sku_no: skuNo, color: color })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    showToast('SKU已添加', 'success');
                    document.getElementById('manual-sku').value = '';
                    document.getElementById('manual-color').value = '';
                    selectedSku = { '货号': skuNo, '颜色': color };
                    selectedColor = null;
                    if (color) {
                        renderColorList(parseColors(color));
                        document.getElementById('color-section').style.display = 'block';
                        document.getElementById('selected-sku-name').textContent = skuNo;
                    } else {
                        selectedColor = '';
                        document.getElementById('color-section').style.display = 'none';
                        document.getElementById('upload-section').style.display = 'block';
                        document.getElementById('selected-color-name').textContent = '默认';
                    }
                    document.getElementById('upload-section').scrollIntoView({ behavior: 'smooth' });
                } else {
                    showToast(data.message, 'error');
                }
            })
            .catch(function() { showToast('网络错误', 'error'); });
        }

        // 搜索筛选SKU
        function filterSkuList() {
            var keyword = document.getElementById('sku-search').value.trim().toLowerCase();
            var clearBtn = document.getElementById('search-clear');
            clearBtn.className = 'search-clear' + (keyword ? ' show' : '');
            var items = document.querySelectorAll('#sku-list .sku-item');
            for (var i = 0; i < items.length; i++) {
                var text = items[i].textContent.toLowerCase();
                items[i].style.display = text.indexOf(keyword) >= 0 ? '' : 'none';
            }
        }

        function clearSearch() {
            document.getElementById('sku-search').value = '';
            filterSkuList();
        }

        // 渲染SKU列表
        function renderSkuList() {
            var list = document.getElementById('sku-list');
            if (skus.length === 0) {
                list.innerHTML = '<div class="empty-state"><div class="icon">📭</div><div class="text">暂无仓库数据，请在上方手动输入货号</div></div>';
                return;
            }

            list.innerHTML = skus.map(function(sku, i) {
                var isSelected = selectedSku && selectedSku['货号'] === sku['货号'];
                var firstChar = (sku['货号'] || 'S').charAt(0).toUpperCase();
                var colors = parseColors(sku['颜色'] || '');
                var colorText = colors.length > 2 ? (colors[0] + '/' + colors[1] + '/...') : (sku['颜色'] || '无颜色');
                var source = sku['_source'] === 'local' ? '<span style="color:#FF9500;font-size:11px;margin-left:4px;">手动</span>' : '';
                var imgCount = sku['_image_count'] ? '<span style="color:#34C759;font-size:12px;">' + sku['_image_count'] + '张</span>' : '';
                var updateTime = sku['_updated_at'] ? '<span class="sku-time">' + formatTime(sku['_updated_at']) + '</span>' : '';

                return '<div class="sku-swipe-wrap" data-index="' + i + '">' +
                    '<div class="sku-swipe-actions"><button class="btn-delete" onclick="confirmDelete(' + i + ', event)">删除</button></div>' +
                    '<div class="sku-swipe-content sku-item ' + (isSelected ? 'selected' : '') + '" onclick="selectSku(' + i + ')">' +
                    '<div class="sku-icon">' + firstChar + '</div>' +
                    '<div class="sku-info">' +
                    '<div class="sku-no">' + sku['货号'] + source + '</div>' +
                    '<div class="sku-meta">' + colorText + updateTime + '</div>' +
                    '</div>' +
                    imgCount +
                    '<span class="sku-count" id="sku-count-' + sku['货号'] + '"></span>' +
                    '<span class="sku-arrow">›</span>' +
                    '</div></div>';
            }).join('');

            // 绑定侧滑事件
            initSwipe();
        }

        // 解析颜色
        function parseColors(colorStr) {
            if (!colorStr) return [];
            return colorStr.split(/[,/、，\s]+/).filter(function(c) { return c.trim(); });
        }

        function formatTime(ts) {
            if (!ts) return '';
            var d = new Date(ts.replace(' ', 'T'));
            if (isNaN(d.getTime())) return '';
            var now = new Date();
            var diff = (now - d) / 1000;
            if (diff < 60) return '刚刚';
            if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
            if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
            var m = d.getMonth() + 1;
            var day = d.getDate();
            var h = d.getHours();
            var min = ('0' + d.getMinutes()).slice(-2);
            return m + '/' + day + ' ' + h + ':' + min;
        }

        // 选择SKU
        function selectSku(index) {
            selectedSku = skus[index];
            selectedColor = null;
            selectedFiles = [];
            renderSkuList();

            var colors = parseColors(selectedSku['颜色'] || '');
            renderColorList(colors);

            document.getElementById('color-section').style.display = 'block';
            document.getElementById('upload-section').style.display = 'none';
            document.getElementById('existing-section').style.display = 'none';
            document.getElementById('selected-sku-name').textContent = selectedSku['货号'];
            document.getElementById('new-color-input').value = '';

            loadExistingImages(selectedSku['货号']);
            document.getElementById('color-section').scrollIntoView({ behavior: 'smooth' });
        }

        // 渲染颜色标签
        function renderColorList(colors) {
            var tabs = document.getElementById('color-tabs');
            var addRow = document.getElementById('add-color-row');
            if (colors.length === 0) {
                tabs.innerHTML = '<span style="color:var(--text-secondary);font-size:13px;">无颜色，请追加</span>';
                addRow.style.display = 'flex';
                return;
            }

            var html = colors.map(function(c) {
                return '<button class="color-tab ' + (selectedColor === c ? 'selected' : '') + '" onclick="selectColor(&apos;' + c + '&apos;)">' + c + '</button>';
            }).join('');
            html += '<button class="color-tab-add" onclick="toggleAddColor()">+</button>';
            tabs.innerHTML = html;
            addRow.style.display = 'none';
        }

        function toggleAddColor() {
            var addRow = document.getElementById('add-color-row');
            addRow.style.display = addRow.style.display === 'none' ? 'flex' : 'none';
            if (addRow.style.display === 'flex') {
                document.getElementById('new-color-input').focus();
            }
        }

        // 选择颜色
        function selectColor(color) {
            selectedColor = color;
            selectedFiles = [];
            renderColorList(parseColors(selectedSku['颜色'] || ''));

            document.getElementById('upload-section').style.display = 'block';
            document.getElementById('color-info').innerHTML = '当前: <strong>' + color + '</strong>';
            document.getElementById('preview-grid').innerHTML = '';
            filterExistingByColor();
            document.getElementById('upload-section').scrollIntoView({ behavior: 'smooth' });
        }

        // 追加颜色到当前SKU
        function addColorToSku() {
            if (!selectedSku) { showToast('请先选择SKU', 'error'); return; }
            var newColor = document.getElementById('new-color-input').value.trim();
            if (!newColor) { showToast('请输入颜色', 'error'); return; }

            var existing = selectedSku['颜色'] || '';
            var colors = parseColors(existing);
            if (colors.indexOf(newColor) >= 0) {
                showToast('该颜色已存在', 'error');
                return;
            }

            var updated = existing ? (existing + '，' + newColor) : newColor;
            selectedSku['颜色'] = updated;
            renderColorList(parseColors(updated));
            document.getElementById('new-color-input').value = '';
            document.getElementById('add-color-row').style.display = 'none';
            showToast('已追加颜色: ' + newColor, 'success');
        }

        // 加载已上传图片
        var allExistingImages = [];
        function loadExistingImages(skuNo) {
            fetch(API_BASE + '/api/v1/skus/' + encodeURIComponent(skuNo) + '/images')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success && data.data.length > 0) {
                        allExistingImages = data.data;
                        // 解析每张图的颜色
                        for (var i = 0; i < allExistingImages.length; i++) {
                            allExistingImages[i]._color = parseColorFromFilename(allExistingImages[i].file_name);
                        }
                        filterExistingByColor();

                        var countEl = document.getElementById('sku-count-' + skuNo);
                        if (countEl) {
                            countEl.textContent = data.data.length + '张';
                        }
                    } else {
                        allExistingImages = [];
                        document.getElementById('existing-section').style.display = 'none';
                    }
                })
                .catch(function() {
                    allExistingImages = [];
                    document.getElementById('existing-section').style.display = 'none';
                });
        }

        // 从文件名解析颜色：测试-红色-1.jpg -> 红色
        function parseColorFromFilename(filename) {
            if (!selectedSku) return '';
            var skuNo = selectedSku['货号'];
            var base = filename;
            // 去掉扩展名
            var dotIdx = base.lastIndexOf('.');
            if (dotIdx > 0) base = base.substring(0, dotIdx);
            // 去掉sku_no前缀
            if (base.indexOf(skuNo + '-') === 0) {
                base = base.substring(skuNo.length + 1);
            }
            // 去掉末尾的 -数字（序号）
            base = base.replace(/-\d+$/, '');
            return base;
        }

        // 按颜色过滤已上传图片
        function filterExistingByColor() {
            var section = document.getElementById('existing-section');
            var grid = document.getElementById('existing-grid');
            var countEl = document.getElementById('existing-count');

            if (allExistingImages.length === 0) {
                section.style.display = 'none';
                return;
            }

            var filtered = allExistingImages;
            if (selectedColor !== null && selectedColor !== '') {
                filtered = allExistingImages.filter(function(img) {
                    return img._color === selectedColor;
                });
            }

            if (filtered.length === 0) {
                section.style.display = 'none';
                return;
            }

            section.style.display = 'block';
            countEl.textContent = filtered.length + ' 张';
            grid.innerHTML = filtered.map(function(img) {
                var thumb = img.url + '/thumb';
                return '<div class="image-cell">' +
                    '<div class="image-item" onclick="openPreview(&apos;' + img.url + '&apos;)">' +
                    '<img src="' + thumb + '" alt="' + img.file_name + '" loading="lazy">' +
                    '<div class="image-name">' + img.file_name + '</div>' +
                    '</div>' +
                    '<div class="image-color-label">' + (img._color || '') + '</div>' +
                    '</div>';
            }).join('');
        }

        // 文件选择变化
        document.getElementById('file-input').addEventListener('change', function(e) {
            selectedFiles = Array.from(e.target.files);
            if (selectedFiles.length > 0) {
                showPreview(selectedFiles);
                uploadFiles();
            }
        });

        // 显示预览
        function showPreview(files) {
            var grid = document.getElementById('preview-grid');
            grid.innerHTML = files.map(function(f) {
                return '<div class="image-item"><img src="' + URL.createObjectURL(f) + '" alt="' + f.name + '"><div class="image-name">' + f.name + '</div></div>';
            }).join('');
        }

        // 压缩图片
        function compressImage(file) {
            return new Promise(function(resolve) {
                var reader = new FileReader();
                reader.onload = function(e) {
                    var img = new Image();
                    img.onload = function() {
                        var w = img.width, h = img.height;
                        var maxW = 1200;
                        if (w > maxW) { h = Math.round(h * maxW / w); w = maxW; }
                        var canvas = document.createElement('canvas');
                        canvas.width = w; canvas.height = h;
                        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
                        canvas.toBlob(function(blob) {
                            resolve(new File([blob], file.name, { type: 'image/jpeg' }));
                        }, 'image/jpeg', 0.6);
                    };
                    img.src = e.target.result;
                };
                reader.readAsDataURL(file);
            });
        }

        // 上传单张带进度
        function uploadOne(file, skuNo, color, onProgress) {
            return new Promise(function(resolve, reject) {
                var formData = new FormData();
                formData.append('color', color || '');
                formData.append('images', file);

                var xhr = new XMLHttpRequest();
                xhr.open('POST', API_BASE + '/api/v1/skus/' + encodeURIComponent(skuNo) + '/upload');
                xhr.upload.onprogress = function(e) {
                    if (e.lengthComputable && onProgress) onProgress(e.loaded, e.total);
                };
                xhr.onload = function() {
                    try { resolve(JSON.parse(xhr.responseText)); }
                    catch(err) { reject(err); }
                };
                xhr.onerror = function() { reject(new Error('网络错误')); };
                xhr.send(formData);
            });
        }

        // 上传文件
        function uploadFiles() {
            if (!selectedSku || selectedColor === null || selectedFiles.length === 0) return;

            var btn = document.getElementById('upload-btn');
            var total = selectedFiles.length;
            var done = 0;
            btn.disabled = true;
            btn.innerHTML = '⏳ 压缩中...';

            // 逐张压缩 + 上传，显示进度
            var chain = Promise.resolve();
            selectedFiles.forEach(function(f, idx) {
                chain = chain.then(function() {
                    btn.innerHTML = '⏳ 压缩 ' + (idx + 1) + '/' + total;
                    var needCompress = f.size > 300000;
                    return needCompress ? compressImage(f) : f;
                }).then(function(compressed) {
                    btn.innerHTML = '⬆️ 上传 ' + (idx + 1) + '/' + total;
                    return uploadOne(compressed, selectedSku['货号'], selectedColor, function(loaded, t) {
                        var pct = Math.round(loaded / t * 100);
                        btn.innerHTML = '⬆️ 上传 ' + (idx + 1) + '/' + total + ' ' + pct + '%';
                    });
                }).then(function(data) {
                    done++;
                });
            });

            chain.then(function() {
                showToast('上传完成！' + done + '张', 'success');
                selectedFiles = [];
                document.getElementById('preview-grid').innerHTML = '';
                document.getElementById('file-input').value = '';
                loadExistingImages(selectedSku['货号']);
            }).catch(function() {
                showToast('部分上传失败', 'error');
            }).then(function() {
                btn.disabled = false;
                btn.innerHTML = '📷 拍照 / 选择照片';
            });
        }

        // 侧滑删除
        function initSwipe() {
            var wraps = document.querySelectorAll('.sku-swipe-wrap');
            for (var w = 0; w < wraps.length; w++) {
                (function(wrap) {
                    var content = wrap.querySelector('.sku-swipe-content');
                    var startX = 0, moveX = 0, isOpen = false;
                    content.addEventListener('touchstart', function(e) {
                        startX = e.touches[0].clientX;
                        if (isOpen) { content.style.transform = 'translateX(0)'; isOpen = false; }
                    }, { passive: true });
                    content.addEventListener('touchmove', function(e) {
                        moveX = e.touches[0].clientX - startX;
                        if (moveX < 0) {
                            content.style.transform = 'translateX(' + Math.max(moveX, -80) + 'px)';
                        }
                    }, { passive: true });
                    content.addEventListener('touchend', function() {
                        if (moveX < -50) {
                            content.style.transform = 'translateX(-80px)';
                            isOpen = true;
                        } else {
                            content.style.transform = 'translateX(0)';
                            isOpen = false;
                        }
                        moveX = 0;
                    });
                })(wraps[w]);
            }
        }

        function confirmDelete(index, e) {
            e.stopPropagation();
            var sku = skus[index];
            if (confirm('确定删除 SKU: ' + sku['货号'] + ' ?')) {
                fetch(API_BASE + '/api/v1/skus/' + encodeURIComponent(sku['货号']) + '/delete', { method: 'POST' })
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.success) {
                            showToast('已删除', 'success');
                            loadDrafts();
                        } else {
                            showToast(d.message || '删除失败', 'error');
                        }
                    })
                    .catch(function() { showToast('网络错误', 'error'); });
            }
        }

        // 图片全屏预览
        function openPreview(url) {
            document.getElementById('preview-img').src = url;
            var overlay = document.getElementById('img-preview');
            overlay.style.display = 'flex';
            setTimeout(function() { overlay.classList.add('show'); }, 10);
        }

        function closePreview() {
            var overlay = document.getElementById('img-preview');
            overlay.classList.remove('show');
            setTimeout(function() {
                overlay.style.display = 'none';
                document.getElementById('preview-img').src = '';
            }, 250);
        }

        // Toast
        function showToast(msg, type) {
            var toast = document.getElementById('toast');
            toast.textContent = msg;
            toast.className = 'toast ' + (type || '') + ' show';
            setTimeout(function() { toast.className = 'toast'; }, 2500);
        }

        // 仓库同步 - 触发Mac推送
        function triggerSync() {
            var btn = document.getElementById('sync-btn');
            btn.classList.add('syncing');
            showSyncBar('已通知Mac同步，请稍候...');

            fetch(API_BASE + '/api/v1/warehouse/sync-request', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        // 轮询等待Mac推送完成
                        pollSyncComplete();
                    } else {
                        showSyncBar('触发失败', true);
                        btn.classList.remove('syncing');
                    }
                })
                .catch(function() {
                    showSyncBar('网络错误', true);
                    btn.classList.remove('syncing');
                });
        }

        function pollSyncComplete() {
            var tries = 0;
            var timer = setInterval(function() {
                tries++;
                fetch(API_BASE + '/api/v1/warehouse/drafts?_t=' + Date.now())
                    .then(function(r) { return r.json(); })
                    .then(function(d) {
                        if (d.success && d.data) {
                            skus = d.data;
                            renderSkuList();
                            document.getElementById('sku-count').textContent = skus.length + ' 个SKU';
                            showSyncBar('同步完成！' + skus.length + ' 个SKU');
                            setTimeout(hideSyncBar, 1500);
                            document.getElementById('sync-btn').classList.remove('syncing');
                            clearInterval(timer);
                        }
                    });
                if (tries >= 20) {
                    showSyncBar('同步超时，请确认Mac在线', true);
                    document.getElementById('sync-btn').classList.remove('syncing');
                    clearInterval(timer);
                }
            }, 3000);
        }

        function showSyncBar(msg, isError) {
            var bar = document.getElementById('sync-bar');
            bar.textContent = msg;
            bar.className = 'sync-bar show' + (isError ? ' error' : '');
        }

        function hideSyncBar() {
            document.getElementById('sync-bar').className = 'sync-bar';
        }

        // 页面加载
        loadDrafts();
    </script>
</body>
</html>''')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route("/")
def redirect_to_app():
    from flask import redirect
    return redirect("/app", code=302)


class APIServer:
    def __init__(self):
        self.thread = None
        self.running = False
        self.port = config["api_port"]

    def start(self):
        if self.running:
            return
        init_db()
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        app.run(host="0.0.0.0", port=self.port, debug=False, use_reloader=False)

    def stop(self):
        self.running = False

    def is_running(self):
        return self.running



if __name__ == "__main__":
    init_db()
    print("Starting API server on port 8765...")
    app.run(host="0.0.0.0", port=8765, debug=False, use_reloader=False)

