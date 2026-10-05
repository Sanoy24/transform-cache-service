"""FastAPI application: HTTP layer over PayloadService."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    status,
)

from transform_cache.config import Settings
from transform_cache.db import create_engine, create_session_factory, init_db
from transform_cache.schemas import PayloadCreate, PayloadCreated, PayloadOutput
from transform_cache.service import PayloadService
from transform_cache.transformer import SimulatedTransformer, Transformer


def get_service(request: Request) -> PayloadService:
    service: PayloadService = request.app.state.service
    return service


ServiceDep = Annotated[PayloadService, Depends(get_service)]

router = APIRouter()


@router.post(
    "/payload",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": PayloadCreated}},
)
async def create_payload(
    body: PayloadCreate, response: Response, service: ServiceDep
) -> PayloadCreated:
    result = await service.create_payload(body.list_1, body.list_2)
    if not result.created:
        response.status_code = status.HTTP_200_OK
        return PayloadCreated(id=result.id, message="Payload already exists")
    response.headers["Location"] = f"/payload/{result.id}"
    return PayloadCreated(id=result.id, message="Payload created")


@router.get("/payload/{payload_id}")
async def get_payload(payload_id: uuid.UUID, service: ServiceDep) -> PayloadOutput:
    output = await service.get_payload_output(payload_id)
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payload not found"
        )
    return PayloadOutput(output=output)


def create_app(
    settings: Settings | None = None, transformer: Transformer | None = None
) -> FastAPI:
    """Build the app; arguments let tests swap the database and transformer."""
    resolved_settings = settings if settings is not None else Settings()
    active_transformer = (
        transformer
        if transformer is not None
        else SimulatedTransformer(resolved_settings.transformer_latency_seconds)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        engine = create_engine(resolved_settings.database_url)
        try:
            await init_db(engine)
            # One instance for the whole app: the concurrency limit and in-flight
            # deduplication only work if every request shares them.
            app.state.service = PayloadService(
                create_session_factory(engine),
                active_transformer,
                resolved_settings.transformer_max_concurrency,
            )
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Transform Cache Service", lifespan=lifespan)
    app.include_router(router)
    return app
