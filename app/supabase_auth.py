from typing import Optional
import urllib.request
import json

from fastapi import Header, HTTPException

from app.config import settings


def get_current_supabase_user(authorization: Optional[str] = Header(default=None)):
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_URL/SUPABASE_ANON_KEY não configurados no .env."
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token de acesso ausente.")

    token = authorization.split(" ", 1)[1].strip()
    req = urllib.request.Request(
        settings.supabase_url.rstrip("/") + "/auth/v1/user",
        headers={
            "apikey": settings.supabase_anon_key,
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=401, detail="Token Supabase inválido ou expirado.")


def require_admin(authorization: Optional[str] = Header(default=None)):
    user = get_current_supabase_user(authorization)
    role = ((user.get("app_metadata") or {}).get("role"))
    if role != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador.")
    return user
