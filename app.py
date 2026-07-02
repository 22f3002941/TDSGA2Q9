from fastapi import FastAPI, Request, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
import time
import uuid
from collections import defaultdict, deque

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
T = 48
RATE_LIMIT = 19
WINDOW = 10  # seconds

orders_store = {}
idempotency_store = {}

# client_id -> timestamps
rate_buckets = defaultdict(deque)

# ---------------- RATE LIMIT ----------------
def check_rate_limit(client_id: str):
    now = time.time()
    dq = rate_buckets[client_id]

    # remove old timestamps
    while dq and now - dq[0] > WINDOW:
        dq.popleft()

    if len(dq) >= RATE_LIMIT:
        retry_after = WINDOW - (now - dq[0])
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(int(retry_after))}
        )

    dq.append(now)


# ---------------- 1. IDENTITY / ORDERS ----------------
@app.post("/orders")
def create_order(request: Request, idempotency_key: str = Header(None), client_id: str = Header(None)):
    if client_id:
        check_rate_limit(client_id)

    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Missing Idempotency-Key")

    # return cached response
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order_id = str(uuid.uuid4())
    order = {"id": order_id}

    idempotency_store[idempotency_key] = order
    orders_store[order_id] = order

    return order


# ---------------- 2. PAGINATION ----------------
@app.get("/orders")
def list_orders(limit: int = Query(10), cursor: int = Query(0), client_id: str = Header(None)):
    if client_id:
        check_rate_limit(client_id)

    start = cursor
    end = min(cursor + limit, T)

    items = [{"id": i} for i in range(start + 1, end + 1)]

    next_cursor = end if end < T else None

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# ---------------- 3. RATE LIMIT TEST HELPER OPTIONAL ----------------
@app.get("/ping")
def ping(client_id: str = Header(None)):
    if client_id:
        check_rate_limit(client_id)
    return {"ok": True}