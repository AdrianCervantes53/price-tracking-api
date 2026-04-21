from fastapi import HTTPException, status

from app.core.security import create_access_token, hash_password, verify_password
from app.repositories.user_repository import UserRepository

_repo = UserRepository()


async def register(email: str, password: str) -> str:
    """
    Creates a new user. Returns a JWT access token.
    Raises HTTP 409 if the email is already registered.
    """
    existing = await _repo.get_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = await _repo.create(email=email, hashed_password=hash_password(password))
    return create_access_token(subject=str(user.id))


async def login(email: str, password: str) -> str:
    """
    Authenticates an existing user. Returns a JWT access token.
    Raises HTTP 401 if credentials are invalid.
    """
    invalid_credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await _repo.get_by_email(email)
    if not user:
        raise invalid_credentials_exception
    if not verify_password(password, user.hashed_password):
        raise invalid_credentials_exception
    return create_access_token(subject=str(user.id))
