# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SKU 拍照上传工具 — 为电商团队设计的移动端 Web 应用，用于仓库 SKU 商品图拍摄、管理和同步。手机端拍照/上传，Mac 端同步到仓库系统。

## Architecture

**单体架构** — 所有逻辑集中在 `api_server.py`（~2000 行），包含 Flask 后端 + 嵌入式 HTML/CSS/JS 前端。无构建工具，无前端框架。

### 核心文件

| 文件 | 职责 |
|------|------|
| `api_server.py` | Flask 应用 + 全部 API 端点 + 嵌入式移动端前端（iOS 风格） |
| `database.py` | SQLite 操作层（`sku_index.db`：Web 应用数据） |
| `sku_manager.py` | SKU 业务逻辑（创建、图片追加、删除、导出） |
| `warehouse_sync.py` | 读取仓库系统 `sku.db`（暂存货盘数据） |
| `config.py` | 配置加载（`settings.json`），含数据库路径、端口等 |
| `ui_app.py` | macOS 桌面 GUI（tkinter，独立于 Web 应用） |
| `sync_to_server.sh` | Mac → 服务器同步脚本（crontab 每 30 秒轮询） |

### 双数据库设计

- **`sku_index.db`**（Web 应用）：`sku_index` 表 + `sku_images` 表，管理手机端创建的 SKU 和图片
- **`sku.db`**（仓库系统）：`skus` 表，`status='draft'` 为暂存货盘，含中文字段名（货号、颜色、品名等）

### 数据同步流程

```
手机 Web → api_server.py → sku_index.db
                        ↕ (Mac 轮询)
Mac 仓库系统 ← sync_to_server.sh ← sku.db
```

手机端触发同步请求 → Mac 脚本检测到请求 → 推送 sku.db 到服务器 → 拉取新图片和新 SKU

## JavaScript Compatibility Rules

**必须使用 `var`，不能用 `const`/`let`** — 旧版 iOS WebView 不支持。
**必须使用 `.then()`，不能用 `async/await`** — 同上。
**Python 字符串中的单引号用 `&apos;`** — 因为 HTML 嵌在 Python 三引号字符串里，`\'` 会导致转义问题。

## API Endpoints

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/warehouse/drafts` | GET | 获取仓库暂存 SKU 列表 |
| `/api/v1/skus/create` | POST | 创建 SKU（支持追加颜色） |
| `/api/v1/skus/<sku_no>/upload` | POST | 上传图片（multipart，带 color 字段） |
| `/api/v1/skus/<sku_no>/images` | GET | 获取 SKU 已有图片列表 |
| `/api/v1/skus/<sku_no>/delete` | POST | 删除 SKU |
| `/api/v1/skus/<sku_no>/images/reorder` | POST | 重排图片顺序 |
| `/api/v1/skus/<sku_no>/images/delete-batch` | POST | 批量删除图片 |
| `/api/v1/warehouse/sync-request` | POST | 触发 Mac 同步 |
| `/api/v1/warehouse/check-sync` | GET | Mac 检查是否有同步请求 |
| `/api/v1/warehouse/push` | POST | Mac 推送 sku.db |
| `/api/v1/sync/new-skus` | GET | Mac 拉取手机端新建的 SKU |
| `/api/v1/sync/images` | GET | Mac 拉取图片列表 |

## Deployment

### 服务器（Ubuntu 81.71.19.125）

```bash
# 部署
sshpass -p 'Wealth123@' scp api_server.py ubuntu@81.71.19.125:/home/ubuntu/sku_app/
sshpass -p 'Wealth123@' ssh ubuntu@81.71.19.125 "sudo systemctl restart sku-app"

# 查看日志
ssh ubuntu@81.71.19.125 "sudo journalctl -u sku-app -f --no-pager"
```

- systemd 服务：`sku-app.service`
- nginx 反向代理：80 → 8765
- 数据目录：`/home/ubuntu/sku_app/data/`

### Mac 本地

```bash
# 运行 Web 应用
python3 main.py  # 启动 GUI + API server (port 8765)

# 同步脚本（crontab）
* * * * * /Users/apple/bin/sku-sync.sh
* * * * * sleep 30 && /Users/apple/bin/sku-sync.sh
```

## Frontend Architecture

嵌入式 SPA，所有 CSS/JS 内联在 `api_server.py` 的 `index()` 函数中。

关键机制：
- **骨架屏**：页面加载时显示 5 个 shimmer 占位卡片
- **localStorage 缓存**：SKU 列表缓存到 `sku_cache`，二次打开秒渲染
- **并行处理**：`parallelRun(tasks, limit)` 并发控制器，压缩 5 并发、上传 3 并发
- **图片压缩**：Canvas API，1200px 最大宽度，0.6 质量，>300KB 才压缩
- **缩略图**：服务端 Pillow 生成（400px 宽，质量 70），带 EXIF 方向校正
- **颜色解析**：从文件名提取颜色（`{sku_no}-{color}-{seq}.ext`）
- **双指缩放**：全屏预览支持 pinch-to-zoom + 拖拽平移
- **下拉刷新**：touch 事件实现

## Git Conventions

版本号格式：`vX.Y: 简要描述`
示例：`v1.8: 7项产品体验优化 - 状态/搜索/删除/压缩/空状态`
