"""Google Calendar facultatif avec OAuth local."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from ..models import AgendaItem, DataSourceStatus, DataState

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _paths(config: dict, root: Path) -> tuple[Path, Path]:
    credentials = Path(str(config.get("credentials_file") or "credentials.json")).expanduser()
    token = Path(str(config.get("token_file") or "token.json")).expanduser()
    return (
        credentials if credentials.is_absolute() else root / credentials,
        token if token.is_absolute() else root / token,
    )


def authorize_google(config: dict, root: Path) -> Path:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise RuntimeError("Installe Signal Matin avec l'extra google.") from error
    credentials, token = _paths(config, root)
    if not credentials.exists():
        raise FileNotFoundError(f"Fichier OAuth introuvable: {credentials}")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials), SCOPES)
    creds = flow.run_local_server(port=0)
    token.parent.mkdir(parents=True, exist_ok=True)
    token.write_text(creds.to_json(), encoding="utf-8")
    return token


def collect_google_calendar(
    config: dict, now: dt.datetime, root: Path,
) -> tuple[list[AgendaItem], DataSourceStatus]:
    credentials_path, token_path = _paths(config, root)
    if not token_path.exists():
        return [], DataSourceStatus(
            name="Google Calendar", state=DataState.UNAVAILABLE,
            detail="OAuth non configure ; lance auth-google.",
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            raise RuntimeError("Jeton OAuth invalide")
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + dt.timedelta(days=1)
        result = service.events().list(
            calendarId=str(config.get("calendar_id") or "primary"),
            timeMin=start.isoformat(), timeMax=end.isoformat(), singleEvents=True,
            orderBy="startTime", maxResults=50,
        ).execute()
        events: list[AgendaItem] = []
        for event in result.get("items", []):
            raw = event.get("start", {})
            all_day = "date" in raw
            value = raw.get("dateTime") or raw.get("date")
            if not value:
                continue
            if all_day:
                event_start = dt.datetime.combine(
                    dt.date.fromisoformat(value), dt.time.min, tzinfo=now.tzinfo)
            else:
                event_start = dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
            events.append(AgendaItem(
                title=str(event.get("summary") or "Sans titre")[:180],
                start=event_start, all_day=all_day,
                location=str(event.get("location") or "")[:160],
            ))
        return events, DataSourceStatus(
            name="Google Calendar", state=DataState.LIVE,
            detail="Lecture seule", item_count=len(events),
        )
    except Exception as error:
        detail = "Reconnexion necessaire" if credentials_path.exists() else "Configuration OAuth absente"
        return [], DataSourceStatus(
            name="Google Calendar", state=DataState.UNAVAILABLE,
            detail=f"{detail}: {type(error).__name__}.",
        )
