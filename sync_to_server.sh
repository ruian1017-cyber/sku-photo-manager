#!/bin/bash
# Mac端同步脚本 - 轮询服务器，同步数据库和图片
LOCAL_DB="/Volumes/Ryan/仓库货盘/仓库系统数据/sku.db"
UPLOADS_DIR="/Volumes/Ryan/仓库货盘/仓库系统数据/uploads/thumbs"
SERVER="http://81.71.19.125"

while true; do
    # 检查是否有同步请求
    PENDING=$(curl -s --connect-timeout 5 --max-time 10 "$SERVER/api/v1/warehouse/check-sync" 2>/dev/null)

    if echo "$PENDING" | grep -q '"pending":true'; then
        # 1. 推送数据库
        if [ -f "$LOCAL_DB" ]; then
            curl -s -X POST "$SERVER/api/v1/warehouse/push" \
                -F "db_file=@$LOCAL_DB" \
                --connect-timeout 10 --max-time 30 > /dev/null 2>&1
        fi
    fi

    # 2. 拉取服务器上的新SKU（手机端创建的）
    NEW_SKUS_JSON=$(curl -s --connect-timeout 5 --max-time 15 "$SERVER/api/v1/sync/new-skus" 2>/dev/null)
    if echo "$NEW_SKUS_JSON" | grep -q '"success":true'; then
        echo "$NEW_SKUS_JSON" | python3 -c "
import json, sys, sqlite3
from datetime import datetime

data = json.load(sys.stdin)
if not data.get('success') or not data.get('data'):
    sys.exit(0)

local_db = '$LOCAL_DB'
conn = sqlite3.connect(local_db)
conn.row_factory = sqlite3.Row

local_nos = set()
for row in conn.execute('SELECT 货号 FROM skus WHERE deleted_at IS NULL'):
    local_nos.add(row[0])

added = 0
for sku in data['data']:
    if sku['货号'] in local_nos:
        continue
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        'INSERT INTO skus (货号, 颜色, status, created_at, updated_at) VALUES (?, ?, \"draft\", ?, ?)',
        (sku['货号'], sku.get('颜色', ''), now, now)
    )
    added += 1

conn.commit()
conn.close()
if added > 0:
    print(f'Added {added} new SKUs')
" 2>/dev/null
    fi

    # 3. 拉取服务器上的新图片
    IMAGES_JSON=$(curl -s --connect-timeout 5 --max-time 15 "$SERVER/api/v1/sync/images" 2>/dev/null)
    if echo "$IMAGES_JSON" | grep -q '"success":true'; then
        # 遍历每个SKU的图片
        echo "$IMAGES_JSON" | python3 -c "
import json, sys, urllib.request, os, sqlite3

data = json.load(sys.stdin)
if not data.get('success'):
    sys.exit(0)

server_url = '$SERVER'
local_db = '$LOCAL_DB'
uploads_dir = '$UPLOADS_DIR'
os.makedirs(uploads_dir, exist_ok=True)

conn = sqlite3.connect(local_db)
conn.row_factory = sqlite3.Row

# 获取本地已有的图片
local_images = set()
for row in conn.execute('SELECT 图片列表 FROM skus WHERE 图片列表 IS NOT NULL AND 图片列表 != \"\"'):
    try:
        imgs = json.loads(row[0])
        for img in imgs:
            local_images.add(os.path.basename(img))
    except:
        pass

synced = 0
for sku_no, images in data['data'].items():
    for img in images:
        fname = img['file_name']
        # 跳过已存在的
        if fname in local_images:
            continue
        # 下载图片
        url = f'{server_url}/api/v1/sync/images/{sku_no}/{fname}'
        try:
            save_path = os.path.join(uploads_dir, fname)
            urllib.request.urlretrieve(url, save_path)
            synced += 1
            # 更新 sku.db 图片列表
            rel_path = f'uploads/thumbs/{fname}'
            for row in conn.execute('SELECT 图片列表 FROM skus WHERE 货号 = ?', (sku_no,)):
                existing = row[0] or '[]'
                try:
                    imgs = json.loads(existing)
                except:
                    imgs = []
                imgs.append(rel_path)
                conn.execute('UPDATE skus SET 图片列表 = ? WHERE 货号 = ?', (json.dumps(imgs), sku_no))
                break
            else:
                # SKU不在本地db中，跳过
                pass
        except:
            pass

conn.commit()
conn.close()
if synced > 0:
    print(f'Synced {synced} images')
" 2>/dev/null
    fi

    sleep 30
done
