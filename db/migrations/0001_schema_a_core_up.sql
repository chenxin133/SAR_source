-- 0001_schema_a_core_up.sql
-- 方案A：images / thumbnails / samples / annotations / tasks / audit_logs 核心表结构（含 project_id）
-- 目标：
-- - 元数据落 PostgreSQL；大文件/缩略图/裁切图落对象存储（storage_key）
-- - 通过 (project_id, id) 复合外键，保证跨表引用在同一项目内
-- - 全表包含 created_at/updated_at（updated_at 由触发器自动维护）
--
-- 注意：
-- - 本脚本默认在空库/新表上执行；若是大表加索引请改用 CREATE INDEX CONCURRENTLY 并拆出事务外执行
-- - 依赖 pgcrypto 扩展以使用 gen_random_uuid()
--
BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 通用 updated_at 触发器函数
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- projects：项目/租户隔离的顶层实体
CREATE TABLE IF NOT EXISTS projects (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  description text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT projects_name_nonempty CHECK (length(btrim(name)) > 0)
);

CREATE TRIGGER trg_projects_set_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- images：原始影像元数据（原文件在对象存储）
CREATE TABLE IF NOT EXISTS images (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id         uuid NOT NULL,
  name              text NOT NULL,
  original_filename text,
  mime_type         text,
  size_bytes        bigint NOT NULL DEFAULT 0,
  checksum_sha256   char(64),
  storage_key       text NOT NULL,        -- 对象存储 key（原图）
  width             integer,
  height            integer,
  status            text NOT NULL DEFAULT 'uploaded',
  error_message     text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT images_project_fk
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
  -- 复合唯一键：供同项目复合外键引用
  CONSTRAINT images_project_id_id_uniq UNIQUE (project_id, id),
  CONSTRAINT images_size_nonneg CHECK (size_bytes >= 0),
  CONSTRAINT images_status_chk CHECK (status IN ('uploaded','processing','ready','failed')),
  CONSTRAINT images_storage_key_nonempty CHECK (length(btrim(storage_key)) > 0),
  CONSTRAINT images_name_nonempty CHECK (length(btrim(name)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_images_project_storage_key
  ON images(project_id, storage_key);

CREATE INDEX IF NOT EXISTS ix_images_project_status_created_at
  ON images(project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_images_project_created_at
  ON images(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_images_project_checksum
  ON images(project_id, checksum_sha256)
  WHERE checksum_sha256 IS NOT NULL;

CREATE TRIGGER trg_images_set_updated_at
BEFORE UPDATE ON images
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- thumbnails：多级缩略图/预览图元数据（文件在对象存储）
CREATE TABLE IF NOT EXISTS thumbnails (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   uuid NOT NULL,
  image_id     uuid NOT NULL,
  purpose     text NOT NULL DEFAULT 'preview', -- preview/thumb/pyramid 等（可扩展）
  level       integer NOT NULL,               -- 例如 256/512/1024/2048（最长边像素）
  format      text NOT NULL DEFAULT 'webp',    -- webp/png/jpeg
  quality     smallint,
  storage_key text NOT NULL,
  width       integer,
  height      integer,
  size_bytes  bigint,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT thumbnails_image_fk
    FOREIGN KEY (project_id, image_id)
    REFERENCES images(project_id, id)
    ON DELETE CASCADE,
  CONSTRAINT thumbnails_project_id_id_uniq UNIQUE (project_id, id),
  CONSTRAINT thumbnails_level_positive CHECK (level > 0),
  CONSTRAINT thumbnails_quality_chk CHECK (quality IS NULL OR (quality >= 1 AND quality <= 100)),
  CONSTRAINT thumbnails_format_chk CHECK (format IN ('webp','png','jpeg','jpg')),
  CONSTRAINT thumbnails_purpose_nonempty CHECK (length(btrim(purpose)) > 0),
  CONSTRAINT thumbnails_storage_key_nonempty CHECK (length(btrim(storage_key)) > 0)
);

-- 同一 image 同一 purpose+level+format 只保留一份
CREATE UNIQUE INDEX IF NOT EXISTS ux_thumbnails_image_variant
  ON thumbnails(project_id, image_id, purpose, level, format);

CREATE INDEX IF NOT EXISTS ix_thumbnails_image
  ON thumbnails(project_id, image_id);

CREATE INDEX IF NOT EXISTS ix_thumbnails_project_created_at
  ON thumbnails(project_id, created_at DESC);

CREATE TRIGGER trg_thumbnails_set_updated_at
BEFORE UPDATE ON thumbnails
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- samples：样本（可为裁切图或 ROI 引用），文件在对象存储
CREATE TABLE IF NOT EXISTS samples (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id        uuid NOT NULL,
  image_id          uuid NOT NULL,
  name             text,
  category         text,
  remark           text,
  roi              jsonb,             -- 例如 {type:'bbox', x:..., y:..., w:..., h:...} 或 polygon 等
  crop_storage_key text,              -- 裁切图 key（可选：懒生成）
  thumb_storage_key text,             -- 样本缩略图 key（可选）
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT samples_image_fk
    FOREIGN KEY (project_id, image_id)
    REFERENCES images(project_id, id)
    ON DELETE CASCADE,
  CONSTRAINT samples_project_id_id_uniq UNIQUE (project_id, id),
  CONSTRAINT samples_crop_storage_key_nonempty CHECK (crop_storage_key IS NULL OR length(btrim(crop_storage_key)) > 0),
  CONSTRAINT samples_thumb_storage_key_nonempty CHECK (thumb_storage_key IS NULL OR length(btrim(thumb_storage_key)) > 0)
);

CREATE INDEX IF NOT EXISTS ix_samples_image
  ON samples(project_id, image_id);

CREATE INDEX IF NOT EXISTS ix_samples_project_created_at
  ON samples(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_samples_category
  ON samples(project_id, category)
  WHERE category IS NOT NULL;

CREATE TRIGGER trg_samples_set_updated_at
BEFORE UPDATE ON samples
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- annotations：标注（JSONB 统一承载 bbox/polygon/line/point/mask 等）
-- 约束：只能绑定 image 或 sample 其中之一（互斥）
CREATE TABLE IF NOT EXISTS annotations (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   uuid NOT NULL,
  image_id     uuid,
  sample_id    uuid,
  type        text NOT NULL,          -- e.g. bbox/polygon/point/mask/classification
  payload     jsonb NOT NULL,         -- 具体标注数据
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT annotations_project_id_id_uniq UNIQUE (project_id, id),
  CONSTRAINT annotations_target_xor_chk CHECK (num_nonnulls(image_id, sample_id) = 1),
  CONSTRAINT annotations_type_nonempty CHECK (length(btrim(type)) > 0),
  CONSTRAINT annotations_image_fk
    FOREIGN KEY (project_id, image_id)
    REFERENCES images(project_id, id)
    ON DELETE CASCADE,
  CONSTRAINT annotations_sample_fk
    FOREIGN KEY (project_id, sample_id)
    REFERENCES samples(project_id, id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_annotations_image
  ON annotations(project_id, image_id)
  WHERE image_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_annotations_sample
  ON annotations(project_id, sample_id)
  WHERE sample_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_annotations_project_type_created_at
  ON annotations(project_id, type, created_at DESC);

-- 如需按 payload 内字段过滤（例如 label/category），再按真实查询模式补充表达式索引或 GIN：
-- CREATE INDEX CONCURRENTLY ... ON annotations USING GIN (payload jsonb_path_ops);

CREATE TRIGGER trg_annotations_set_updated_at
BEFORE UPDATE ON annotations
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- tasks：异步处理任务（缩略图生成/裁切/导入等）
-- 约束：只能绑定 image 或 sample 其中之一（互斥）
CREATE TABLE IF NOT EXISTS tasks (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      uuid NOT NULL,
  image_id        uuid,
  sample_id       uuid,
  type           text NOT NULL,   -- e.g. generate_thumbnails / generate_sample_crop / import
  status         text NOT NULL DEFAULT 'pending', -- pending/processing/succeeded/failed/canceled
  progress       real NOT NULL DEFAULT 0,         -- 0..100
  celery_task_id text,                             -- 对接 Celery/其他队列的外部任务ID
  payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
  result         jsonb,
  error_message  text,
  started_at     timestamptz,
  finished_at    timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tasks_project_id_id_uniq UNIQUE (project_id, id),
  CONSTRAINT tasks_target_xor_chk CHECK (num_nonnulls(image_id, sample_id) = 1),
  CONSTRAINT tasks_type_nonempty CHECK (length(btrim(type)) > 0),
  CONSTRAINT tasks_status_chk CHECK (status IN ('pending','processing','succeeded','failed','canceled')),
  CONSTRAINT tasks_progress_chk CHECK (progress >= 0 AND progress <= 100),
  CONSTRAINT tasks_image_fk
    FOREIGN KEY (project_id, image_id)
    REFERENCES images(project_id, id)
    ON DELETE CASCADE,
  CONSTRAINT tasks_sample_fk
    FOREIGN KEY (project_id, sample_id)
    REFERENCES samples(project_id, id)
    ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tasks_celery_task_id
  ON tasks(celery_task_id)
  WHERE celery_task_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_tasks_project_status_created_at
  ON tasks(project_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_tasks_image
  ON tasks(project_id, image_id)
  WHERE image_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_tasks_sample
  ON tasks(project_id, sample_id)
  WHERE sample_id IS NOT NULL;

CREATE TRIGGER trg_tasks_set_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- audit_logs：审计日志（追加写，建议长期按时间归档/分区）
CREATE TABLE IF NOT EXISTS audit_logs (
  id             bigserial PRIMARY KEY,
  project_id      uuid NOT NULL,
  actor_type     text NOT NULL DEFAULT 'system',  -- system/user/service
  actor_id       uuid,
  action         text NOT NULL,                  -- create/update/delete/process/...
  entity_type    text NOT NULL,                  -- images/samples/annotations/tasks/...
  entity_id      uuid,                           -- 业务对象 id（不强制FK，允许对象已删除）
  correlation_id uuid,                           -- 请求/链路ID
  ip             inet,
  user_agent     text,
  before         jsonb,
  after          jsonb,
  meta           jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT audit_logs_project_fk
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
  CONSTRAINT audit_logs_action_nonempty CHECK (length(btrim(action)) > 0),
  CONSTRAINT audit_logs_entity_type_nonempty CHECK (length(btrim(entity_type)) > 0),
  CONSTRAINT audit_logs_actor_type_nonempty CHECK (length(btrim(actor_type)) > 0)
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_project_created_at
  ON audit_logs(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_logs_entity
  ON audit_logs(project_id, entity_type, entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_logs_actor
  ON audit_logs(project_id, actor_type, actor_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation
  ON audit_logs(project_id, correlation_id)
  WHERE correlation_id IS NOT NULL;

COMMIT;

