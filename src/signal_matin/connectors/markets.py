"""Cours de marche via l'API publique de graphiques Yahoo Finance, sans cle API."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..models import DataSourceStatus, DataState, MarketGroup, MarketQuote

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"


def _meta(symbol: str) -> dict[str, Any]:
    url = _URL.format(symbol=urllib.parse.quote(symbol, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Signal-Matin/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)["chart"]["result"][0]["meta"]


def _quote(entry: Any) -> MarketQuote | None:
    if isinstance(entry, str):
        entry = {"symbol": entry}
    if not isinstance(entry, dict) or not entry.get("symbol"):
        return None
    symbol = str(entry["symbol"])
    try:
        meta = _meta(symbol)
        value = float(meta["regularMarketPrice"])
        previous = meta.get("chartPreviousClose") or meta.get("previousClose")
        previous = float(previous) if previous else None
    except Exception:
        return None
    decimals = entry.get("decimals")
    return MarketQuote(
        name=str(entry.get("name") or meta.get("shortName") or symbol)[:60],
        value=value,
        change=value - previous if previous else None,
        change_pct=(value - previous) / previous * 100 if previous else None,
        unit=str(entry.get("unit") or "")[:8],
        decimals=int(decimals) if decimals is not None else None,
    )


def collect_markets(config: dict) -> tuple[list[MarketGroup], DataSourceStatus]:
    wanted = [
        (str(group.get("name") or "Marches"), list(group.get("symbols") or []))
        for group in (config.get("groups") or []) if isinstance(group, dict)
    ]
    entries = [entry for _, symbols in wanted for entry in symbols]
    if not entries:
        return [], DataSourceStatus(
            name="Marches", state=DataState.DISABLED,
            detail="Aucun symbole configure.",
        )
    with ThreadPoolExecutor(max_workers=8) as pool:
        quotes = iter(list(pool.map(_quote, entries)))
    groups: list[MarketGroup] = []
    for name, symbols in wanted:
        found = [quote for quote in (next(quotes) for _ in symbols) if quote]
        if found:
            groups.append(MarketGroup(name=name[:60], quotes=found[:12]))
    count = sum(len(group.quotes) for group in groups)
    return groups[:10], DataSourceStatus(
        name="Marches",
        state=DataState.LIVE if count else DataState.UNAVAILABLE,
        detail=f"{count}/{len(entries)} cours lus",
        item_count=count,
    )
