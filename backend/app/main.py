from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.config import Settings, get_settings
from app.services.container import build_services
from app.websocket.telemetry import router as websocket_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.services = build_services(configuration)
        yield

    application = FastAPI(
        title="PhantomNet Backend",
        version="2.0.0",
        description="Isolated telemetry and cyber-deception backend interfaces.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(api_router)
    application.include_router(websocket_router)
    return application


app = create_app()
