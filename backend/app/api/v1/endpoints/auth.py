"""Routes « Auth » : session visiteur (SA-25), comptes (SA-28) et rattachement (SA-29)."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.security import (create_guest_access_token, decode_guest_token, get_current_user,
                               require_roles)
from app.db.session import get_dict_connection
from app.models.user import Role, UserAccount
from app.schemas.auth import (ClaimRequest, ClaimResponse, GuestTokenResponse, LoginRequest,
                              LoginResponse, RefreshRequest, RegisterRequest, TokenPairResponse,
                              UserResponse)
from app.services import auth_service
from app.services.guest_service import claim_guest_session, create_guest_session

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/guest", response_model=GuestTokenResponse, status_code=201,
             summary="Crée une session visiteur")
def post_guest() -> GuestTokenResponse:
    """Instancie une session temporaire anonyme (UUID v4) et son JWT `role=guest` (SA-25)."""
    with get_dict_connection() as connection:
        session = create_guest_session(connection)
    return GuestTokenResponse(
        access_token=create_guest_access_token(session.id, session.expires_at),
        token_type="bearer",
        role="guest",
        session_id=session.id,
        expires_at=session.expires_at,
    )


@router.post("/register", response_model=UserResponse, status_code=201,
             summary="Crée un compte candidat")
def post_register(request: RegisterRequest) -> UserResponse:
    with get_dict_connection() as connection:
        user = auth_service.register_candidate(connection, request)
    return UserResponse.from_account(user)


@router.post("/login", response_model=LoginResponse, summary="Connexion")
def post_login(request: LoginRequest) -> LoginResponse:
    with get_dict_connection() as connection:
        user, tokens = auth_service.login(connection, request)
    return LoginResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                         expires_in=tokens.expires_in, user=UserResponse.from_account(user))


@router.post("/refresh", response_model=TokenPairResponse, summary="Renouvelle le jeton")
def post_refresh(request: RefreshRequest) -> TokenPairResponse:
    """Rotation : le jeton de renouvellement présenté est révoqué et remplacé."""
    with get_dict_connection() as connection:
        tokens = auth_service.refresh_tokens(connection, request.refresh_token)
    return TokenPairResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token,
                             expires_in=tokens.expires_in)


@router.get("/me", response_model=UserResponse, summary="Compte connecté")
def get_me(current_user: UserAccount = Depends(get_current_user)) -> UserResponse:
    return UserResponse.from_account(current_user)


@router.post("/claim", response_model=ClaimResponse,
             summary="Rattache la conversation invitée au compte")
def post_claim(request: ClaimRequest,
               current_user: UserAccount = Depends(require_roles(Role.CANDIDATE))) -> ClaimResponse:
    """Double preuve : JWT candidat en en-tête + JWT visiteur signé dans le corps (SA-29)."""
    decode_guest_token(request.guest_token, request.guest_session_id)
    with get_dict_connection() as connection:
        result = claim_guest_session(connection, guest_session_id=str(request.guest_session_id),
                                     candidate_id=current_user.id)
    return ClaimResponse(
        message="Session invitée rattachée au compte candidat avec succès.",
        user_id=UUID(current_user.id),
        claimed_conversation_ids=[UUID(conversation_id) for conversation_id in result.conversation_ids],
        transferred_messages_count=result.transferred_messages,
        merged_profile_draft=result.merged_profile,
    )
