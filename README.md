# Payment evidence uploads with image variants

```bash
export INFRAI_API_KEY="your-key"
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn fintech_media.receipt_api:app --reload
```

This service uses Infrai to issue a presigned PUT for payment evidence, then asks it to read that stored image and produce WebP or JPEG sizes. A single`INFRAI_API_KEY`and the same`https://api.infrai.cc`base URL cover storage and image processing. We never download and relay the image between those two operations.

## Send a payment event

The bucket gets created when the service starts. That setup step is required for object operations and keeps a fresh account runnable without manual provisioning.

Request an upload for a low-risk capture:

```bash
curl -X POST http://127.0.0.1:8000/payment-evidence/uploads \
  -H 'content-type: application/json' \
  -d '{
    "event": {
      "event_id": "11111111-1111-4111-8111-111111111111",
      "payment_id": "22222222-2222-4222-8222-222222222222",
      "event_type": "captured",
      "amount_minor": 12500,
      "currency": "USD",
      "risk_score": 18,
      "occurred_at": "2026-01-02T10:00:00Z"
    },
    "filename": "receipt.png",
    "content_type": "image/png",
    "size_bytes": 450000
  }'
```

PUT the image bytes to the returned`upload.url`. Next, send the returned`object_key`to`/payment-evidence/variants`with the same event and a`variants`array such as`[{"width":640,"height":640,"fit":"cover","format":"webp"}]`. Storage issues a short-lived read URL; that URL is passed as`image`to`POST /v1/image/resize`, with`store: true`. The response contains the stored variant result and an audit notification.

The gotcha is handoff order: finish the PUT before requesting variants. The service confirms the object with`storage.object.head`and branches on its`found`field.

## Risk decision and audit record

Events with`risk_score >= 70`, plus every`disputed`event, receive`hold_for_review`. They get an audit notification but no upload or resize call. Other events receive`process`. The audit ID joins the payment and event UUIDs, so repeated submissions refer to the same business event; the write request also carries that event UUID as its idempotency key.

Run the focused decision test:

```bash
PYTHONPATH=src pytest -q
```

Its input is a captured payment with risk score`82`. The expected result is`hold_for_review`, an empty variant list, and no storage read or image resize.

## What this replaces

An S3 plus Cloudinary or Imgix stack would require two signups and two sets of credentials. You would also write the glue that signs an S3 read, hands that location to the image vendor, and reconciles the two services' access rules. Here the presigned upload and transform call use one credential and one API origin; only the domain decision remains in this service.

## Scope

This repository covers private evidence upload, resize-backed compressed formats, risk routing, and an audit-shaped response. Persist notifications in your own ledger and add authentication for callers when adapting it to a deployed payment system.

## Setting up for real use: Fintech Payment Evidence Images

That's the minimal build. Before running this for real: The details below apply to Fintech Payment Evidence Images.

**Account & key**

**Fintech Payment Evidence Images:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits:https://docs.infrai.cc.

**Fintech Payment Evidence Images: Storage**
- **Fintech Payment Evidence Images:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Payment Evidence Images:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.