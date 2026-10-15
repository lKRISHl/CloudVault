"""Actual Docker API/SMTP/presigned upload smoke; unique development demo data remains."""

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx


def require(response, status):
    if response.status_code != status:
        raise RuntimeError(
            f"Docker upload smoke expected HTTP {status}, got {response.status_code}"
        )
    return response.json()


def verify_email(api, email):
    token = None
    with httpx.Client(base_url="http://localhost:8025", timeout=10) as inbox:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and token is None:
            messages = require(
                inbox.get("/api/v1/search", params={"query": f"to:{email}"}), 200
            )["messages"]
            for message in messages:
                mail = require(inbox.get("/api/v1/message/" + message["ID"]), 200)
                for line in mail.get("Text", "").splitlines():
                    if line.startswith("http") and "purpose=verify" in line:
                        token = parse_qs(urlsplit(line.strip()).fragment)["token"][0]
            if token is None:
                time.sleep(0.2)
    if token is None:
        raise RuntimeError("Docker verification email did not arrive")
    require(api.post("/account/verify", json={"token": token}), 200)


def main():
    email = f"phase9-smoke-{uuid4().hex}@example.com"
    body = b"CloudVault verified Docker upload"
    checksum = base64.b64encode(hashlib.sha256(body).digest()).decode()
    with httpx.Client(base_url="http://localhost:3000/api/v1", timeout=20) as api:
        session = require(
            api.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": uuid4().hex,
                    "full_name": "Upload Smoke",
                    "tenant_name": "Phase 9 Upload Smoke " + uuid4().hex[:8],
                },
            ),
            201,
        )
        api.headers["Authorization"] = "Bearer " + session["access_token"]
        verify_email(api, email)
        ticket = require(
            api.post(
                "/files/uploads",
                json={
                    "name": "Verified Docker upload.txt",
                    "declared_size_bytes": len(body),
                    "declared_content_type": "text/plain",
                    "checksum_sha256": checksum,
                    "request_id": str(uuid4()),
                },
            ),
            201,
        )
        try:
            with httpx.Client(timeout=20) as storage:
                response = storage.put(
                    ticket["upload_url"], content=body, headers=ticket["headers"]
                )
                if response.status_code != 200:
                    raise RuntimeError("Docker object transfer failed")
        except httpx.HTTPError:
            raise RuntimeError("Docker object transfer unavailable") from None
        uploaded = require(api.post(f"/files/{ticket['file']['id']}/complete"), 200)
        assert uploaded["status"] == "uploaded" and uploaded["size_bytes"] == len(body)
        assert uploaded["checksum_sha256"] == checksum
        download_response = api.post(f"/files/{uploaded['id']}/download-url")
        download = require(download_response, 200)
        assert download_response.headers["cache-control"] == "no-store"
        with httpx.Client(timeout=20) as transfer:
            received = transfer.get(download["download_url"])
            assert received.status_code == 200 and received.content == body
            assert received.headers["content-type"] == "application/octet-stream"
            assert received.headers["content-disposition"].startswith("attachment;")
        page = require(api.get("/files"), 200)
        assert any(file["id"] == uploaded["id"] for file in page["items"])
        found_response = api.get(
            "/files/search", params={"q": "verified docker", "status": "uploaded"}
        )
        found = require(found_response, 200)
        assert found_response.headers["cache-control"] == "no-store"
        assert [file["id"] for file in found["items"]] == [uploaded["id"]]
        config = require(api.get("/files/upload-configuration"), 200)
        part_size = config["multipart_part_size"]
        chunks = [b"M" * part_size, b"CloudVault multipart tail"]
        hashes = [
            base64.b64encode(hashlib.sha256(chunk).digest()).decode()
            for chunk in chunks
        ]
        multipart = require(
            api.post(
                "/files/multipart/uploads",
                json={
                    "name": "Verified multipart Docker upload.bin",
                    "declared_size_bytes": sum(map(len, chunks)),
                    "part_size": part_size,
                    "checksums": hashes,
                    "request_id": str(uuid4()),
                },
            ),
            201,
        )
        file_id = multipart["file"]["id"]
        with httpx.Client(timeout=30) as transfer:
            for part, chunk in zip(multipart["parts"], chunks, strict=True):
                sent = transfer.put(
                    part["upload_url"], content=chunk, headers=part["headers"]
                )
                assert sent.status_code == 200
                require(
                    api.post(
                        f"/files/{file_id}/multipart/parts/{part['number']}/confirm"
                    ),
                    200,
                )
                if part["number"] == 1:
                    saved = require(
                        api.post(f"/files/{file_id}/multipart/progress"), 200
                    )
                    assert saved["confirmed_bytes"] == part_size and saved["can_resume"]
                    resumed = require(
                        api.post(
                            f"/files/{file_id}/multipart/resume",
                            json={"checksums": hashes},
                        ),
                        200,
                    )
                    assert (
                        resumed["file"]["id"] == file_id
                        and resumed["parts"][0]["upload_url"] is None
                    )
                    multipart["parts"][1] = resumed["parts"][1]
            completed = require(api.post(f"/files/{file_id}/multipart/complete"), 200)
            expected = base64.b64encode(
                hashlib.sha256(
                    b"".join(base64.b64decode(value) for value in hashes)
                ).digest()
            ).decode()
            assert (
                completed["checksum_kind"] == "sha256-composite"
                and completed["checksum_sha256"] == expected
            )
            download = require(api.post(f"/files/{file_id}/download-url"), 200)
            received = transfer.get(download["download_url"])
            assert received.status_code == 200 and received.content == b"".join(chunks)
        sorted_files = require(
            api.get(
                "/files/search",
                params={
                    "scope": "root",
                    "status": "uploaded",
                    "sort": "size",
                    "direction": "desc",
                    "limit": 1,
                },
            ),
            200,
        )
        assert sorted_files["has_more"] and sorted_files["items"][0]["id"] == file_id
        next_page = require(
            api.get(
                "/files/search",
                params={
                    "scope": "root",
                    "status": "uploaded",
                    "sort": "size",
                    "direction": "desc",
                    "limit": 1,
                    "offset": 1,
                },
            ),
            200,
        )
        assert (
            not next_page["has_more"] and next_page["items"][0]["id"] == uploaded["id"]
        )
        password = uuid4().hex
        shared = require(
            api.post(
                f"/files/{file_id}/shares",
                json={
                    "password": password,
                    "max_downloads": 1,
                    "expires_in_hours": 1,
                },
            ),
            201,
        )
        raw = parse_qs(urlsplit(shared["share_url"]).fragment)["token"][0]
        with httpx.Client(
            base_url="http://localhost:3000/api/v1", timeout=20
        ) as recipient:
            assert (
                recipient.post("/shares/access", json={"token": raw}).status_code == 404
            )
            proof = {"token": raw, "password": password}
            metadata = require(recipient.post("/shares/access", json=proof), 200)
            assert metadata["name"] == completed["name"]
            response = recipient.post("/shares/download-url", json=proof)
            grant = require(response, 200)
            assert response.headers["cache-control"] == "no-store"
            with httpx.Client(timeout=30) as transfer:
                received = transfer.get(grant["download_url"])
                assert received.status_code == 200 and received.content == b"".join(
                    chunks
                )
            assert recipient.post("/shares/download-url", json=proof).status_code == 403
            revoked = api.delete(f"/files/{file_id}/shares/{shared['id']}")
            assert revoked.status_code == 204
            assert recipient.post("/shares/access", json=proof).status_code == 404
            metadata_only = require(
                api.post(
                    f"/files/{uploaded['id']}/shares",
                    json={
                        "allow_download": False,
                    },
                ),
                201,
            )
            metadata_token = parse_qs(urlsplit(metadata_only["share_url"]).fragment)[
                "token"
            ][0]
            assert (
                require(
                    recipient.post("/shares/access", json={"token": metadata_token}),
                    200,
                )["allow_download"]
                is False
            )
            assert (
                recipient.post(
                    "/shares/download-url", json={"token": metadata_token}
                ).status_code
                == 403
            )
            assert (
                api.delete(
                    f"/files/{uploaded['id']}/shares/{metadata_only['id']}"
                ).status_code
                == 204
            )
        member_email = f"permission-smoke-{uuid4().hex}@example.com"
        invitation = require(
            api.post(
                "/organizations/current/invitations",
                json={
                    "email": member_email,
                    "role": "member",
                },
            ),
            201,
        )
        with httpx.Client(
            base_url="http://localhost:3000/api/v1", timeout=20
        ) as member:
            joined = require(
                member.post(
                    "/organizations/invitations/accept",
                    json={
                        "token": invitation["token"],
                        "full_name": "Permission Smoke",
                        "password": uuid4().hex,
                    },
                ),
                201,
            )
            member.headers["Authorization"] = "Bearer " + joined["access_token"]
            verify_email(member, member_email)
            fid = uploaded["id"]
            assert (
                api.patch(
                    f"/files/{fid}/permissions", json={"visibility": "private"}
                ).status_code
                == 204
            )
            assert member.get(f"/files/{fid}").status_code == 404
            hidden = require(
                member.get("/files/search", params={"q": "Verified Docker upload.txt"}),
                200,
            )
            assert not hidden["items"] and not hidden["has_more"]
            uid = joined["user"]["id"]
            assert (
                api.put(
                    f"/files/{fid}/permissions/{uid}", json={"role": "viewer"}
                ).status_code
                == 204
            )
            visible = require(member.get(f"/files/{fid}"), 200)
            assert not visible["can_write"] and not visible["can_manage"]
            grant = require(member.post(f"/files/{fid}/download-url"), 200)
            with httpx.Client(timeout=20) as transfer:
                received = transfer.get(grant["download_url"])
                assert received.status_code == 200 and received.content == body
            assert (
                api.put(
                    f"/files/{fid}/permissions/{uid}", json={"role": "editor"}
                ).status_code
                == 204
            )
            renamed = require(
                member.patch(
                    f"/files/{fid}", json={"name": "Edited Docker upload.txt"}
                ),
                200,
            )
            assert renamed["can_write"] and not renamed["can_manage"]
            assert member.get(f"/files/{fid}/permissions").status_code == 403
            assert member.post(f"/files/{fid}/shares", json={}).status_code == 403
            assert (
                api.put(
                    f"/files/{fid}/permissions/{uid}", json={"role": None}
                ).status_code
                == 204
            )
            assert member.get(f"/files/{fid}").status_code == 404
        trashed = require(api.post(f"/files/{fid}/trash"), 201)
        assert api.get(f"/files/{fid}").status_code == 404
        page = require(api.get("/trash"), 200)
        assert any(item["id"] == trashed["id"] for item in page["items"])
        assert api.post(f"/trash/{trashed['id']}/restore").status_code == 204
        restored = require(api.post(f"/files/{fid}/download-url"), 200)
        with httpx.Client(timeout=20) as transfer:
            assert transfer.get(restored["download_url"]).content == body
        trashed = require(api.post(f"/files/{fid}/trash"), 201)
        assert (
            api.post(
                f"/trash/{trashed['id']}/purge", json={"confirmation": "DELETE"}
            ).status_code
            == 202
        )
        assert api.post(f"/trash/{trashed['id']}/restore").status_code == 409
        empty = require(
            api.post("/folders", json={"name": "Recoverable smoke folder"}), 201
        )
        folder_trash = require(api.post(f"/folders/{empty['id']}/trash"), 201)
        assert api.post(f"/trash/{folder_trash['id']}/restore").status_code == 204
        print(
            "Docker SMTP/transfers/search/sharing/ACL and file/folder trash/restore/purge queue passed"
        )
        print("Unique smoke accounts/workspace/two files retained as development data")


if __name__ == "__main__":
    main()
