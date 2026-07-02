from fastapi import FastAPI, Request, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from collections import defaultdict, deque
import time
import uuid

app = FastAPI()

# ---------------- CORS (REQUIRED) ----------------
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
WINDOW = 10  # seconds

# ---------------- STATE ----------------
idempotency_store = {}  # key -> response
rate_buckets = defaultdict(deque)

# ---------------- RATE LIMIT RESPONSE ----------------
def rate_limit_response(retry_after: int):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
        headers={"Retry-After": str(retry_after)}
    )

# ---------------- RATE LIMIT LOGIC ----------------
def check_rate_limit(client_id: str):
    if not client_id:
        client_id = "anonymous"

    now = time.time()
    dq = rate_buckets[client_id]

    # remove expired requests
    while dq and now - dq[0] > WINDOW:
        dq.popleft()

    # enforce limit
    if len(dq) >= RATE_LIMIT:
        retry_after = int(WINDOW - (now - dq[0]))
        return rate_limit_response(max(retry_after, 1))

    dq.append(now)
    return None

# ---------------- 1. IDEMPOTENT ORDER CREATION ----------------
@app.post("/orders")
def create_order(
    request: Request,
    idempotency_key: str = Header(None),
    x_client_id: str = Header(None)
):
    rl = check_rate_limit(x_client_id)
    if rl:
        return rl

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key")

    # return cached response
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
    rl = check_rate_limit(x_client_id)
    if rl:
        return rl

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