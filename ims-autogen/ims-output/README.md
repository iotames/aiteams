# 进销存管理系统 (IMS) v1.0 MVP

库存管理、销售、采购 — 一体化管理系统。

## 技术栈

- **后端**: Python Flask + SQLAlchemy + SQLite
- **前端**: HTML5 + CSS3 + JavaScript（原生 SPA，无框架依赖）
- **运行**: Python 3.9+ 直接运行，无需编译

## 快速启动

### Windows
```bash
start.bat
```

### macOS / Linux
```bash
chmod +x start.sh && ./start.sh
```

### 手动启动
```bash
pip install -r requirements.txt
python start.py
```

访问 http://127.0.0.1:5000

## 功能模块

| 模块 | 功能 |
|------|------|
| 📊 工作台 | 仪表盘概览、快捷入口 |
| 📦 商品 | 商品CRUD、分类管理、单位管理 |
| 👥 基础数据 | 供应商管理、客户管理 |
| 🛒 采购 | 采购订单创建/编辑/删除/入库确认 |
| 💰 销售 | 销售订单创建/编辑/删除/出库确认 |
| 📋 库存 | 库存查询、库存流水、低库存预警 |
| 📈 报表 | 进销存汇总、销售明细 |

## API 接口

所有接口均位于 `/api/v1/` 下，返回统一 JSON 格式：
```json
{"success": true, "data": {...}, "message": "操作成功"}
```

## 项目结构

```
ims/
├── backend/           # Python 后端
│   ├── app.py         # Flask 应用入口
│   ├── models/        # 数据模型
│   ├── routes/        # API 路由
│   ├── services/      # 业务逻辑
│   └── utils/         # 工具函数
├── frontend/          # 前端
│   ├── index.html     # 主页面
│   ├── css/app.css    # 样式
│   └── js/
│       ├── api.js     # API 客户端
│       ├── router.js  # 路由管理器
│       └── app.js     # 页面逻辑
├── docs/
│   ├── prd.md         # 产品需求文档
│   └── architecture.md # 架构设计文档
├── requirements.txt   # Python 依赖
├── start.py           # 启动脚本
├── start.bat          # Windows 启动
└── start.sh           # Linux/Mac 启动
```
