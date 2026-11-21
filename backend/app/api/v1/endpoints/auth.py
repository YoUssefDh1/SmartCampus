"""Routes « Auth » : à coder par Membre 4. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/guest", summary="Crée une session visiteur")
def post_guest():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/register", summary="Crée un compte candidat")
def post_register():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/login", summary="Connexion")
def post_login():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/refresh", summary="Renouvelle le jeton")
def post_refresh():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/me", summary="Compte connecté")
def get_me():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/claim", summary="Rattache la conversation invitée au compte")
def post_claim():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
