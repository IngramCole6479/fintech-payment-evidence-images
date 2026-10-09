from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentEventType(str, Enum):
    CAPTURED = "captured"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


class ReviewAction(str, Enum):
    PROCESS = "process"
    HOLD_FOR_REVIEW = "hold_for_review"


class PaymentEvent(BaseModel):
    event_id: UUID
    payment_id: UUID
    event_type: PaymentEventType
    amount_minor: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    risk_score: int = Field(ge=0, le=100)
    occurred_at: datetime


class UploadRequest(BaseModel):
    event: PaymentEvent
    filename: str = Field(min_length=1, max_length=120)
    content_type: str = Field(pattern=r"^image/(jpeg|png|webp)$")
    size_bytes: int = Field(gt=0, le=10_000_000)


class UploadGrant(BaseModel):
    action: ReviewAction
    audit_id: str
    object_key: str
    upload: dict[str, Any] | None
    notification: dict[str, str]


class VariantSpec(BaseModel):
    width: int = Field(gt=0, le=2400)
    height: int = Field(gt=0, le=2400)
    fit: str = "cover"
    format: str = "webp"


class VariantRequest(BaseModel):
    event: PaymentEvent
    object_key: str = Field(min_length=1)
    variants: list[VariantSpec] = Field(min_length=1, max_length=4)


class VariantResult(BaseModel):
    action: ReviewAction
    audit_id: str
    outputs: list[dict[str, Any]]
    notification: dict[str, str]


class PaymentEvidenceService:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket
        self.client.create_bucket(bucket)

    def close(self) -> None:
        try:
            self.client.delete_bucket(self.bucket)
        finally:
            self.client.close()

    @staticmethod
    def decide(event: PaymentEvent) -> ReviewAction:
        if event.risk_score >= 70 or event.event_type == PaymentEventType.DISPUTED:
            return ReviewAction.HOLD_FOR_REVIEW
        return ReviewAction.PROCESS

    @staticmethod
    def audit_id(event: PaymentEvent) -> str:
        return f"{event.payment_id}:{event.event_id}"

    @staticmethod
    def notification(event: PaymentEvent, action: ReviewAction) -> dict[str, str]:
        return {
            "audit_id": PaymentEvidenceService.audit_id(event),
            "event": event.event_type.value,
            "action": action.value,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

    def grant_upload(self, request: UploadRequest) -> UploadGrant:
        action = self.decide(request.event)
        suffix = request.filename.rsplit(".", 1)[-1].lower()
        object_key = f"payments/{request.event.payment_id}/{request.event.event_id}.{suffix}"
        upload = None
        if action == ReviewAction.PROCESS:
            upload = self.client.presign_put(
                self.bucket,
                object_key,
                content_type=request.content_type,
                max_bytes=request.size_bytes,
                idempotency_key=str(request.event.event_id),
            )
        return UploadGrant(
            action=action,
            audit_id=self.audit_id(request.event),
            object_key=object_key,
            upload=upload,
            notification=self.notification(request.event, action),
        )

    def make_variants(self, request: VariantRequest) -> VariantResult:
        action = self.decide(request.event)
        outputs: list[dict[str, Any]] = []
        if action == ReviewAction.PROCESS:
            head = self.client.object_head(self.bucket, request.object_key)
            if not head.get("found"):
                raise ValueError("uploaded image was not found")
            source = self.client.presign_get(self.bucket, request.object_key)
            image = str(source["url"])
            outputs = [
                self.client.resize_image(
                    image,
                    width=variant.width,
                    height=variant.height,
                    fit=variant.fit,
                    image_format=variant.format,
                )
                for variant in request.variants
            ]
        return VariantResult(
            action=action,
            audit_id=self.audit_id(request.event),
            outputs=outputs,
            notification=self.notification(request.event, action),
        )
