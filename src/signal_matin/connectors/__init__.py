"""Connecteurs facultatifs de Signal Matin."""

from .article import enrich_articles
from .calendar_ics import collect_ics
from .google_calendar import authorize_google, collect_google_calendar
from .markets import collect_markets
from .quote import collect_quote
from .rss import collect_rss
from .tasks import collect_tasks
from .weather import collect_weather

__all__ = [
    "authorize_google", "collect_google_calendar", "collect_ics", "enrich_articles",
    "collect_markets", "collect_quote", "collect_rss", "collect_tasks", "collect_weather",
]
