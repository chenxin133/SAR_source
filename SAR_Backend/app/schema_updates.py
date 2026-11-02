"""Small, idempotent schema updates for existing desktop SQLite databases."""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect
from sqlalchemy.engine import Engine


def allow_samples_without_source(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as connection:
        columns = inspect(connection).get_columns("samples")
        source = next(column for column in columns if column["name"] == "image_id")
        if source["nullable"]:
            return
        connection.rollback()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        try:
            database = connection.exec_driver_sql("PRAGMA database_list").fetchone()[2]
            connection.rollback()
            if database:
                backup = Path(database + ".before-optional-sample-source.bak")
                if not backup.exists():
                    temporary = backup.with_suffix(backup.suffix + ".tmp")
                    try:
                        with closing(sqlite3.connect(str(temporary))) as destination:
                            connection.connection.driver_connection.backup(destination)
                        os.replace(temporary, backup)
                    finally:
                        temporary.unlink(missing_ok=True)
            # Explicit BEGIN makes the entire SQLite table rebuild transactional.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            triggers = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='samples' AND sql IS NOT NULL"
            ).scalars().all()
            operations = Operations(MigrationContext.configure(connection))
            with operations.batch_alter_table("samples", recreate="always") as batch:
                batch.alter_column("image_id", existing_type=source["type"], nullable=True)
            for statement in triggers:
                connection.exec_driver_sql(statement)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql(f"PRAGMA foreign_keys={int(bool(foreign_keys))}")
            connection.commit()


def add_sample_import_metadata(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("samples")}
        missing = {"resolution": "TEXT", "checksum_sha256": "VARCHAR(64)"}.keys() - columns
        if not missing:
            return
        database = connection.exec_driver_sql("PRAGMA database_list").fetchone()[2]
        if database:
            backup = Path(database + ".before-sample-import-metadata.bak")
            if not backup.exists():
                temporary = backup.with_suffix(backup.suffix + ".tmp")
                try:
                    with closing(sqlite3.connect(str(temporary))) as destination:
                        connection.connection.driver_connection.backup(destination)
                    os.replace(temporary, backup)
                finally:
                    temporary.unlink(missing_ok=True)
        for name in sorted(missing):
            sql_type = "TEXT" if name == "resolution" else "VARCHAR(64)"
            connection.exec_driver_sql(f"ALTER TABLE samples ADD COLUMN {name} {sql_type}")
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_samples_project_checksum ON samples(project_id, checksum_sha256)"
        )


def add_scene_xml_metadata(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    definitions = {
        "images": {"metadata_xml_key": "TEXT", "metadata_xml_filename": "TEXT", "scene_metadata": "JSON"},
        "samples": {"frequency_band": "TEXT", "sequence_no": "INTEGER", "metadata_xml_key": "TEXT", "scene_metadata": "JSON"},
    }
    with engine.begin() as connection:
        missing = {table: {name: kind for name, kind in fields.items() if name not in
                   {column["name"] for column in inspect(connection).get_columns(table)}}
                   for table, fields in definitions.items()}
        if not any(missing.values()):
            return
        database = connection.exec_driver_sql("PRAGMA database_list").fetchone()[2]
        if database:
            backup = Path(database + ".before-scene-xml-metadata.bak")
            if not backup.exists():
                temporary = backup.with_suffix(backup.suffix + ".tmp")
                try:
                    with closing(sqlite3.connect(str(temporary))) as destination:
                        connection.connection.driver_connection.backup(destination)
                    os.replace(temporary, backup)
                finally:
                    temporary.unlink(missing_ok=True)
        for table, fields in missing.items():
            for name, kind in fields.items():
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS ux_samples_project_sequence ON samples(project_id, sequence_no)")
