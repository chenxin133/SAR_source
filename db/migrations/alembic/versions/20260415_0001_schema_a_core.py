"""0001 schema a core

方案A（含 project_id）的核心表结构：
images / thumbnails / samples / annotations / tasks / audit_logs

说明：
- 该 revision 以 op.execute 执行与 SQL 脚本一致的 DDL，便于在没有 ORM model 的情况下落库
- 如果你的 Alembic 环境启用了 "transaction_per_migration"，本 revision 的 DDL 默认在事务内执行
- 未来若需对大表新增索引，请改为 CONCURRENTLY 并使用 autocommit_block

Revision ID: 20260415_0001
Revises: None
Create Date: 2026-04-15
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260415_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$;

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

        CREATE TABLE IF NOT EXISTS images (
          id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id         uuid NOT NULL,
          name              text NOT NULL,
          original_filename text,
          mime_type         text,
          size_bytes        bigint NOT NULL DEFAULT 0,
          checksum_sha256   char(64),
          storage_key       text NOT NULL,
          width             integer,
          height            integer,
          status            text NOT NULL DEFAULT 'uploaded',
          error_message     text,
          created_at        timestamptz NOT NULL DEFAULT now(),
          updated_at        timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT images_project_fk
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
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

        CREATE TABLE IF NOT EXISTS thumbnails (
          id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id   uuid NOT NULL,
          image_id     uuid NOT NULL,
          purpose     text NOT NULL DEFAULT 'preview',
          level       integer NOT NULL,
          format      text NOT NULL DEFAULT 'webp',
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

        CREATE TABLE IF NOT EXISTS samples (
          id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id         uuid NOT NULL,
          image_id           uuid NOT NULL,
          name              text,
          category          text,
          remark            text,
          roi               jsonb,
          crop_storage_key  text,
          thumb_storage_key text,
          created_at        timestamptz NOT NULL DEFAULT now(),
          updated_at        timestamptz NOT NULL DEFAULT now(),
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

        CREATE TABLE IF NOT EXISTS annotations (
          id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id   uuid NOT NULL,
          image_id     uuid,
          sample_id    uuid,
          type        text NOT NULL,
          payload     jsonb NOT NULL,
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

        CREATE TRIGGER trg_annotations_set_updated_at
        BEFORE UPDATE ON annotations
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();

        CREATE TABLE IF NOT EXISTS tasks (
          id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id      uuid NOT NULL,
          image_id        uuid,
          sample_id       uuid,
          type           text NOT NULL,
          status         text NOT NULL DEFAULT 'pending',
          progress       real NOT NULL DEFAULT 0,
          celery_task_id text,
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

        CREATE TABLE IF NOT EXISTS audit_logs (
          id             bigserial PRIMARY KEY,
          project_id      uuid NOT NULL,
          actor_type     text NOT NULL DEFAULT 'system',
          actor_id       uuid,
          action         text NOT NULL,
          entity_type    text NOT NULL,
          entity_id      uuid,
          correlation_id uuid,
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
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_tasks_set_updated_at ON tasks;
        DROP TRIGGER IF EXISTS trg_annotations_set_updated_at ON annotations;
        DROP TRIGGER IF EXISTS trg_samples_set_updated_at ON samples;
        DROP TRIGGER IF EXISTS trg_thumbnails_set_updated_at ON thumbnails;
        DROP TRIGGER IF EXISTS trg_images_set_updated_at ON images;
        DROP TRIGGER IF EXISTS trg_projects_set_updated_at ON projects;

        DROP TABLE IF EXISTS audit_logs;
        DROP TABLE IF EXISTS tasks;
        DROP TABLE IF EXISTS annotations;
        DROP TABLE IF EXISTS samples;
        DROP TABLE IF EXISTS thumbnails;
        DROP TABLE IF EXISTS images;
        DROP TABLE IF EXISTS projects;

        DROP FUNCTION IF EXISTS set_updated_at();
        """
    )

