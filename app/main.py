"""Photo Drop: invite-only image hosting. Upload an image, get a link that expires in 30 days."""
import hmac
import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from PIL import Image, UnidentifiedImageError
from werkzeug.middleware.proxy_fix import ProxyFix

from storage import make_backend

MAX_BYTES = 5 * 1024 * 1024
RETENTION_DAYS = 30
ALLOWED = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8}$")
Image.MAX_IMAGE_PIXELS = 25_000_000  # reject decompression bombs


def clean_image(raw):
    """Verify the bytes are really a JPEG/PNG/WebP and re-encode them (this drops EXIF/GPS data)."""
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        return None
    if fmt not in ALLOWED:
        return None
    out = io.BytesIO()
    img.save(out, format=fmt)
    return out.getvalue(), ALLOWED[fmt]


def create_app(backend=None):
    app = Flask(__name__, static_folder=None)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # correct https links behind Cloud Run
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 64 * 1024
    store = backend or make_backend()
    invite = os.environ.get("INVITE_CODE", "")  # empty = uploads disabled (fail closed)
    static_dir = os.path.join(os.path.dirname(__file__), "static")

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="That file is over the 5 MB limit."), 413

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.get("/healthz")
    def healthz():
        return "ok"

    @app.post("/upload")
    def upload():
        code = request.form.get("code", "")
        if not invite or not hmac.compare_digest(code.encode(), invite.encode()):
            return jsonify(error="The invite code is missing or wrong."), 403
        file = request.files.get("file")
        if file is None:
            return jsonify(error="Choose an image to upload."), 400
        raw = file.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return too_large(None)
        cleaned = clean_image(raw)
        if cleaned is None:
            return jsonify(error="Only JPEG, PNG or WebP images are accepted."), 400
        data, content_type = cleaned
        image_id = secrets.token_urlsafe(6)  # 8 URL-safe characters
        now = datetime.now(timezone.utc)
        meta = {
            "content_type": content_type,
            "size": len(data),
            "created_at": now,
            "expires_at": now + timedelta(days=RETENTION_DAYS),
        }
        store.put(image_id, data, meta)
        return jsonify(url=f"{request.host_url}i/{image_id}", expires_at=meta["expires_at"].isoformat()), 201

    @app.get("/i/<image_id>")
    def view(image_id):
        if not ID_RE.match(image_id):
            abort(404)
        found = store.get(image_id)
        if found is None:
            abort(404)
        data, meta = found
        if meta["expires_at"] <= datetime.now(timezone.utc):
            abort(404)  # also enforced by bucket lifecycle rule + Firestore TTL
        return Response(data, mimetype=meta["content_type"], headers={"Cache-Control": "public, max-age=3600"})

    return app
