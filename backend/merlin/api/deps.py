from __future__ import annotations

from urllib.parse import unquote

from fastapi import Header, HTTPException

from ..state import AppState, get_state


def state() -> AppState:
    return get_state()


def current_user(x_merlin_user: str | None = Header(default=None)) -> str:
    """Pas d'authentification pour l'instant : l'interface envoie le prénom choisi par l'utilisateur."""
    name = unquote(x_merlin_user or "").strip()[:60]
    return name or get_state().settings.default_user


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"message": message, "hint": "Vérifiez le lien ou revenez au grimoire."})


def bad_request(message: str, hint: str = "") -> HTTPException:
    return HTTPException(status_code=400, detail={"message": message, "hint": hint})
