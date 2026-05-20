# CI/CD、灰度与回滚（建议）

## 1. CI（质量门禁）

- 后端
  - `ruff check`
  - `pytest + coverage`（建议 CI 设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`）
  - 生成 OpenAPI（`/openapi.json`）并可选做快照比对（防接口漂移）
- 前端
  - `npm ci`
  - `npm run build`

仓库内已提供 GitHub Actions 示例：
- 后端：[backend.yml](file:///e:/SAR/.github/workflows/backend.yml)
- 前端：[frontend.yml](file:///e:/SAR/.github/workflows/frontend.yml)

## 2. CD（交付与部署）

- 镜像构建：`api` 与 `worker` 可复用同一镜像，不同启动命令
- 迁移执行：部署阶段先执行 `alembic upgrade head`（可作为一次性 Job）
- 配置管理：使用环境变量注入（DB/Redis/S3/JWT/CORS 等）

## 3. 灰度发布策略

- 接口层灰度
  - 通过反向代理/网关按用户/Token/百分比路由到新版本
  - 维持 `api_prefix=/api/v1` 不变，保证路径稳定
- 业务层灰度（推荐）
  - 前端增加 feature flag（已提供 `VITE_STORAGE_MODE=backend|local`）
  - 灰度开启后端链路：只对部分用户启用 backend 模式
  - 观察指标：任务失败率、处理耗时 P95、队列积压、对象存储错误率

## 4. 回滚策略

- 镜像回滚：按 tag 回退 `backend-api` 与 `backend-worker`
- DB 回滚
  - 避免不可逆迁移：推荐 expand/contract（先加字段/表 → 双写 → 切读 → 再删旧字段）
  - 若必须回滚 DDL，优先回滚应用读写，再做 schema downgrade，避免“降级时仍写入新字段”
- 对象存储回滚
  - 删除建议延迟执行（生命周期回收或软删），降低误删的不可逆性

