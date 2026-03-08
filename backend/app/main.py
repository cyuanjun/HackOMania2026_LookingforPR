from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import cases_router, residents_router
from app.core import AppContainer, Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.default()
    resolved_settings.ensure_directories()

    app = FastAPI(title=resolved_settings.app_name)
    app.state.settings = resolved_settings
    app.state.container = AppContainer(resolved_settings)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(residents_router, prefix="/api/v1")
    app.include_router(cases_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

