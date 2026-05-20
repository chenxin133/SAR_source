"""0002 users and ownership

Revision ID: 20260415_0002
Revises: 20260415_0001
Create Date: 2026-04-15
"""

from alembic import op

revision = "20260415_0002"
down_revision = "20260415_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          email         text NOT NULL UNIQUE,
          password_hash text NOT NULL,
          role          text NOT NULL DEFAULT 'user',
          created_at    timestamptz NOT NULL DEFAULT now(),
          updated_at    timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT users_email_nonempty CHECK (length(btrim(email)) > 0),
          CONSTRAINT users_role_chk CHECK (role IN ('admin','user'))
        );

        DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
        CREATE TRIGGER trg_users_set_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();

        ALTER TABLE images
          ADD COLUMN IF NOT EXISTS owner_id uuid;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'images_owner_fk'
          ) THEN
            ALTER TABLE images
              ADD CONSTRAINT images_owner_fk
              FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
          END IF;
        END $$;

        ALTER TABLE samples
          ADD COLUMN IF NOT EXISTS owner_id uuid;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'samples_owner_fk'
          ) THEN
            ALTER TABLE samples
              ADD CONSTRAINT samples_owner_fk
              FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
          END IF;
        END $$;

        ALTER TABLE annotations
          ADD COLUMN IF NOT EXISTS owner_id uuid;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'annotations_owner_fk'
          ) THEN
            ALTER TABLE annotations
              ADD CONSTRAINT annotations_owner_fk
              FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
          END IF;
        END $$;

        ALTER TABLE tasks
          ADD COLUMN IF NOT EXISTS owner_id uuid;
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'tasks_owner_fk'
          ) THEN
            ALTER TABLE tasks
              ADD CONSTRAINT tasks_owner_fk
              FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_owner_fk;
        ALTER TABLE tasks DROP COLUMN IF EXISTS owner_id;

        ALTER TABLE annotations DROP CONSTRAINT IF EXISTS annotations_owner_fk;
        ALTER TABLE annotations DROP COLUMN IF EXISTS owner_id;

        ALTER TABLE samples DROP CONSTRAINT IF EXISTS samples_owner_fk;
        ALTER TABLE samples DROP COLUMN IF EXISTS owner_id;

        ALTER TABLE images DROP CONSTRAINT IF EXISTS images_owner_fk;
        ALTER TABLE images DROP COLUMN IF EXISTS owner_id;

        DROP TRIGGER IF EXISTS trg_users_set_updated_at ON users;
        DROP TABLE IF EXISTS users;
        """
    )
