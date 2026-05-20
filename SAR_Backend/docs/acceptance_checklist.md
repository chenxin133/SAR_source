# 验收清单（方案A）

## 1. 功能验收

- 上传与存储
  - 支持分片上传：`POST /api/v1/images/upload/init`、`PUT /api/v1/images/upload/{id}/part/{no}`、`POST /api/v1/images/upload/{id}/complete`
  - 上传完成后原始文件落入对象存储（MinIO/S3），DB 仅保存元数据与 `storage_key`
- 处理与预览
  - `POST /api/v1/images/{image_id}/process` 创建异步任务
  - 生成多级缩略图（至少 256/512/1024/2048）
  - 前端可在上传完成后快速看到可用预览（优先低清，再补高清）
- 任务状态
  - `GET /api/v1/tasks/{task_id}` 可查询 `pending/processing/succeeded/failed`
  - `GET /api/v1/tasks/stream/{task_id}` 支持 SSE 推送进度
- 删除与级联
  - 删除影像会同步删除对象存储中的原图与缩略图

## 2. 非功能验收

- 性能与稳定性
  - 单任务超时：默认 5 分钟（可配置）
  - 失败自动重试：最多 3 次（指数退避）
  - 前端大文件不在浏览器解码，避免 `allocation failed`
- 安全
  - MinIO 私有桶 + 签名 URL（短 TTL）
  - 日志不输出密钥等敏感信息
- 可观测性
  - `/metrics` 可导出 Prometheus 指标（HTTP 请求数与耗时直方图）
  - 结构化请求日志包含 `request_id`

## 3. 质量门槛

- pytest 通过率 ≥ 90%（建议目标：100%）
- 覆盖率 ≥ 80%（`pytest-cov`）
- 接口文档可访问：`/docs` 与 `/openapi.json`
