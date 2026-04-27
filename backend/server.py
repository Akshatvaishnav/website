from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


# ---------------- ENV LOADER ---------------- #
def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ---------------- SUPABASE ---------------- #
def get_supabase_url():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL missing")
    return url


def get_supabase_key():
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_KEY missing")
    return key


def supabase_insert(data: dict[str, Any]) -> Any:
    url = f"{get_supabase_url()}/rest/v1/inquiries"
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        method="POST",
        headers={
            "apikey": get_supabase_key(),
            "Authorization": f"Bearer {get_supabase_key()}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        raise RuntimeError(f"Supabase error: {e}")


# ---------------- HANDLER ---------------- #
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def send_json(self, status: HTTPStatus, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if not self.path.startswith("/api/inquiries"):
            self.send_json(HTTPStatus.NOT_FOUND, {"message": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode())
        except:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid JSON"})
            return

        data = {
            "name": str(payload.get("name", "")).strip(),
            "email": str(payload.get("email", "")).strip(),
            "phone": str(payload.get("phone", "")).strip(),
            "student_class": str(payload.get("grade", "")).strip(),
            "message": str(payload.get("message", "")).strip(),
            "submitted_at": datetime.now().isoformat(),
        }

        # Basic validation (email optional)
        if not data["name"] or not data["phone"] or not data["student_class"]:
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Required fields missing"})
            return

        if data["email"] and ("@" not in data["email"]):
            self.send_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid email"})
            return

        # Save to Supabase
        try:
            result = supabase_insert(data)
        except Exception as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(e)})
            return

        self.send_json(
            HTTPStatus.CREATED,
            {
                "message": "Enquiry submitted successfully",
                "data": result,
            },
        )


# ---------------- MAIN ---------------- #
def main():
    load_env_file(BACKEND_DIR / ".env")
    port = int(os.getenv("PORT", 8000))

    with ThreadingHTTPServer(("0.0.0.0", port), Handler) as server:
        print(f"Server running on port {port}")
        server.serve_forever()


if __name__ == "__main__":
    main()