"""Actual nginx/WebSocket/SMTP/part receipt smoke; unique development demo data remains."""

import base64
import hashlib
import json
import time
from uuid import uuid4

import httpx
from upload_smoke import require, verify_email
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


def receipt(peer, file_id, amount):
    deadline = time.monotonic() + 15
    while (remaining := deadline - time.monotonic()) > 0:
        event = json.loads(peer.recv(timeout=remaining))
        assert "Realtime receipt smoke.bin" not in json.dumps(event)
        if (
            event.get("type") == "invalidate"
            and event.get("key") == "receipts"
            and {"id": file_id, "bytes": amount} in event.get("progress", [])
        ):
            return
    raise RuntimeError("Own confirmed receipt did not arrive over the live proxy")


def main():
    email = f"phase19-live-{uuid4().hex}@example.com"
    with httpx.Client(base_url="http://localhost:3000/api/v1", timeout=20) as api:
        session = require(
            api.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": uuid4().hex,
                    "full_name": "Realtime Quota Smoke",
                    "tenant_name": "Owned realtime quota smoke",
                },
            ),
            201,
        )
        api.headers["Authorization"] = "Bearer " + session["access_token"]
        verify_email(api, email)
        ticket = require(api.post("/realtime/ticket"), 200)["ticket"]
        with connect(
            "ws://localhost:3000/api/v1/realtime/connect",
            origin="http://localhost:3000",
            open_timeout=10,
        ) as peer:
            peer.send(json.dumps({"op": "authenticate", "ticket": ticket}))
            assert json.loads(peer.recv(timeout=10))["type"] == "ready"
            peer.send(
                json.dumps(
                    {
                        "op": "subscribe",
                        "topics": [
                            {"key": "receipts", "kind": "files"},
                        ],
                    }
                )
            )
            part_size = require(api.get("/files/upload-configuration"), 200)[
                "multipart_part_size"
            ]
            chunks = [b"Q" * part_size, b"tail"]
            checksums = [
                base64.b64encode(hashlib.sha256(chunk).digest()).decode()
                for chunk in chunks
            ]
            grant = require(
                api.post(
                    "/files/multipart/uploads",
                    json={
                        "name": "Realtime receipt smoke.bin",
                        "declared_size_bytes": sum(map(len, chunks)),
                        "declared_content_type": "application/octet-stream",
                        "part_size": part_size,
                        "checksums": checksums,
                        "request_id": str(uuid4()),
                    },
                ),
                201,
            )
            file_id = grant["file"]["id"]
            receipt(peer, file_id, 0)
            part = grant["parts"][0]
            with httpx.Client(timeout=30) as provider:
                assert (
                    provider.put(
                        part["upload_url"], headers=part["headers"], content=chunks[0]
                    ).status_code
                    == 200
                )
            require(api.post(f"/files/{file_id}/multipart/parts/1/confirm"), 200)
            receipt(peer, file_id, part_size)
            require(api.post(f"/files/{file_id}/multipart/abort"), 200)
            usage = require(api.get("/organizations/current/storage-usage"), 200)
            assert usage["reserved_bytes"] >= sum(map(len, chunks))
            assert api.post("/auth/logout").status_code == 204
            deadline = time.monotonic() + 15
            try:
                while (remaining := deadline - time.monotonic()) > 0:
                    peer.recv(timeout=remaining)
            except ConnectionClosed as closed:
                assert closed.rcvd and closed.rcvd.code == 4401
            else:
                raise RuntimeError("Revoked login session retained a live connection")
    print(
        "nginx upgrade, opaque own receipts, retained quota and live session revocation OK"
    )


if __name__ == "__main__":
    main()
