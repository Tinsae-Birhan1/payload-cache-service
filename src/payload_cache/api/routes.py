import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import text

from payload_cache.api.dependencies import PayloadServiceDep, SessionmakerDep
from payload_cache.api.schemas import HealthStatus, PayloadCreate, PayloadCreated, PayloadRead

router = APIRouter()


@router.post(
    "/payload",
    response_model=PayloadCreated,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {"model": PayloadCreated, "description": "Payload already existed"},
        status.HTTP_502_BAD_GATEWAY: {"description": "Transformer service failed"},
    },
)
async def create_payload(
    body: PayloadCreate, response: Response, service: PayloadServiceDep
) -> PayloadCreated:
    ref = await service.create(body.list_1, body.list_2)
    # 201 vs 200 tells the client whether work was done, without a separate field to parse.
    if not ref.created:
        response.status_code = status.HTTP_200_OK
    response.headers["Location"] = f"/payload/{ref.id}"
    message = "Payload created" if ref.created else "Payload already exists"
    return PayloadCreated(id=ref.id, message=message)


@router.get(
    "/payload/{payload_id}",
    response_model=PayloadRead,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Payload not found"}},
)
async def read_payload(payload_id: uuid.UUID, service: PayloadServiceDep) -> PayloadRead:
    output = await service.get_output(payload_id)
    if output is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payload not found")
    return PayloadRead(output=output)


@router.get(
    "/health",
    response_model=HealthStatus,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database unreachable"}},
)
async def health(sessionmaker: SessionmakerDep) -> HealthStatus:
    # Checks the database, not just the process: a container whose DB is gone should be
    # taken out of rotation by the orchestrator.
    try:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unreachable"
        ) from exc
    return HealthStatus(status="ok")
