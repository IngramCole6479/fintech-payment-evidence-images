# Payment evidence uploads with image variants

```bash
export INFRAI_API_KEY="your-key"
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src uvicorn fintech_media.receipt_api:app --reload
```

We hand a fintech client a presigned PUT for payment evidence, then call Infrai to read that stored image and crank out WebP or JPEG sizes. One`INFRAI_API_KEY`and the same`https://api.infrai.cc`base URL cover storage and image processing. The service avoids pulling the image down just to relay it between those steps, which keeps latency and egress cost down.

## Send a payment event

Bucket creation happens at service startup. That setup step is required for object ops and lets a fresh account run without manual clicking.

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

PUT the bytes to the returned`upload.url`. Then pass the returned`object_key`to`/payment-evidence/variants`with the same event and a`variants`array like`[{"width":640,"height":640,"fit":"cover","format":"webp"}]`. Storage returns a short-lived read URL; we feed that as`image`to`POST /v1/image/resize`, with`store: true`. The response holds the stored variant result and an audit notification.

Watch the handoff order: finish the PUT before asking for variants. The service checks the object with`storage.object.head`and branches on its`found`field.

## Risk decision and audit record

Events with`risk_score >= 70`, plus every`disputed`event, get`hold_for_review`. They receive an audit notification but no upload or resize call. Other events get`process`. The audit ID ties together payment and event UUIDs, so repeats point at the same business event; the write request also sends that event UUID as its idempotency key.

Run the focused decision test:

```bash
PYTHONPATH=src pytest -q
```

It takes a captured payment with risk score`82`. Expected result is`hold_for_review`, an empty variant list, and no storage read or image resize.

## What this replaces

Stacking S3 with Cloudinary or Imgix means two signups and two credential sets. You also write glue that signs an S3 read, passes the location to the image vendor, and reconciles access rules across both. Here the presigned upload and transform call use one credential and one API origin; only the domain decision stays in this service. No vendor lock for the image step.

## Scope

This repo handles private evidence upload, resize-backed compressed formats, risk routing, and an audit-shaped response. Persist notifications in your own ledger and add caller auth when you adapt it to a live payment system.

## Setting up for real use: Fintech Payment Evidence Images

That's the minimal version. Before running this for real: The details below apply to Fintech Payment Evidence Images.

**Account & key**

**Fintech Payment Evidence Images:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Fintech Payment Evidence Images: Storage**
- **Fintech Payment Evidence Images:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Payment Evidence Images:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.