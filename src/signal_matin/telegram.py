"""Envoi facultatif du PDF du jour dans une conversation Telegram."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

_URL = "https://api.telegram.org/bot{token}/sendDocument"


def _multipart(fields: dict[str, str], path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
        f'filename="{path.name}"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
        + path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def send_pdf(config: dict[str, Any], path: Path, caption: str = "") -> None:
    """Envoie le PDF au chat configure; leve RuntimeError si Telegram refuse."""
    token = str(config.get("bot_token") or "").strip()
    chat_id = str(config.get("chat_id") or "").strip()
    if not token or not chat_id:
        raise RuntimeError(
            "Telegram: TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID doivent etre renseignes dans .env.")
    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
    body, content_type = _multipart(fields, path)
    request = urllib.request.Request(
        _URL.format(token=token), data=body, headers={"Content-Type": content_type})
    # Le jeton figure dans l'URL : les messages d'erreur ne la reprennent jamais.
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("description", "")
        except ValueError:
            detail = ""
        raise RuntimeError(f"Telegram: envoi refuse ({error.code}) {detail}".rstrip()) from None
    except (urllib.error.URLError, TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise RuntimeError(f"Telegram: service injoignable ({reason})") from None
    if not answer.get("ok"):
        raise RuntimeError(f"Telegram: envoi refuse {answer.get('description', '')}".rstrip())
