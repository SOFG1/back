import importlib.util
import os
import unittest
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Self, TypeAlias

import sqlalchemy
from alembic.command import upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from more_itertools import partition
from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert

ALEMBIC_CONFIG_PATH = "alembic.ini"
INSERT_VALUES_AFTER_REVISION_SOURCE_DIR = Path("tests") / "alembic_migration_inserts_by_revision"

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_CONNECTION = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/"
TEST_DATABASE = f"alembic-migration-test-{uuid.uuid4()}"

RevisionId: TypeAlias = str
TableName: TypeAlias = str
ColumnName: TypeAlias = str
ColumnData: TypeAlias = Any
InsertData: TypeAlias = dict[
    RevisionId, dict[TableName, dict[ColumnName, ColumnData] | list[dict[ColumnName, ColumnData]]]
]
RowId: TypeAlias = str | uuid.UUID | dict[str, str | uuid.UUID]
DeleteData: TypeAlias = dict[RevisionId, dict[TableName, RowId | list[RowId]]]
UpdateData: TypeAlias = dict[RevisionId, dict[TableName, dict[RowId, dict[ColumnName, ColumnData]]]]


def load_insert_values_from(folder: Path) -> tuple[InsertData, DeleteData]:
    """
    Load and return a dictionary of 'data' values from Python files matching the pattern 'rev_*.py' in the given folder.

    This function looks for all Python files in the specified folder whose names start with 'rev_'.
    It dynamically loads the module for each file. If the module contains an attribute called 'data',
    the function extracts that attribute and adds it to the dictionary. The keys in the dictionary
    are the file names with the prefix 'rev_' removed, and the values are the corresponding 'data'
    attributes from the modules.

    Args:
        folder (Path): The folder containing the Python files to load.

    Returns:
        dict: A dictionary where keys are the Python file names (with 'rev_' removed) and
              values are the 'data' attributes from those files, if present.
    """
    insert_values: InsertData = {}
    delete_values: DeleteData = {}

    for file in folder.glob("rev_*.py"):
        # Perform importlib dance to load the module without adding folder to sys.path
        spec = importlib.util.spec_from_file_location(file.stem, file)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        if hasattr(module, "data"):
            insert_values[file.stem.replace("rev_", "")] = module.data
        if hasattr(module, "delete"):
            delete_values[file.stem.replace("rev_", "")] = module.delete
    return insert_values, delete_values


# keys are hexadecimal revision ids
# insert values are maps of table names and one insert (map) or multiple inserts (list of maps)
# insert values take the shape of {"table1": {"key1": 42 }, "table2": [{"key1": 4711 }, {"key1": 4712 }]}
# delete values are maps of table names and one delete (map) or multiple deletes (list of maps)
# delete values take the shape of {"table1": "42", "table2": ["43", "44"], "table3": {"key1": "4711", "key2": "4712" }, "table4": [{"keyA": "a1", "keyB": "b1"}, {"keyA": "a2", "keyB": "b2"}]}
INSERT_VALUES_AFTER_REVISION, DELETE_VALUES_AFTER_REVISION = load_insert_values_from(
    INSERT_VALUES_AFTER_REVISION_SOURCE_DIR
)


def alembic_revisions() -> Iterator[str]:
    alembic_cfg = Config(ALEMBIC_CONFIG_PATH)
    script_directory = ScriptDirectory.from_config(alembic_cfg)
    migrations = list(script_directory.walk_revisions(base="base", head="heads"))
    for migration in reversed(migrations):
        yield migration.revision


class TestAlembicMigrations(unittest.TestCase):
    generated_test_counter = 0

    @classmethod
    def setUpClass(cls) -> None:
        with sqlalchemy.create_engine(
            DB_CONNECTION,
            isolation_level="AUTOCOMMIT",
        ).connect() as conn:
            conn.execute(sqlalchemy.text(f'CREATE DATABASE "{TEST_DATABASE}"'))

        cls.engine = sqlalchemy.create_engine(f"{DB_CONNECTION}{TEST_DATABASE}")
        cls.alembic_cfg = Config(ALEMBIC_CONFIG_PATH)
        cls.alembic_cfg.set_section_option("alembic", "sqlalchemy.url", f"{DB_CONNECTION}{TEST_DATABASE}")
        session_class = sqlalchemy.orm.sessionmaker(bind=cls.engine)
        cls.session = session_class()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.session.close()
        cls.engine.dispose()
        with sqlalchemy.create_engine(
            DB_CONNECTION,
            isolation_level="AUTOCOMMIT",
        ).connect() as conn:
            conn.execute(sqlalchemy.text(f'DROP DATABASE "{TEST_DATABASE}"'))

    @classmethod
    def add_test_for(cls, revision_id: str) -> None:
        def method(self: Self) -> None:
            self.check_tables_not_empty()
            upgrade(self.alembic_cfg, revision_id)
            self.session.commit()
            self.insert_into_tables(revision_id)
            self.check_tables_not_empty()

        cls.generated_test_counter += 1
        test_name = f"test_migration_{cls.generated_test_counter:06g}_revision_{revision_id}"
        setattr(cls, test_name, method)

    def check_tables_not_empty(self) -> None:
        meta = MetaData()
        meta.reflect(self.engine)
        for table_name in sqlalchemy.inspect(self.engine).get_table_names():
            table = Table(table_name, meta, autoload_with=self.engine)
            select_stmt = sqlalchemy.select(table)
            with self.session.begin():
                result = self.session.execute(select_stmt)
                first_row = result.fetchone()
                if first_row is None:
                    self.fail(f"Table {table_name} is empty!")

    def insert_into_tables(self, revision_id: str) -> None:
        meta = MetaData()
        meta.reflect(self.engine)

        insert_values = INSERT_VALUES_AFTER_REVISION.get(revision_id, {})
        delete_values = DELETE_VALUES_AFTER_REVISION.get(revision_id, {})

        # delete first
        for table_name, ids in delete_values.items():
            if not isinstance(ids, list):
                ids = [ids]  # noqa: PLW2901

            compound_ids, simple_ids = partition(lambda id_: isinstance(id_, str | uuid.UUID), ids)
            simple_ids = set(simple_ids)
            if simple_ids:
                table = Table(table_name, meta, autoload_with=self.engine)
                delete_stmt = sqlalchemy.delete(table).where(table.c.id.in_(simple_ids))
                self.session.execute(delete_stmt)

            for id_ in compound_ids:
                assert isinstance(id_, dict)
                self.session.execute(
                    text(
                        f"DELETE FROM {table_name} WHERE "  # noqa: S608
                        + " AND ".join(f'"{column_name}" = :{column_name}' for column_name in id_)
                    ),
                    id_,
                )

        # insert second
        for table_name, values in insert_values.items():
            if not isinstance(values, list):
                values = [values]  # noqa: PLW2901
            table = Table(table_name, meta, autoload_with=self.engine)
            for value in values:
                insert_stmt = insert(table).values(value)
                self.session.execute(insert_stmt)
        self.session.commit()


for revision in alembic_revisions():
    TestAlembicMigrations.add_test_for(revision)


if __name__ == "__main__":
    unittest.main()
