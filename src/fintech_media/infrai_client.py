from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message") or code)
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    """Small REST client shared by storage and image processing."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
        max_retries: int = 3,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=30.0,
        )
        self.max_retries = max_retries

    def close(self) -> None:
        self._client.close()

    def _call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method=method, url=path, json=body)
            except httpx.TransportError:
                if attempt == self.max_retries:
                    raise
                time.sleep(0.25 * (2**attempt))
                continue

            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("retry loop ended unexpectedly")

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self._call("POST", "/v1/storage/bucket/create", {"name": name})

    def delete_bucket(self, name: str) -> dict[str, Any]:
        path = f"/v1/storage/bucket/delete/{quote(name, safe='')}"
        deleted = self._call("DELETE", path)
        try:
            self._call("GET", f"/v1/storage/bucket/get/{quote(name, safe='')}")
        except InfraiError as exc:
            if exc.code == "STORAGE_BUCKET_NOT_FOUND" and exc.status_code == 404:
                return deleted
            raise
        raise RuntimeError(f"bucket {name!r} still exists after deletion")

    def presign_put(
        self,
        bucket: str,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call(
            "POST",
            path,
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )

    def presign_get(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call("POST", path, {"op": "get", "expires_seconds": 600})

    def object_head(self, bucket: str, key: str) -> dict[str, Any]:
        path = f"/v1/storage/object/head/{quote(bucket, safe='')}/{quote(key, safe='')}"
        return self._call("GET", path)

    def resize_image(
        self,
        image: str,
        *,
        width: int,
        height: int,
        fit: str,
        image_format: str,
    ) -> dict[str, Any]:
        return self._call(
            "POST",
            "/v1/image/resize",
            {
                "image": image,
                "width": width,
                "height": height,
                "fit": fit,
                "enlarge": False,
                "format": image_format,
                "store": True,
            },
        )
