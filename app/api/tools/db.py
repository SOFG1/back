from collections.abc import Generator

from alembic import command
from alembic.config import Config
from sqlmodel import Session, create_engine


class DBEngine:
    def __init__(self) -> None:
        self.engine = None
        self.connection_string: str | None = None
        self.connection_pool_size: int | None = None

    def create_engine(self) -> None:
        assert self.connection_string, "connection_string needs to be set"
        self.engine = create_engine(
            self.connection_string, pool_size=self.connection_pool_size, max_overflow=0, pool_pre_ping=True
        )

    def create_schema(self) -> None:
        config = Config("alembic.ini")
        assert self.connection_string, "connection_string needs to be set"
        config.set_main_option("sqlalchemy.url", self.connection_string)
        command.upgrade(config, "head")

    def get_session(self) -> Generator[Session, None, None]:
        with Session(self.engine) as session:
            yield session

    def get_session_raw(self) -> Session:
        with Session(self.engine) as session:
            return session


db_engine = DBEngine()
