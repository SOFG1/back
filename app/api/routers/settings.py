import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Security, status
from sqlmodel import Session

from app.api.exceptions import IndexerNotInitializedError
from app.api.models import (
    ErrorMessage,
    Scope,
    User,
)
from app.api.tools.auth import get_current_user
from app.api.tools.db import db_engine
from app.custom_logging import get_logger
from app.engine.indexer import Indexer
from app.settings import AdminSettings, get_admin_settings

settings_router = st = APIRouter(prefix="/api/settings", tags=["settings"])

logger = get_logger(__name__)


def reinitialize_indexer(request: Request, namespace: str, indexer: Indexer) -> None:
    indexer.stop()
    new_indexer = Indexer()
    new_indexer.initialize(namespace)
    request.app.state.indexer = new_indexer
    threading.Thread(target=new_indexer.poll_continuously, name="indexer", daemon=True).start()


def get_indexer(request: Request) -> Indexer:
    if not hasattr(request.app.state, "indexer"):
        raise IndexerNotInitializedError()  # noqa: RSE102
    return request.app.state.indexer


@st.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorMessage},
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def set_admin_settings(
    body: AdminSettings,
    session: Annotated[Session, Depends(db_engine.get_session)],
    _: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
    indexer: Annotated[Indexer, Depends(get_indexer)],
    request: Request,
) -> None:
    if indexer.index != body.namespace:
        reinitialize_indexer(request, body.namespace, indexer)
    body.to_db(session=session)


@st.get(
    "/",
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorMessage},
        status.HTTP_403_FORBIDDEN: {"model": ErrorMessage},
    },
)
def get_admin_settings_(
    admin_settings: Annotated[AdminSettings, Depends(get_admin_settings)],
    _: Annotated[User, Security(get_current_user, scopes=[Scope.SETTINGS])],
) -> AdminSettings:
    return admin_settings
