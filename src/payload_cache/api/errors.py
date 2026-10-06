import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from payload_cache.services.transformation_cache import TransformerError

logger = logging.getLogger(__name__)


async def _transformer_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # 502: the failure is in an upstream dependency, not in the client's request or in
    # this service. Clients can retry; results that did succeed are already cached.
    logger.warning("transformer failure on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Transformer service failed, please retry"},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TransformerError, _transformer_error_handler)
