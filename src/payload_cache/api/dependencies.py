from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payload_cache.services.payload_service import PayloadService


# Services are built once in the app lifespan and stored on app.state. They hold
# process-wide state (the in-flight call registry, the connection pool), so building
# them per request would defeat their purpose.
def get_payload_service(request: Request) -> PayloadService:
    service: PayloadService = request.app.state.payload_service
    return service


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    return sessionmaker


PayloadServiceDep = Annotated[PayloadService, Depends(get_payload_service)]
SessionmakerDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)]
