# 部署与一键启动（方案A）

## 1. 目标

- 前后端分离：前端可独立构建/热更新；后端提供 API、任务队列、对象存储、数据库与可观测性。
- 一键启动：以 `e:\SAR\docker-compose.yml` 启动后端依赖与服务。

## 2. 一键启动（本地开发/联调）

在仓库根目录执行：

```bash
docker compose up -d --build
```

默认端口：
- FastAPI：`http://localhost:8000`
  - OpenAPI/Swagger：`http://localhost:8000/docs`
- MinIO Console：`http://localhost:9001`
- Flower：`http://localhost:5555`

默认无登录鉴权：所有接口在本地/内网环境直接可访问（生产环境建议在网关层补齐鉴权与权限控制）。

## 3. 前端联调

前端建议通过 Vite 代理联调：

- 在 `SAR_Front` 配置 `VITE_PROXY_TARGET=http://localhost:8000`
- `VITE_STORAGE_MODE=backend`

后端跨域也已支持（`CORS_ALLOW_ORIGINS`）。

## 4. 迁移与升级

- DB 迁移由 `backend-migrate` 容器执行：`alembic upgrade head`
- Alembic 脚本路径：`SAR_Backend/migrations/versions`

## 5. 生产建议（最小化）

- `CORS_ALLOW_ORIGINS` 不要使用 `*`，而是明确前端域名
- MinIO 使用私有桶（默认已禁用匿名访问），通过签名 URL 访问缩略图/预览图
- Worker 并发与资源隔离：通过 docker/k8s 的 cpu/memory limit 控制，默认 worker `-c 1`
