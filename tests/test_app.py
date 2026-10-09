import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from main import MAX_BYTES, create_app
from storage import LocalBackend


def image_bytes(fmt="PNG", size=(20, 20)):
    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("INVITE_CODE", "letmein")
    store = LocalBackend(tmp_path)
    return create_app(store).test_client(), store


def upload(client, raw, code="letmein", name="a.png"):
    return client.post("/upload", data={"code": code, "file": (io.BytesIO(raw), name)},
                       content_type="multipart/form-data")


def test_upload_then_view(setup):
    client, _ = setup
    r = upload(client, image_bytes())
    assert r.status_code == 201
    path = "/i/" + r.get_json()["url"].rsplit("/", 1)[1]
    got = client.get(path)
    assert got.status_code == 200 and got.mimetype == "image/png"


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
def test_other_allowed_formats(setup, fmt):
    client, _ = setup
    assert upload(client, image_bytes(fmt)).status_code == 201


def test_wrong_code_rejected(setup):
    assert upload(setup[0], image_bytes(), code="nope").status_code == 403


def test_no_invite_configured_blocks_uploads(tmp_path, monkeypatch):
    monkeypatch.delenv("INVITE_CODE", raising=False)
    client = create_app(LocalBackend(tmp_path)).test_client()
    assert upload(client, image_bytes(), code="").status_code == 403


def test_non_image_rejected(setup):
    assert upload(setup[0], b"<script>alert(1)</script>").status_code == 400


def test_gif_rejected(setup):
    assert upload(setup[0], image_bytes("GIF")).status_code == 400


def test_oversize_rejected(setup):
    assert upload(setup[0], b"0" * (MAX_BYTES + 1)).status_code == 413


def test_exif_stripped(setup):
    client, store = setup
    exif = Image.Exif()
    exif[0x010F] = "SecretCameraMaker"
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="JPEG", exif=exif)
    assert b"SecretCameraMaker" in buf.getvalue()  # sanity check: the input really has EXIF
    r = upload(client, buf.getvalue(), name="a.jpg")
    data, _ = store.get(r.get_json()["url"].rsplit("/", 1)[1])
    assert b"SecretCameraMaker" not in data


def test_expired_image_is_gone(setup):
    client, store = setup
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    store.put("abcd1234", image_bytes(), {"content_type": "image/png", "size": 1,
                                          "created_at": past, "expires_at": past})
    assert client.get("/i/abcd1234").status_code == 404


def test_bad_ids_404(setup):
    client, _ = setup
    assert client.get("/i/..%2f..%2fetc").status_code == 404
    assert client.get("/i/short").status_code == 404
    assert client.get("/i/zzzzzzzz").status_code == 404


def test_health_and_index(setup):
    client, _ = setup
    assert client.get("/healthz").data == b"ok"
    assert b"Photo Drop" in client.get("/").data
