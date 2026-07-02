from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import uuid
import time
import math
import os

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


def check_rate_limit(client_id: str):
    now = time.time()
    bucket = rate_buckets[client_id]

    # Remove expired timestamps
    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    # Limit reached
    if len(bucket) >= RATE_LIMIT:
        retry_after = max(
            1,
            math.ceil(WINDOW - (now - bucket[0]))
        )

        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )
        response.headers["Retry-After"] = str(retry_after)
        return response

    bucket.append(now)
    return None


@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    # Do NOT count POSTs towards the rate limit.

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
    x_client_id: str = Header(..., alias="X-Client-Id"),
):
    rl = check_rate_limit(x_client_id)
    if rl:
        return rl

    start = 1 if cursor is None else int(cursor)
    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start, end + 1)]

    next_cursor = str(end + 1) if end < TOTAL_ORDERS else None

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
    return {
        "bucket_count": len(rate_buckets),
        "clients": list(rate_buckets.keys()),
        "pid": os.getpid(),
    }


@app.get("/test429")
def test429():
    response = JSONResponse(
        status_code=429,
        content={"detail": "test"},
    )
    response.headers["Retry-After"] = "10"
    return response