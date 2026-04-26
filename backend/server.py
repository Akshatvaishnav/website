from __future__ import annotations

import json
import os
import smtplib
import ssl
import threading
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def get_supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")

    if not url:
        raise RuntimeError(
            "Supabase is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env."
        )

    return url


def get_supabase_key() -> str:
    key = (
        os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_SECRET_KEY", "").strip()
    )

    if not key:
        raise RuntimeError(
            "Supabase is not configured. Add SUPABASE_SERVICE_KEY in backend/.env."
        )

    return key


def get_supabase_table() -> str:
    table = os.getenv("SUPABASE_TABLE", "inquiries").strip()
    return table or "inquiries"


def build_supabase_headers(include_body: bool = False, prefer: str | None = None) -> dict[str, str]:
    key = get_supabase_key()
    headers = {"apikey": key}

    # New `sb_secret_...` keys should not be forced into Authorization.
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"

    if include_body:
        headers["Content-Type"] = "application/json"

    if prefer:
        headers["Prefer"] = prefer

    return headers


def parse_supabase_response(response_text: str) -> Any:
    if not response_text:
        return None

    return json.loads(response_text)


def supabase_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    prefer: str | None = None,
) -> Any:
    url = f"{get_supabase_url()}/rest/v1/{path.lstrip('/')}"

    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers=build_supabase_headers(include_body=payload is not None, prefer=prefer),
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return parse_supabase_response(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raw_body = error.read().decode("utf-8", errors="replace")

        try:
            parsed = parse_supabase_response(raw_body)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            message = (
                str(parsed.get("message", "")).strip()
                or str(parsed.get("error_description", "")).strip()
                or str(parsed.get("hint", "")).strip()
                or raw_body.strip()
            )
        else:
            message = raw_body.strip() or str(error.reason)

        raise RuntimeError(f"Supabase request failed: {message}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Supabase is not reachable: {error.reason}") from error


def save_inquiry(payload: dict[str, str], remote_address: str | None) -> str:
    inserted_rows = supabase_request(
        "POST",
        get_supabase_table(),
        payload={
            "submitted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "name": payload["name"],
            "email": payload["email"],
            "phone": payload["phone"],
            "student_class": payload["grade"],
            "message": payload["message"],
            "remote_address": remote_address,
            "email_sent": False,
            "email_error": None,
        },
        prefer="return=representation",
    )

    if not isinstance(inserted_rows, list) or not inserted_rows:
        raise RuntimeError("Supabase insert did not return the saved enquiry.")

    inserted_row = inserted_rows[0]
    inquiry_id = inserted_row.get("id")

    if inquiry_id is None:
        raise RuntimeError("Supabase insert did not return an enquiry id.")

    return str(inquiry_id)


def update_email_status(inquiry_id: str, sent: bool, error_message: str | None = None) -> None:
    supabase_request(
        "PATCH",
        get_supabase_table(),
        payload={
            "email_sent": sent,
            "email_error": error_message,
        },
        query={"id": f"eq.{inquiry_id}"},
    )


def send_notification_email(payload: dict[str, str], inquiry_id: str) -> tuple[bool, str | None]:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    recipient = os.getenv("SCHOOL_NOTIFICATION_EMAIL", "st.judesfnr@gmail.com").strip()
    sender = os.getenv("SMTP_FROM_EMAIL", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not recipient:
        return False, "Thank you. Your enquiry was saved, but email notification is not configured yet."

    message = EmailMessage()
    message["Subject"] = f"New Admission Enquiry #{inquiry_id} - {payload['name']}"
    message["From"] = sender
    message["To"] = recipient
    message["Reply-To"] = payload["email"]
    message.set_content(
        "\n".join(
            [
                "A new enquiry has been submitted on the school website.",
                "",
                f"Inquiry ID: {inquiry_id}",
                f"Parent Name: {payload['name']}",
                f"Parent Email: {payload['email']}",
                f"Mobile Number: {payload['phone']}",
                f"Student Class: {payload['grade']}",
                "",
                "Message:",
                payload["message"] or "No additional message provided.",
            ]
        )
    )

    use_ssl = os.getenv("SMTP_USE_SSL", "true" if smtp_port == 465 else "false").lower() in {
        "1",
        "true",
        "yes",
    }
    use_starttls = os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                context=ssl.create_default_context(),
                timeout=20,
            ) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                if use_starttls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(smtp_user, smtp_password)
                server.send_message(message)
    except Exception as error:  # noqa: BLE001
        return False, f"Thank you. Your enquiry was saved, but email notification failed: {error}"

    return True, None


class SchoolWebsiteHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def send_api_headers(self, status: HTTPStatus, content_length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_api_headers(status, len(body))
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self.path == "/api/inquiries":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/inquiries":
            self.end_json(HTTPStatus.NOT_FOUND, {"message": "Endpoint not found."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.end_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid request size."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except json.JSONDecodeError:
            self.end_json(HTTPStatus.BAD_REQUEST, {"message": "Invalid JSON payload."})
            return

        cleaned_payload = {
            "name": str(payload.get("name", "")).strip(),
            "email": str(payload.get("email", "")).strip(),
            "phone": str(payload.get("phone", "")).strip(),
            "grade": str(payload.get("grade", "")).strip(),
            "message": str(payload.get("message", "")).strip(),
        }

        required_fields = {
            "name": "Parent name is required.",
            "email": "Parent email is required.",
            "phone": "Mobile number is required.",
            "grade": "Student class is required.",
        }

        for field_name, error_message in required_fields.items():
            if not cleaned_payload[field_name]:
                self.end_json(HTTPStatus.BAD_REQUEST, {"message": error_message})
                return

        if "@" not in cleaned_payload["email"] or "." not in cleaned_payload["email"]:
            self.end_json(HTTPStatus.BAD_REQUEST, {"message": "Enter a valid email address."})
            return

        try:
            inquiry_id = save_inquiry(
                cleaned_payload,
                self.client_address[0] if self.client_address else None,
            )
        except RuntimeError as error:
            self.end_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": str(error)})
        #     return

        # email_sent, email_error = send_notification_email(cleaned_payload, inquiry_id)

        # status_update_error = None

        # try:
        #     update_email_status(inquiry_id, email_sent, email_error)
        # except RuntimeError as error:
        #     status_update_error = str(error)

        # if email_sent:
        #     message = "Thank you. Your enquiry was saved and emailed to the school successfully."

        #     if status_update_error:
        #         message = f"{message} However, the email status could not be synced back to Supabase."

        #     self.end_json(
        #         HTTPStatus.CREATED,
        #         {
        #             "message": message,
        #             "inquiryId": inquiry_id,
        #         },
        #     )



        # ✅ Send response immediately
        self.end_json(
        HTTPStatus.CREATED,
        {
            "message": "Thank you. Your enquiry was submitted successfully.",
            "inquiryId": inquiry_id,
        },
)

        # ✅ Run email in background (non-blocking)
        import threading

        def background_task():
            email_sent, email_error = send_notification_email(cleaned_payload, inquiry_id)
        try:
            update_email_status(inquiry_id, email_sent, email_error)
        except Exception:
            pass

        threading.Thread(target=background_task, daemon=True).start() 
        return

        message = email_error or "Thank you. Your enquiry was saved successfully."

        if status_update_error:
            message = f"{message} However, the email status could not be synced back to Supabase."

        self.end_json(
            HTTPStatus.CREATED,
            {
                "message": message,
                "inquiryId": inquiry_id,
            },
        )


def main() -> None:
    load_env_file(BACKEND_DIR / ".env")
    port = int(os.getenv("PORT", "8000"))

    with ThreadingHTTPServer(("0.0.0.0", port), SchoolWebsiteHandler) as server:
        print(f"School website running at http://127.0.0.1:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
