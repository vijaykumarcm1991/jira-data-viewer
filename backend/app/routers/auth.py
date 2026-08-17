from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import SESSION_COOKIE, authenticate_admin, create_session_token, require_admin
from ..database import get_db
from ..schemas import LoginIn, LoginOut

router = APIRouter()


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db), response: Response = None):
    user = authenticate_admin(payload.username, payload.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_session_token(user.id, user.username)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24,
        path="/",
    )
    return LoginOut(username=user.username)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return None


@router.get("/me", response_model=LoginOut)
def me(claims: dict = Depends(require_admin)):
    return LoginOut(username=claims.get("username", ""))
