#!/bin/bash
# Mac端同步脚本 - 轮询服务器，有请求时推送 sku.db
LOCAL_DB="/Volumes/Ryan/仓库货盘/仓库系统数据/sku.db"
SERVER="http://81.71.19.125"

while true; do
    # 检查是否有同步请求
    PENDING=$(curl -s --connect-timeout 5 --max-time 10 "$SERVER/api/v1/warehouse/check-sync" 2>/dev/null)

    if echo "$PENDING" | grep -q '"pending":true'; then
        if [ -f "$LOCAL_DB" ]; then
            curl -s -X POST "$SERVER/api/v1/warehouse/push" \
                -F "db_file=@$LOCAL_DB" \
                --connect-timeout 10 \
                --max-time 30 > /dev/null 2>&1
        fi
    fi

    sleep 30
done
