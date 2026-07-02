from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import time
import uuid
import math

app = FastAPI()

# ---------------- CORS ----------------
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

# ---------------- In-memory state ----------------
idempotency_store = {}
rate_buckets = defaultdict(deque)


# ---------------- Rate limiter ----------------
def enforce_rate_limit(client_id: str | None):
    client_id = client_id or "anonymous"

    now = time.time()
    bucket = rate_buckets[client_id]

    # Remove expired timestamps
    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    # Limit reached
    if len(bucket) >= RATE_LIMIT:
        retry_after = max(1, math.ceil(WINDOW - (now - bucket[0])))

        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after)
            },
        )

    bucket.append(now)
    return None


# ---------------- POST /orders ----------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_client_id: str | None = Header(None, alias="X-Client-Id"),
):

    rl = enforce_rate_limit(x_client_id)
    if rl:
        return rl

    if not idempotency_key:
        return JSONResponse(
            status_code=400,
            content={"detail": "Missing Idempotency-Key"},
        )

    if idempotency_key in idempotency_store:
        # Return the same object for repeated key
        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key],
        )

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
    )


# ---------------- GET /orders ----------------
@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1),
    cursor: str | None = Query(None),
    x_client_id: str | None = Header(None, alias="X-Client-Id"),
):

    rl = enforce_rate_limit(x_client_id)
    if rl:
        return rl

    if cursor is None:
        start = 1
    else:
        try:
            start = int(cursor)
        except ValueError:
            start = 1

    end = min(start + limit - 1, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start, end + 1)]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = str(end + 1)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.get("/healthz")
def health():
    return {"status": "ok"}