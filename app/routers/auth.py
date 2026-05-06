from fastapi import APIRouter, status

from app.services import auth_service
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter()


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
