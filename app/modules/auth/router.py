import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.auth.google_oauth import (
    GoogleOAuthFailure,
    create_authorization_url,
    exchange_code,
    verify_identity,
)
from app.modules.auth.google_observability import new_attempt_id, observe_google_auth
from app.modules.auth.google_service import link_google_identity, sign_in_with_google
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.modules.auth.service import authenticate_user, register_user
from app.modules.auth.validations.google_flow import (
    GOOGLE_FLOW_COOKIE,
    GOOGLE_FLOW_TTL,
    decode_google_flow,
    encode_google_flow,
    new_google_flow,
)
from app.modules.auth.validations.tokens import (
    ACCESS_TOKEN_COOKIE,
    ACCESS_TOKEN_TTL,
    create_access_token,
    validate_access_token,
)
from app.shared.errors.authentication_error import AuthenticationError

router = APIRouter(prefix="/auth", tags=["Authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


def set_auth_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=create_access_token(user_id, settings.secret_key),
        max_age=int(ACCESS_TOKEN_TTL.total_seconds()),
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    request: RegisterRequest, response: Response, session: DatabaseSession
) -> AuthResponse:
    user = await register_user(
        session, request.email, request.password, request.display_name
    )
    set_auth_cookie(response, user.id)
    return AuthResponse(
        message="Cuenta creada correctamente.", user=UserResponse.model_validate(user)
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    request: LoginRequest, response: Response, session: DatabaseSession
) -> AuthResponse:
    user = await authenticate_user(session, request.email, request.password)
    set_auth_cookie(response, user.id)
    return AuthResponse(
        message="Inicio de sesión correcto.", user=UserResponse.model_validate(user)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/", samesite="lax")


@router.get("/me", response_model=UserResponse)
async def current_profile(request: Request, session: DatabaseSession) -> UserResponse:
    user_id = current_user_id(request)
    user = await session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise AuthenticationError(
            code="AUTH_REQUIRED", message="Iniciá sesión para ver tu perfil."
        )
    return UserResponse.model_validate(user)


def google_error_response(code: str, source: str = "login") -> RedirectResponse:
    page = {"login": "/iniciar-sesion", "register": "/registro", "dashboard": "/"}.get(
        source, "/iniciar-sesion"
    )
    if code == "GOOGLE_LOGIN_REQUIRED":
        page = "/iniciar-sesion"
    response = RedirectResponse(f"{page}?auth_error={code}", status_code=303)
    response.delete_cookie(GOOGLE_FLOW_COOKIE, path="/auth/google", samesite="lax")
    return response


def current_user_id(request: Request) -> int | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return None
    try:
        return validate_access_token(token, get_settings().secret_key)
    except AuthenticationError:
        return None


@router.get("/google/start", include_in_schema=False)
async def google_start(
    request: Request,
    session: DatabaseSession,
    flow: Literal["signin", "link"] = "signin",
    source: Literal["login", "register"] = "login",
) -> RedirectResponse:
    settings = get_settings()
    origin = "dashboard" if flow == "link" else source
    if not settings.google_oauth_enabled:
        observe_google_auth("start", "rejected", new_attempt_id(), reason="not_configured")
        return google_error_response("GOOGLE_NOT_CONFIGURED", origin)

    user_id = None
    if flow == "link":
        user_id = current_user_id(request)
        if user_id is None or await session.get(User, user_id) is None:
            observe_google_auth("start", "rejected", new_attempt_id(), reason="login_required")
            return google_error_response("GOOGLE_LOGIN_REQUIRED")

    google_flow = new_google_flow(flow, origin, user_id)
    response = RedirectResponse(
        create_authorization_url(
            settings,
            state=google_flow.state,
            nonce=google_flow.nonce,
            verifier=google_flow.verifier,
        ),
        status_code=303,
    )
    response.set_cookie(
        key=GOOGLE_FLOW_COOKIE,
        value=encode_google_flow(google_flow, settings.secret_key),
        max_age=int(GOOGLE_FLOW_TTL.total_seconds()),
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/auth/google",
    )
    observe_google_auth("start", "started", google_flow.attempt_id)
    return response


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    request: Request,
    session: DatabaseSession,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    token = request.cookies.get(GOOGLE_FLOW_COOKIE)
    if not settings.google_oauth_enabled or not token:
        observe_google_auth("callback", "rejected", new_attempt_id(), reason="missing_flow")
        return google_error_response("GOOGLE_SESSION_EXPIRED")
    try:
        flow = decode_google_flow(token, settings.secret_key)
    except GoogleOAuthFailure as failure:
        observe_google_auth("callback", "rejected", new_attempt_id(), reason="invalid_flow")
        return google_error_response(failure.code)

    if not state or not secrets.compare_digest(state, flow.state):
        observe_google_auth("callback", "rejected", flow.attempt_id, reason="invalid_state")
        return google_error_response("GOOGLE_SESSION_EXPIRED", flow.source)
    if error:
        observe_google_auth("callback", "rejected", flow.attempt_id, reason="provider_denied")
        return google_error_response("GOOGLE_ACCESS_DENIED", flow.source)
    if not code:
        observe_google_auth("callback", "rejected", flow.attempt_id, reason="missing_code")
        return google_error_response("GOOGLE_AUTH_FAILED", flow.source)

    account_started = False
    try:
        id_token = await exchange_code(
            code, flow.verifier, settings, attempt_id=flow.attempt_id
        )
        identity = await verify_identity(
            id_token, flow.nonce, settings, attempt_id=flow.attempt_id
        )
        account_started = True
        observe_google_auth("account", "started", flow.attempt_id)
        if flow.flow == "link":
            user_id = flow.user_id
            if user_id is None or current_user_id(request) != user_id:
                raise GoogleOAuthFailure("GOOGLE_LOGIN_REQUIRED")
            await link_google_identity(session, user_id, identity)
            response = RedirectResponse("/?auth_status=GOOGLE_LINKED", status_code=303)
        else:
            user = await sign_in_with_google(session, identity)
            response = RedirectResponse("/", status_code=303)
            set_auth_cookie(response, user.id)
    except GoogleOAuthFailure as failure:
        if account_started:
            observe_google_auth("account", "failed", flow.attempt_id, reason=failure.code)
        observe_google_auth("callback", "failed", flow.attempt_id, reason=failure.code)
        return google_error_response(failure.code, flow.source)

    response.delete_cookie(GOOGLE_FLOW_COOKIE, path="/auth/google", samesite="lax")
    observe_google_auth("account", "succeeded", flow.attempt_id)
    observe_google_auth("callback", "succeeded", flow.attempt_id)
    return response
