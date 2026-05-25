from fastapi import APIRouter

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health(settings: Settings = get_settings()) -> dict:
    return {
        "status": "ok",
        "app": {
            "name": settings.app.name,
            "version": settings.app.version,
            "environment": settings.app.environment,
        },
        "dependencies": {
            "database": {
                "configured": bool(settings.database.url),
                "url_env": settings.database.url_env,
            },
            "livekit": {
                "configured": bool(settings.livekit.url),
                "url_env": settings.livekit.url_env,
                "credentials_configured": bool(settings.livekit.api_key and settings.livekit.api_secret),
            },
            "adaption": {
                "configured": bool(settings.adaption.api_key),
                "api_key_env": settings.adaption.api_key_env,
                "base_url_configured": bool(settings.adaption.base_url),
            },
        },
    }
