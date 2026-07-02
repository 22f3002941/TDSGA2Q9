from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import uuid
import time
import math
import os

app = FastAPI()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- CONFIG ----------------
TOTAL_ORDERS = 48
RATE_LIMIT = 19
WINDOW = 10

# ---------------- STATE ----------------
idempotency_store = {}
rate_buckets = defaultdict(deque)


# ---------------- RATE LIMIT ----------------
def check_rate_limit(client_id: str):
    client_id = client_id or "anonymous"

    now = time.time()
    bucket = rate_buckets[client_id]

    # Remove expired timestamps
    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry_after = max(
            1,
            math.ceil(WINDOW - (now - bucket[0]))
        )

        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after)
            }
        )

    bucket.append(now)
    return None


# ---------------- IDEMPOTENT POST ----------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    # POST is intentionally NOT rate limited.

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return order


# ---------------- CURSOR PAGINATION ----------------
@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1),
    cursor: str | None = Query(None),
    x_client_id: str = Header(..., alias="X-Client-Id"),
):
    rl = check_rate_limit(x_client_id)
    if rl is not None:
        return rl

    start = 1 if cursor is None else int(cursor)

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [
        {"id": i}
        for i in range(start, end + 1)
    ]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = str(end + 1)

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# ---------------- ROOT ----------------
@app.get("/")
def root():
    return {"status": "ok"}


@app.head("/")
def root_head():
    return JSONResponse(content=None, status_code=200)


@app.get("/healthz")
def health():
    return {"status": "ok"}


# ---------------- DEBUG ----------------
@app.get("/debug")
def debug():
    return {
        "bucket_count": len(rate_buckets),
        "clients": list(rate_buckets.keys()),
        "pid": os.getpid()
    }


# ---------------- TEST ENDPOINT ----------------
@app.get("/test429")
def test429():
    return JSONResponse(
        status_code=429,
        content={"detail": "test"},
        headers={
            "Retry-After": "10"
        }
    )


# ---------------- VERSION ----------------
@app.get("/version")
def version():
    return {
        "version": "FINAL-JUL2",
        "rate_limit": RATE_LIMIT,
        "window": WINDOW
    }