from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlalchemy.orm import subqueryload
from sqlmodel import Session, or_, select

from app.api.exceptions import InsufficientPermissionsError, InvalidCredentialsError
from app.api.models import Scope, User
from app.api.tools.db import db_engine
from app.settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def authenticate_user(session: Session, username_or_email: str, password: str) -> User | None:
    user: User | None = session.exec(
        select(User).where(or_(User.username == username_or_email, User.email == username_or_email))
    ).one_or_none()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + expires_delta if expires_delta else datetime.now(UTC) + timedelta(days=1)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.oauth_secret_key.get_secret_value(), algorithm=settings.oauth_algorithm)


def _get_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(db_engine.get_session)],
    options: Sequence | None = None,
) -> User:
    try:
        payload = jwt.decode(token, settings.oauth_secret_key.get_secret_value(), algorithms=[settings.oauth_algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise InvalidCredentialsError
    except (InvalidTokenError, ValidationError) as e:
        raise InvalidCredentialsError from e
    if options:
        user: User | None = session.exec(select(User).where(User.username == username).options(*options)).one_or_none()
    else:
        user: User | None = session.exec(select(User).where(User.username == username)).one_or_none()
    if user is None:
        raise InvalidCredentialsError
    user_scopes = {x.value for x in Scope} if user.scopes == "*" else set(user.scopes.split(","))
    # User needs to have at least one of the defined scopes on the endpoint
    if security_scopes.scopes and not set(security_scopes.scopes) & user_scopes:
        raise InsufficientPermissionsError(
            headers={
                "WWW-Authenticate": f'Bearer scope="{security_scopes.scope_str}"'
                if security_scopes.scopes
                else "Bearer"
            }
        )
    session.close()
    return user


def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> User:
    return _get_user(security_scopes, token, session, None)


def get_current_user_eager(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(db_engine.get_session)],
) -> User:
    return _get_user(security_scopes, token, session, [subqueryload("*")])
