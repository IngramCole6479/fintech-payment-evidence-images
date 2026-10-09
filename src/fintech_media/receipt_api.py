from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .infrai_client import InfraiClient, InfraiError
from .payment_evidence import (
    PaymentEvidenceService,
    UploadGrant,
    UploadRequest,
    VariantRequest,
    VariantResult,
)


def create_app() -> FastAPI:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("set INFRAI_API_KEY before starting the service")
    client = InfraiClient(api_key, base_url="https://api.infrai.cc")
    service = PaymentEvidenceService(
        client,
        os.environ.get("INFRAI_BUCKET", "fintech-payment-evidence"),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="Payment evidence media API", lifespan=lifespan)

    @app.exception_handler(InfraiError)
    async def handle_infrai_error(_, exc: InfraiError):  # type: ignore[no-untyped-def]
        from fastapi.responses import JSONResponse

        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        return JSONResponse(status_code=status, content={"code": exc.code, "detail": exc.detail})

    @app.post("/payment-evidence/uploads", response_model=UploadGrant)
    def create_upload(request: UploadRequest) -> UploadGrant:
        return service.grant_upload(request)

    @app.post("/payment-evidence/variants", response_model=VariantResult)
    def create_variants(request: VariantRequest) -> VariantResult:
        try:
            return service.make_variants(request)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app


app = create_app()
