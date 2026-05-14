# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SKU 拍照上传工具 — 为电商团队设计的移动端 Web 应用，用于仓库 SKU 商品图拍摄、管理和同步。手机端拍照/上传，Mac 端同步到仓库系统。

## Architecture

**单体架构** — 所有逻辑集中在 `api_server.py`（~2300 行），包含 Flask 后端 + 嵌入式 HTML/CSS/JS 前端。无构建工具，无前端框架。

### 核心文件

| 文件 | 职责 |
|------|------|
| `api_server.py` | Flask 应用 + 全部 API 端点 + 嵌入式移动端前端（iOS 风格） |
| `database.py` | SQLite 操作层（3 张表：`sku_index`、`sku_images`、`deleted_skus`） |
| `sku_manager.py` | SKU 业务逻辑（创建、图片追加、删除、导出） |
| `warehouse_sync.py` | 读取仓库系统 `sku.db`（暂存货盘数据） |
| `config.py` | 配置加载（`settings.json`），含数据库路径、端口等 |
| `sync_to_server.sh` | Mac → 服务器同步脚本（crontab 每 30 秒轮询） |

### 三张数据库表

- **`sku_index`**：SKU 主表（货号、文件夹路径、图片计数、颜色、时间戳）
- **`sku_images`**：图片明细表（货号、文件名、序号、文件路径），外键关联 sku_index
- **`deleted_skus`**：手机端删除记录（防误删保护），Mac 同步时过滤这些货号

### 双数据库设计

- **`sku_index.db`**（Web 应用，服务器）：手机端操作的数据
- **`sku.db`**（仓库系统，Mac）：`skus` 表，`status='draft'` 为暂存货盘，含中文字段名

### 数据同步流程

```
手机 Web → api_server.py → sku_index.db（服务器）
                        ↕ (Mac 轮询每30秒)
Mac 仓库系统 ← sync_to_server.sh ← sku.db
```

手机端触发同步请求 → Mac 脚本检测到请求 → 推送 sku.db 到服务器 → 拉取新图片和新 SKU

### 防误删保护

手机端删除 SKU 时，货号被记录到 `deleted_skus` 表。Mac 同步推送 `sku.db` 后，加载暂存列表时自动过滤这些货号，确保手机端删除不会被仓库数据"复活"。撤销删除时清除 `deleted_skus` 记录。

## JavaScript Compatibility Rules

**必须使用 `var`，不能用 `const`/`let`** — 旧版 iOS WebView 不支持。
**必须使用 `.then()`，不能用 `async/await`** — 同上。
**Python 字符串中的单引号用 `&apos;`** — 因为 HTML 嵌在 Python 三引号字符串里，`\'` 会导致转义问题。

## API Endpoints

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/warehouse/drafts` | GET | 获取仓库暂存 SKU 列表（过滤 deleted_skus） |
| `/api/v1/skus/create` | POST | 创建 SKU（支持追加颜色） |
| `/api/v1/skus/<sku_no>/upload` | POST | 上传图片（multipart，带 color 字段） |
| `/api/v1/skus/<sku_no>/images` | GET | 获取 SKU 已有图片列表 |
| `/api/v1/skus/<sku_no>/delete` | POST | 删除 SKU（同时记录到 deleted_skus） |
| `/api/v1/skus/<sku_no>/unmark-delete` | POST | 撤销删除标记 |
| `/api/v1/skus/<sku_no>/images/reorder` | POST | 重排图片顺序 |
| `/api/v1/skus/<sku_no>/images/delete-batch` | POST | 批量删除图片 |
| `/api/v1/warehouse/sync-request` | POST | 触发 Mac 同步 |
| `/api/v1/warehouse/check-sync` | GET | Mac 检查是否有同步请求 |
| `/api/v1/warehouse/push` | POST | Mac 推送 sku.db |
| `/api/v1/sync/new-skus` | GET | Mac 拉取手机端新建的 SKU |
| `/api/v1/sync/images` | GET | Mac 拉取图片列表（中文文件名需 URL 编码） |

## Deployment

### 服务器（Ubuntu 81.71.19.125）

```bash
# 部署 api_server.py + database.py
sshpass -p 'Wealth123@' scp api_server.py database.py ubuntu@81.71.19.125:/home/ubuntu/sku_app/
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

# 同步脚本（crontab，注意必须用 ~/bin/ 路径，Desktop 路径有 macOS 权限问题）
* * * * * /Users/apple/bin/sku-sync.sh
* * * * * sleep 30 && /Users/apple/bin/sku-sync.sh
```

同步脚本修改后需同步到 `~/bin/sku-sync.sh`：
```bash
cp sync_to_server.sh ~/bin/sku-sync.sh && chmod +x ~/bin/sku-sync.sh
```

## Frontend Architecture

嵌入式 SPA，所有 CSS/JS 内联在 `api_server.py` 的 `index()` 函数中。

关键机制：
- **骨架屏**：页面加载时显示 5 个 shimmer 占位卡片
- **localStorage 缓存**：SKU 列表缓存到 `sku_cache`，二次打开秒渲染
- **并行处理**：`parallelRun(tasks, limit, maxRetries)` 并发控制器，带 completed 守卫防止重试重复执行
- **图片上传**：直接上传原图（不做客户端压缩），保留高清画质用于抖店等平台对接
- **缩略图**：服务端 Pillow 按需生成（400px 宽，质量 70），带 EXIF 方向校正，缓存到 `thumbs/`
- **颜色命名**：文件名格式 `{sku_no}-{颜色}-{序号}.ext`，颜色从文件名解析
- **双指缩放**：全屏预览支持 pinch-to-zoom + 拖拽平移
- **下拉刷新**：touch 事件实现
- **批量操作**：批量删除图片、图片排序（左右箭头）
- **删除确认**：iOS 风格底部面板 + 5 秒撤销功能

## Git Conventions

版本号格式：`vX.Y: 简要描述`
示例：`v1.8: 7项产品体验优化 - 状态/搜索/删除/压缩/空状态`

修复类提交：`fix: 简要描述`
功能类提交：`feat: 简要描述`
