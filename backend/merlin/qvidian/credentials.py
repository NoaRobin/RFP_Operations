"""Identifiant + clé d'API Qvidian mémorisés sur le poste, saisis une fois dans l'app (pas besoin du .env).

Windows : chiffrement DPAPI (`CryptProtectData`), lié à la session Windows de l'utilisateur — le fichier copié sur un
autre poste ou lu par un autre compte est illisible. Ailleurs (poste de test, Linux) : fichier lisible par le seul
utilisateur, marqué « non chiffré » dans l'écran. Fichier dans data/qvidian/ (jamais committé). Jamais dans le code,
jamais dans un journal, jamais renvoyé au navigateur.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

ENTROPY = b"merlin-qvidian-credentials"


def _protect(data: bytes) -> tuple[str, str]:
    if sys.platform == "win32":
        try:
            import win32crypt  # pywin32

            blob = win32crypt.CryptProtectData(data, "Merlin Qvidian", ENTROPY, None, None, 0)
            return "dpapi", base64.b64encode(blob).decode("ascii")
        except Exception:  # noqa: BLE001 - pywin32 absent : repli lisible par l'utilisateur seul
            pass
    return "local", base64.b64encode(data).decode("ascii")


def _unprotect(kind: str, value: str) -> bytes:
    raw = base64.b64decode(value)
    if kind == "dpapi":
        import win32crypt

        return win32crypt.CryptUnprotectData(raw, ENTROPY, None, None, 0)[1]
    return raw


class CredentialStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, user: str, api_key: str = "", password: str = "", auth_url: str = "") -> str:
        kind, blob = _protect(json.dumps({"api_key": api_key, "password": password}).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"user": user, "auth_url": auth_url, "protection": kind, "secret": blob}), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)
        return kind

    def load(self) -> dict[str, Any] | None:
        """{"user", "api_key", "password", "protection"} ou None (absent ou illisible sur ce poste / ce compte)."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            secret = json.loads(_unprotect(data["protection"], data["secret"]).decode("utf-8"))
            return {"user": data["user"], "auth_url": data.get("auth_url", ""), "protection": data["protection"], **secret}
        except Exception:  # noqa: BLE001
            return None

    def public(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {"remembered": True, "user": data.get("user", ""), "protection": data.get("protection", "")}
        except Exception:  # noqa: BLE001
            return {"remembered": False, "user": "", "protection": ""}

    def forget(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


__all__ = ["CredentialStore"]
