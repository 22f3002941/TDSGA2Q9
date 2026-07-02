from fastapi import FastAPI, Header, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import uuid
import time
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 48
RATE_LIMIT = 19
WINDOW = 10

idempotency_store = {}
rate_buckets = defaultdict(deque)


def check_rate_limit(client_id: str | None):
    client_id = client_id or "anonymous"

    now = time.time()
    bucket = rate_buckets[client_id]

    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry_after = max(
            1,
            math.ceil(WINDOW - (now - bucket[0]))
        )

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after)
            },
        )

    bucket.append(now)


@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    x_client_id: str | None = Header(None, alias="X-Client-Id"),
):
    #check_rate_limit(x_client_id)

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order
    return order


@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1),
    cursor: str | None = Query(None),
    x_client_id: str | None = Header(None, alias="X-Client-Id"),
):
    check_rate_limit(x_client_id)

    if cursor is None:
        start = 1
    else:
        start = int(cursor)

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start, end + 1)]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = str(end + 1)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/debug")
def debug():
    import os

    return {
        "bucket_count": len(rate_buckets),
        "clients": list(rate_buckets.keys()),
        "pid": os.getpid(),
    }


@app.get("/test429")
def test429():
    raise HTTPException(
        status_code=429,
        detail="test",
        headers={
            "Retry-After": "10"
        },
    )