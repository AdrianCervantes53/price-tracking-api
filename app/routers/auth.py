from fastapi import APIRouter, status
from pydantic import BaseModel, EmailStr

from app.services import auth_service

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(body: RegisterRequest) -> TokenResponse:
    token = await auth_service.register(email=body.email, password=body.password)
    return TokenResponse(access_token=token)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and obtain JWT",
)
async def login(body: LoginRequest) -> TokenResponse:
    token = await auth_service.login(email=body.email, password=body.password)
    return TokenResponse(access_token=token)
