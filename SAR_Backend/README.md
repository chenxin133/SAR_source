# SAR_Backend（方案A）

## 目录结构

- `app/` FastAPI 应用（API、鉴权、存储、worker 任务等）
- `migrations/` Alembic 迁移
- `docs/` 部署/验收/压测/发布文档

## 快速开始

推荐直接使用仓库根目录的 `docker-compose.yml` 启动（含 Postgres/Redis/MinIO/api/worker）：

```bash
docker compose up -d --build
```

常用入口：
- Swagger：`http://localhost:8000/docs`
- Health：`http://localhost:8000/api/v1/healthz`

## 关键接口（方案A）

- 上传分片：`/api/v1/images/upload/init`、`/api/v1/images/upload/{upload_id}/part/{part_no}`、`/api/v1/images/upload/{upload_id}/complete`
- 触发处理：`POST /api/v1/images/{image_id}/process`
- 任务查询：`GET /api/v1/tasks/{task_id}`
- SSE：`GET /api/v1/tasks/stream/{task_id}`
- 预览资源：`GET /api/v1/images/{image_id}/thumbnails`
