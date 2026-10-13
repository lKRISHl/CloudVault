from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from app.api.users import CurrentUser, Database
from app.core.security import clear_refresh_cookie
from app.schemas.accounts import (
    ConfirmEmailRequest,
    DeleteAccountRequest,
    EmailChangeRequest,
    EmailDeliveryRead,
    PasswordRequest,
    RecoveryRequest,
    ResetRequest,
    SessionRead,
    TokenRequest,
)
from app.services.accounts import GENERIC_RECOVERY, AccountService

router = APIRouter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/recovery-request", status_code=202)
async def recovery(payload: RecoveryRequest, request: Request, db: Database):
    await AccountService(db).request_recovery(payload.email, payload.purpose, client_ip(request))
    return {"detail": GENERIC_RECOVERY}


@router.post("/verify")
async def verify(payload: TokenRequest, request: Request, db: Database):
    service = AccountService(db)
    await service.limit("account-links", client_ip(request))
    await service.verify(payload.token)
    return {"detail": "Email verified. You can use your organization."}


@router.post("/reset-password")
async def reset(payload: ResetRequest, request: Request, response: Response, db: Database):
    service = AccountService(db)
    await service.limit("account-links", client_ip(request))
    await service.reset_password(payload.token, payload.password)
    clear_refresh_cookie(response)
    return {"detail": "Password reset. Sign in with your new password."}


@router.post("/email-change", status_code=202)
async def change_email(
    payload: EmailChangeRequest, actor: CurrentUser, request: Request, db: Database
):
    service = AccountService(db)
    await service.limit("email-change", client_ip(request), str(actor.id))
    await service.request_email_change(actor, payload.email, payload.password)
    return {"detail": "Verification queued for the new address. Your current email is unchanged."}


@router.post("/confirm-email")
async def confirm_email(
    payload: ConfirmEmailRequest,
    actor: CurrentUser,
    request: Request,
    response: Response,
    db: Database,
):
    service = AccountService(db)
    await service.limit("reauth", client_ip(request), str(actor.id))
    await service.confirm_email_change(actor, payload.token, payload.password)
    clear_refresh_cookie(response)
    return {"detail": "Email changed. Sign in with your new address."}


@router.get("/sessions", response_model=list[SessionRead])
async def sessions(
    actor: CurrentUser,
    request: Request,
    db: Database,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    return await AccountService(db).sessions(actor, request.state.session_id, offset, limit)


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(session_id: UUID, actor: CurrentUser, db: Database):
    await AccountService(db).revoke_session(actor, session_id)


@router.post("/sign-out-all", status_code=204)
async def sign_out_all(
    payload: PasswordRequest, actor: CurrentUser, request: Request, response: Response, db: Database
):
    service = AccountService(db)
    await service.limit("reauth", client_ip(request), str(actor.id))
    user = await service.lock_user(actor.id)
    service.reauthenticate(user, payload.password)
    await service.revoke_all(user.id)
    await db.commit()
    clear_refresh_cookie(response)


@router.get("/email-deliveries", response_model=list[EmailDeliveryRead])
async def deliveries(actor: CurrentUser, db: Database):
    return await AccountService(db).deliveries(actor)


@router.delete("", status_code=204)
async def delete_account(
    payload: DeleteAccountRequest,
    actor: CurrentUser,
    request: Request,
    response: Response,
    db: Database,
):
    service = AccountService(db)
    await service.limit("reauth", client_ip(request), str(actor.id))
    await service.delete_account(actor, payload.password)
    clear_refresh_cookie(response)
