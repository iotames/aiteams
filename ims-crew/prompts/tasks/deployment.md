# Task: DevOps 部署与文档

## Description

基于完整项目代码（后端 + 前端 + 测试），创建部署配置、容器化方案和项目文档。

### 需要创建的文件

```
project/
├── Dockerfile               # 后端 Docker 镜像
├── docker-compose.yml       # 多服务编排
├── requirements.txt         # 项目根依赖（仅用于 Docker 构建）
├── .env.example             # 环境变量模板
└── README.md                # 项目使用文档
```

### 各文件要求

#### Dockerfile
- 基于 `python:3.12-slim` 多阶段构建
- 仅安装生产依赖
- 暴露端口 8000
- 启动命令使用 uvicorn

#### docker-compose.yml
- 定义 `backend` 服务（构建镜像、端口映射、环境变量、数据卷）
- 定义 `db` 服务（PostgreSQL，可选）
- 服务依赖关系
- 网络配置

#### .env.example
- `DATABASE_URL` — 数据库连接 URL
- `SECRET_KEY` — 应用密钥
- `ENVIRONMENT` — 运行环境（development/production）
- `LOG_LEVEL` — 日志级别
- 各变量的说明注释

#### project/README.md
- 项目简介
- 技术栈
- 环境要求
- 快速启动（两种方式）
  - Docker Compose 一键启动
  - 手动安装运行
- 访问地址
- 项目结构说明

## Expected Output

部署配置文件和项目文档，保存在 `project/` 目录下。
确保通过 `docker-compose up` 可以一键启动完整系统。
