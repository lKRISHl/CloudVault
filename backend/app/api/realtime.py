from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, WebSocket

from app.api.deps import get_verified_user
from app.api.users import Database
from app.core.database import async_session_maker
from app.models import User
from app.services.realtime import LiveConnection, issue_ticket
from app.services.realtime_store import LiveStore

router = APIRouter()
VerifiedUser = Annotated[User, Depends(get_verified_user)]


async def get_live_store():
    store = LiveStore()
    try:
        yield store
    finally:
        await store.close()


def get_live_factory():
    return async_session_maker


@router.post("/ticket")
async def ticket(
    actor: VerifiedUser,
    db: Database,
    request: Request,
    response: Response,
    store: Annotated[LiveStore, Depends(get_live_store)],
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return await issue_ticket(
        db, store, actor, request.state.session_id, request.client.host if request.client else ""
    )


@router.websocket("/connect")
async def connect(
    socket: WebSocket,
    store: Annotated[LiveStore, Depends(get_live_store)],
    factory: Annotated[Any, Depends(get_live_factory)],
):
    await LiveConnection(socket, store, factory).serve()
