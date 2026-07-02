from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict, deque
import time
import uuid

app = FastAPI()

# ---------------- CORS (MANDATORY) ----------------
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
WINDOW_SECONDS = 10

# ---------------- STORAGE ----------------
idempotency_store = {}  # key -> response
rate_buckets = defaultdict(deque)

# ---------------- RATE LIMIT ----------------
def check_rate_limit(client_id: str):
    if not client_id:
        client_id = "anonymous"

    now = time.time()
    dq = rate_buckets[client_id]

    # remove expired timestamps
    while dq and now - dq[0] > WINDOW_SECONDS:
        dq.popleft()

    # enforce limit
    if len(dq) >= RATE_LIMIT:
        retry_after = int(WINDOW_SECONDS - (now - dq[0]))
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(max(retry_after, 1))}
        )

    dq.append(now)


# ---------------- 1. IDEMPOTENT ORDER CREATION ----------------
@app.post("/orders")
def create_order(
    request: Request,
    idempotency_key: str = Header(None),
    x_client_id: str = Header(None)
):
    check_rate_limit(x_client_id)

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key")

    # return cached response if exists
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order
    return order


# ---------------- 2. CURSOR PAGINATION ----------------
@app.get("/orders")
def list_orders(
    limit: int = Query(10),
    cursor: int = Query(0),
    x_client_id: str = Header(None)
):
    check_rate_limit(x_client_id)

    start = cursor
    end = min(cursor + limit, TOTAL_ORDERS)

    items = [{"id": i} for i in range(start + 1, end + 1)]

    next_cursor = end if end < TOTAL_ORDERS else None

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# ---------------- OPTIONAL HEALTH ----------------
@app.get("/healthz")
def health():
    return {"status": "ok"}