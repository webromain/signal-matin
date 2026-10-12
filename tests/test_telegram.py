import io
import json
import urllib.error

import pytest

from signal_matin.telegram import send_pdf


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_pdf_is_posted_to_the_chat(tmp_path, monkeypatch):
    pdf = tmp_path / "2026-10-12-signal-matin.pdf"
    pdf.write_bytes(b"%PDF-test")
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["body"] = request.data
        return _Response(json.dumps({"ok": True}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    send_pdf({"bot_token": "123:abc", "chat_id": "42"}, pdf, caption="Edition test")
    assert seen["url"] == "https://api.telegram.org/bot123:abc/sendDocument"
    assert b'name="chat_id"\r\n\r\n42\r\n' in seen["body"]
    assert b"Edition test" in seen["body"]
    assert b'filename="2026-10-12-signal-matin.pdf"' in seen["body"]
    assert b"%PDF-test" in seen["body"]


def test_missing_credentials_are_reported(tmp_path):
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        send_pdf({"bot_token": "", "chat_id": ""}, tmp_path / "absent.pdf")


def test_refusal_never_leaks_the_token(tmp_path, monkeypatch):
    pdf = tmp_path / "edition.pdf"
    pdf.write_bytes(b"%PDF-test")

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"ok": False, "description": "Unauthorized"}).encode()))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as caught:
        send_pdf({"bot_token": "123:secret", "chat_id": "42"}, pdf)
    assert "401" in str(caught.value)
    assert "123:secret" not in str(caught.value)
