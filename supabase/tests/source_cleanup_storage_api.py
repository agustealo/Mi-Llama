from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_URL = os.environ.get("API_URL", "http://127.0.0.1:54321").rstrip("/")
ANON_KEY = os.environ["ANON_KEY"]
SERVICE_ROLE_KEY = os.environ["SERVICE_ROLE_KEY"]
BUCKET = "mi-llama-sources"


def request(
    method: str,
    path: str,
    *,
    key: str,
    token: str | None = None,
    json_body: object | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
    expected: set[int] | None = None,
) -> tuple[int, bytes]:
    headers = {"apikey": key}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif data is not None:
        headers["Content-Type"] = content_type

    req = urllib.request.Request(f"{API_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read()

    allowed = expected or {200, 201, 204}
    if status not in allowed:
        raise AssertionError(
            f"{method} {path} returned {status}, expected {sorted(allowed)}: "
            f"{body.decode(errors='replace')}"
        )
    return status, body


def create_user(email: str, password: str) -> tuple[str, str]:
    _, body = request(
        "POST",
        "/auth/v1/admin/users",
        key=SERVICE_ROLE_KEY,
        token=SERVICE_ROLE_KEY,
        json_body={"email": email, "password": password, "email_confirm": True},
    )
    user_id = json.loads(body)["id"]
    _, body = request(
        "POST",
        "/auth/v1/token?grant_type=password",
        key=ANON_KEY,
        json_body={"email": email, "password": password},
    )
    return user_id, json.loads(body)["access_token"]


def post_rest(table: str, token: str, payload: object) -> list[dict[str, object]]:
    _, body = request(
        "POST",
        f"/rest/v1/{table}",
        key=ANON_KEY,
        token=token,
        json_body=payload,
        extra_headers={"Prefer": "return=representation"},
    )
    return json.loads(body)


def main() -> None:
    suffix = uuid.uuid4().hex[:12]
    owner_id, owner_token = create_user(
        f"storage-owner-{suffix}@example.test", "MiLlama-Test-Owner-42!"
    )
    editor_id, editor_token = create_user(
        f"storage-editor-{suffix}@example.test", "MiLlama-Test-Editor-42!"
    )

    project_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    path = f"{project_id}/{source_id}/{version_id}/revoked-cleanup.txt"
    checksum = "a" * 64

    post_rest(
        "projects",
        owner_token,
        {"id": project_id, "owner_id": owner_id, "title": "Storage API revocation burn"},
    )
    post_rest(
        "project_members",
        owner_token,
        {"project_id": project_id, "user_id": editor_id, "role": "editor"},
    )
    post_rest(
        "sources",
        editor_token,
        {
            "id": source_id,
            "project_id": project_id,
            "created_by": editor_id,
            "filename": "revoked-cleanup.txt",
            "media_type": "text/plain",
            "kind": "text",
            "checksum_sha256": checksum,
            "size_bytes": 25,
            "status": "processing",
        },
    )
    post_rest(
        "source_versions",
        editor_token,
        {
            "id": version_id,
            "source_id": source_id,
            "project_id": project_id,
            "created_by": editor_id,
            "version_number": 1,
            "storage_path": path,
            "checksum_sha256": checksum,
            "parser": "plain-text",
            "character_count": 25,
            "status": "processing",
            "research_status": "not_indexed",
        },
    )

    encoded_path = urllib.parse.quote(path, safe="/")
    request(
        "POST",
        f"/storage/v1/object/{BUCKET}/{encoded_path}",
        key=ANON_KEY,
        token=editor_token,
        data=b"source awaiting cleanup\n",
        content_type="text/plain",
        extra_headers={"x-upsert": "false"},
    )

    filters = urllib.parse.urlencode(
        {"project_id": f"eq.{project_id}", "user_id": f"eq.{editor_id}"}
    )
    request(
        "DELETE",
        f"/rest/v1/project_members?{filters}",
        key=ANON_KEY,
        token=owner_token,
    )

    # The revoked editor can no longer mutate source state.
    status, body = request(
        "PATCH",
        f"/rest/v1/sources?id=eq.{source_id}",
        key=ANON_KEY,
        token=editor_token,
        json_body={"error_message": "must not persist"},
        extra_headers={"Prefer": "return=representation"},
        expected={200},
    )
    if status != 200 or json.loads(body) != []:
        raise AssertionError("revoked editor unexpectedly mutated source state")

    # Cleanup must still work through the real Storage API for the exact object
    # created by this ingest attempt.
    request(
        "DELETE",
        f"/storage/v1/object/{BUCKET}",
        key=ANON_KEY,
        token=editor_token,
        json_body={"prefixes": [path]},
    )

    # Service-role read is used only to prove the physical object is gone.
    request(
        "GET",
        f"/storage/v1/object/authenticated/{BUCKET}/{encoded_path}",
        key=SERVICE_ROLE_KEY,
        token=SERVICE_ROLE_KEY,
        expected={400, 404},
    )

    print("Storage API revocation cleanup burn passed")


if __name__ == "__main__":
    main()
