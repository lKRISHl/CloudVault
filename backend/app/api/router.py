from fastapi import APIRouter

from app.api.accounts import router as accounts_router
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.folders import router as folders_router
from app.api.health import router as health_router
from app.api.organizations import router as organizations_router
from app.api.shares import router as shares_router
from app.api.users import router as users_router

api_router = APIRouter()
api_router.include_router(shares_router, tags=["sharing"])
api_router.include_router(files_router, prefix="/files", tags=["files"])
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(folders_router, prefix="/folders", tags=["folders"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(accounts_router, prefix="/account", tags=["account"])
api_router.include_router(organizations_router, prefix="/organizations", tags=["organizations"])
