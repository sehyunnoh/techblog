#!/usr/bin/env python3
"""Payload size of the same 50 orders as JSON and as Protocol Buffers.

No third-party packages. The protobuf bytes come from a small hand-written
encoder that follows https://protobuf.dev/programming-guides/encoding/ and is
checked against the documented example (a = 150 encodes to 08 96 01).

Run:  python3 api-payload-bench.py
"""
import gzip
import json
import random
import struct
from datetime import datetime, timezone


# ---- minimal protobuf encoder (varint and length-delimited only) ----------
def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def tag(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def f_varint(field: int, value: int) -> bytes:
    return tag(field, 0) + varint(value)


def f_bytes(field: int, payload: bytes) -> bytes:
    return tag(field, 2) + varint(len(payload)) + payload


# documented example from the protobuf encoding guide
assert f_varint(1, 150) == bytes.fromhex("089601")
assert f_bytes(2, b"testing") == bytes.fromhex("120774657374696e67")

STATUS = {"PENDING": 1, "PAID": 2, "SHIPPED": 3, "DELIVERED": 4}


def make_orders(n: int, seed: int = 42):
    rnd = random.Random(seed)
    base = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
    orders = []
    for i in range(n):
        orders.append(
            {
                "id": 100000 + i,
                "customer_id": 42,
                "status": rnd.choice(list(STATUS)),
                "total_cents": rnd.randint(500, 250000),
                "created_at": base + rnd.randint(0, 40 * 86400),
                "item_count": rnd.randint(1, 12),
            }
        )
    return orders


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_json(orders, iso_dates: bool, envelope=None) -> bytes:
    rows = [
        {
            "id": o["id"],
            "customerId": o["customer_id"],
            "status": o["status"],
            "totalCents": o["total_cents"],
            "createdAt": iso(o["created_at"]) if iso_dates else o["created_at"],
            "itemCount": o["item_count"],
        }
        for o in orders
    ]
    doc = envelope(rows) if envelope else rows
    return json.dumps(doc, separators=(",", ":")).encode()


def order_pb(o) -> bytes:
    return (
        f_varint(1, o["id"])
        + f_varint(2, o["customer_id"])
        + f_varint(3, STATUS[o["status"]])
        + f_varint(4, o["total_cents"])
        + f_varint(5, o["created_at"])
        + f_varint(6, o["item_count"])
    )


def gz(b: bytes) -> int:
    return len(gzip.compress(b, 6, mtime=0))


def main():
    orders = make_orders(50)

    rest = to_json(orders, iso_dates=True)
    rest_epoch = to_json(orders, iso_dates=False)
    graphql = to_json(orders, iso_dates=True, envelope=lambda r: {"data": {"orders": r}})
    odata = to_json(
        orders,
        iso_dates=True,
        envelope=lambda r: {"@odata.context": "https://api.example.com/odata/$metadata#Orders", "value": r},
    )
    # gRPC unary: one response message holding a repeated field, plus the 5 byte frame header
    msg = b"".join(f_bytes(1, order_pb(o)) for o in orders)
    grpc_unary = b"\x00" + struct.pack(">I", len(msg)) + msg
    # gRPC server streaming: one framed message per order
    grpc_stream = b"".join(b"\x00" + struct.pack(">I", len(order_pb(o))) + order_pb(o) for o in orders)

    rows = [
        ("REST, JSON, ISO dates", rest),
        ("REST, JSON, epoch integers", rest_epoch),
        ("GraphQL response (data/orders envelope)", graphql),
        ("OData response (@odata.context + value)", odata),
        ("gRPC unary (protobuf, one message)", grpc_unary),
        ("gRPC server stream (50 framed messages)", grpc_stream),
    ]
    print(f"{'payload':44s} {'raw bytes':>10s} {'gzip bytes':>11s}")
    for name, b in rows:
        print(f"{name:44s} {len(b):10d} {gz(b):11d}")

    one = order_pb(orders[0])
    print()
    print(f"one order: protobuf {len(one)} bytes, JSON epoch {len(to_json(orders[:1], False)) - 2} bytes, JSON ISO {len(to_json(orders[:1], True)) - 2} bytes")

    # Request side for the same question: customer 42 and their 3 newest orders.
    graphql_q = json.dumps(
        {"query": "{ customer(id: 42) { name orders(first: 3, orderBy: CREATED_DESC) { id status totalCents } } }"},
        separators=(",", ":"),
    )
    odata_url = "/odata/Customers(42)?$select=Name&$expand=Orders($select=Id,Status,TotalCents;$orderby=CreatedAt desc;$top=3)"
    rest_url = "/customers/42?include=orders&orders.limit=3&fields=name"
    grpc_req = b"\x00" + struct.pack(">I", 4) + f_varint(1, 42) + f_varint(2, 3)
    print()
    print("request size for 'customer 42 with 3 newest orders':")
    print(f"  REST URL      {len(rest_url):4d} bytes (no body)")
    print(f"  OData URL     {len(odata_url):4d} bytes (no body)")
    print(f"  GraphQL POST  {len(graphql_q):4d} bytes (body)")
    print(f"  gRPC request  {len(grpc_req):4d} bytes (framed protobuf, plus HTTP/2 headers)")


if __name__ == "__main__":
    main()
