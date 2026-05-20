-- 0001_schema_a_core_down.sql
-- 回滚：删除 0001_schema_a_core_up.sql 创建的对象
-- 注意：会丢失对应表内全部数据
BEGIN;

-- 触发器（存在则删）
DROP TRIGGER IF EXISTS trg_tasks_set_updated_at ON tasks;
DROP TRIGGER IF EXISTS trg_annotations_set_updated_at ON annotations;
DROP TRIGGER IF EXISTS trg_samples_set_updated_at ON samples;
DROP TRIGGER IF EXISTS trg_thumbnails_set_updated_at ON thumbnails;
DROP TRIGGER IF EXISTS trg_images_set_updated_at ON images;
DROP TRIGGER IF EXISTS trg_projects_set_updated_at ON projects;

-- 表（从子到父）
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS annotations;
DROP TABLE IF EXISTS samples;
DROP TABLE IF EXISTS thumbnails;
DROP TABLE IF EXISTS images;
DROP TABLE IF EXISTS projects;

-- 函数
DROP FUNCTION IF EXISTS set_updated_at();

-- 扩展：通常不建议在回滚里删除（可能被其他对象依赖）
-- DROP EXTENSION IF EXISTS pgcrypto;

COMMIT;

