from fastapi import APIRouter

from app.apis.v1 import admin, auth, health, stats
from app.apis.v1 import chat

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(stats.router)
api_router.include_router(admin.router)
api_router.include_router(health.router)
