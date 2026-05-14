# SKU拍照上传工具 - 前端设计提示词

## 功能清单

### 核心流程
1. **SKU列表浏览** - 展示所有货号，支持搜索筛选
2. **手动添加SKU** - 输入货号+颜色，快速创建
3. **颜色选择** - 每个SKU支持多颜色，可追加新颜色
4. **拍照/上传** - 支持手机拍照和相册选择，多张批量上传
5. **图片预览** - 已上传图片缩略图网格展示
6. **全屏查看** - 点击图片全屏预览原图
7. **侧滑删除** - 左滑SKU项露出删除按钮
8. **上传进度** - 逐张压缩+上传，显示百分比进度

### 辅助功能
- 仓库数据自动同步（暂存货盘列表）
- 手动添加的SKU与仓库数据合并显示
- 图片服务端缩略图（节省流量）
- 客户端压缩（1200px/0.6质量，>300KB才压缩）
- 来源标记（仓库/手动）

---

## 设计参考风格

参考以下顶流设计趋势：

### 1. iOS 18 风格 (Apple Human Interface Guidelines)
- 毛玻璃导航栏 (backdrop-filter: blur)
- 圆角卡片 (16px border-radius)
- SF Pro 字体系统
- 安全区域适配 (safe-area-inset)
- 细线分割线 (0.5px)
- 渐变紫色主色调 (#667eea → #764ba2)

### 2. 参考 App 设计
- **Shopify** - 商品管理、图片上传流程
- **闲鱼** - 二手商品发布、拍照上传
- **得物** - 商品详情图、多图展示
- **小红书** - 图片选择器、滤镜预览
- **Apple Store** - 产品列表卡片设计

### 3. 2025-2026 设计趋势
- **Glassmorphism** - 毛玻璃效果、半透明背景
- **Neumorphism 2.0** - 柔和阴影、微妙立体感
- **大圆角卡片** - 16-24px 圆角
- **渐变色按钮** - 紫蓝渐变、绿松石渐变
- **微动效** - 按压缩放、列表入场动画
- **深色模式** - 暗色背景、高对比度文字
- **底部安全区** - iPhone 底部手势条适配

---

## 设计提示词（英文，直接用于AI生图）

### Prompt 1: 整体页面概览

```
Design a modern mobile app UI for a SKU photo management tool, iOS 18 style.

The app has these sections from top to bottom:

1. **Navigation Bar**: Frosted glass effect, title "SKU拍照上传", centered
2. **Quick Add Section**: A card with two input fields (SKU number, Color) and an "Add" button with purple gradient
3. **SKU List**: Scrollable card list showing SKU items, each with:
   - Left: Circular gradient icon with first letter of SKU
   - Center: SKU number (bold) + color tags
   - Right: Image count badge + chevron arrow
   - Swipe-to-left reveals red delete button
4. **Search Bar**: Floating search input above the SKU list with magnifying glass icon, rounded pill shape, subtle shadow

Design style: Clean, minimal, iOS-native feel. Use SF Pro font. Colors: white cards on #F2F2F7 background, purple gradient (#667eea to #764ba2) for primary actions. 16px border radius on cards. 0.5px separator lines.

Show this as an iPhone 15 Pro mockup, full screen, with status bar.
```

### Prompt 2: SKU详情 + 颜色选择

```
Design a mobile app screen showing SKU detail view with color selection, iOS 18 style.

Layout:
1. **Breadcrumb**: "SKU列表 > A2301" at top
2. **Color Selection Card**: Grid of pill-shaped color buttons (红/蓝/绿/黑/白), selected state shows gradient fill with checkmark, unselected shows outline. Plus an "Add Color" input with green border button.
3. **Photo Upload Card**: Large purple gradient button "📷 拍照 / 选择照片" with camera icon, full width, 56px height, rounded corners, subtle shadow
4. **Upload Progress**: "⬆️ 上传 2/3 67%" text with progress bar
5. **Photo Grid**: 3-column grid of uploaded product photos, each with rounded corners (12px), subtle shadow, filename label at bottom with gradient overlay

Design: iOS native, clean whitespace, card-based layout. Purple accent color (#667eea). Smooth transitions. iPhone 15 Pro frame.
```

### Prompt 3: 图片全屏预览

```
Design a full-screen image preview overlay for a mobile app, iOS style.

- Dark overlay background (rgba 0,0,0,0.95)
- Centered product photo, max 95vw width, max 90vh height
- Subtle rounded corners (4px) on the image
- Tap anywhere to dismiss
- Smooth fade-in animation
- Status bar hidden for immersive view
- No UI chrome, just the photo and dark background

Show as iPhone 15 Pro mockup, the image is a product detail photo of clothing.
```

### Prompt 4: 搜索 + 筛选状态

```
Design a mobile app search experience, iOS 18 style.

- Search bar at top: rounded pill shape, white background, subtle shadow, magnifying glass icon on left, placeholder "搜索货号...", clear button (×) on right when active
- Below search bar: filtered SKU list showing only matching items
- Each SKU row: left icon, SKU number with search keyword highlighted in purple, color text, image count
- Empty state when no results: large icon + "未找到匹配的货号" text
- Search bar should be visually prominent but not dominating

Clean, minimal design. iOS native feel. iPhone 15 Pro mockup.
```

### Prompt 5: 侧滑删除交互

```
Design a swipe-to-delete interaction for a mobile app list, iOS Mail style.

Show 3 states side by side:
1. **Normal state**: SKU list item with white background, content visible
2. **Swiping state**: Item sliding left, red delete button partially revealed on the right
3. **Delete revealed state**: Item shifted left 80px, red "删除" button fully visible on right

The delete button: full height, red background (#FF3B30), white text "删除", bold.
Content layer has white background covering the delete button when not swiped.

iOS native feel, smooth animation. iPhone 15 Pro frame.
```

---

## 关键设计要求

1. **搜索栏位置** - 当前放在SKU列表卡片内部，太丑且不直观。应改为：
   - 独立浮动在SKU列表上方
   - 圆角药丸形状，带阴影
   - 左侧搜索图标，右侧清除按钮
   - 与导航栏保持视觉层次区分

2. **移动端优先** - 所有交互必须适合手指操作：
   - 按钮最小 44x44pt
   - 输入框高度 48px
   - 间距充足，避免误触

3. **性能感知** - 加载状态要有视觉反馈：
   - 骨架屏加载
   - 上传进度百分比
   - 图片懒加载

4. **一致性** - 整个App使用统一的设计语言：
   - 统一的圆角、阴影、间距
   - 统一的配色方案
   - 统一的字体层级
