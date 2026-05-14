#!/bin/bash
# 将本地 sku.db 推送到远程服务器
LOCAL_DB="/Volumes/Ryan/仓库货盘/仓库系统数据/sku.db"
SERVER="http://81.71.19.125/api/v1/warehouse/push"

if [ ! -f "$LOCAL_DB" ]; then
    exit 0
fi

curl -s -X POST "$SERVER" \
    -F "db_file=@$LOCAL_DB" \
    --connect-timeout 10 \
    --max-time 30 > /dev/null 2>&1
