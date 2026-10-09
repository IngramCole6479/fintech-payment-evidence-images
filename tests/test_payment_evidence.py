from datetime import datetime, timezone
from uuid import UUID

from fintech_media.payment_evidence import (
    PaymentEvent,
    PaymentEventType,
    PaymentEvidenceService,
    ReviewAction,
    VariantRequest,
    VariantSpec,
)


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_bucket(self, name: str) -> dict:
        self.calls.append("create_bucket")
        return {"name": name}

    def delete_bucket(self, name: str) -> dict:
        self.calls.append("delete_bucket")
        return {"deleted": True}

    def close(self) -> None:
        self.calls.append("close")

    def presign_put(self, bucket: str, key: str, **kwargs: object) -> dict:
        self.calls.append("presign_put")
        return {"url": "https://upload.example"}

    def presign_get(self, bucket: str, key: str) -> dict:
        self.calls.append("presign_get")
        return {"url": "https://read.example"}

    def object_head(self, bucket: str, key: str) -> dict:
        self.calls.append("object_head")
        return {"found": True}

    def resize_image(self, image: str, **kwargs: object) -> dict:
        self.calls.append("resize_image")
        return {"stored": True}


def test_high_risk_payment_is_held_without_processing() -> None:
    client = RecordingClient()
    service = PaymentEvidenceService(client, "evidence")
    event = PaymentEvent(
        event_id=UUID("11111111-1111-4111-8111-111111111111"),
        payment_id=UUID("22222222-2222-4222-8222-222222222222"),
        event_type=PaymentEventType.CAPTURED,
        amount_minor=12500,
        currency="USD",
        risk_score=82,
        occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    request = VariantRequest(
        event=event,
        object_key="payments/receipt.png",
        variants=[VariantSpec(width=640, height=640)],
    )

    result = service.make_variants(request)

    assert result.action == ReviewAction.HOLD_FOR_REVIEW
    assert result.outputs == []
    assert result.notification["action"] == "hold_for_review"
    assert client.calls == ["create_bucket"]


def test_service_deletes_its_bucket_when_closed() -> None:
    client = RecordingClient()
    service = PaymentEvidenceService(client, "evidence")

    service.close()

    assert client.calls == ["create_bucket", "delete_bucket", "close"]
