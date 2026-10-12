import datetime as dt

from signal_matin.connectors.rss import collect_rss
from signal_matin.models import DataState


RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Une information de test</title><link>https://example.org/a</link>
<description>Un resume entierement fictif pour le test du connecteur.</description>
<pubDate>Sat, 26 Sep 2026 06:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_rss_is_normalized(monkeypatch):
    monkeypatch.setattr("signal_matin.connectors.rss._payload", lambda _url: RSS)
    now = dt.datetime(2026, 9, 26, 8, tzinfo=dt.timezone.utc)
    items, status = collect_rss([
        {"name": "Source test", "category": "Monde", "url": "https://example.org/rss"}
    ], now)
    assert status.state == DataState.LIVE
    assert items[0].title == "Une information de test"
    assert items[0].source.name == "Source test"


def test_empty_rss_is_optional():
    items, status = collect_rss([], dt.datetime.now().astimezone())
    assert items == []
    assert status.state == DataState.DISABLED


def test_markets_compute_change_without_network(monkeypatch):
    from signal_matin.connectors import markets

    def fake_meta(symbol):
        if symbol == "KO":
            raise OSError("hors ligne")
        return {"regularMarketPrice": 110.0, "chartPreviousClose": 100.0, "shortName": "Demo"}

    monkeypatch.setattr(markets, "_meta", fake_meta)
    groups, status = markets.collect_markets({"groups": [
        {"name": "Indices", "symbols": [{"symbol": "OK", "name": "Indice fictif"}, "KO"]},
        {"name": "Vide", "symbols": ["KO"]},
    ]})
    assert [group.name for group in groups] == ["Indices"]
    quote = groups[0].quotes[0]
    assert quote.name == "Indice fictif"
    assert round(quote.change_pct, 2) == 10.0
    assert status.item_count == 1


def test_weather_forecast_skips_today_and_bad_rows():
    from signal_matin.connectors.weather import _forecast

    days = _forecast({
        "time": ["2026-10-12", "2026-10-13", "2026-10-14"],
        "weather_code": [3, 61, None],
        "temperature_2m_min": [7, 9, 8],
        "temperature_2m_max": [18, 16, 17],
        "precipitation_probability_max": [10, 60, 5],
    })
    assert [day.date.isoformat() for day in days] == ["2026-10-13"]
    assert days[0].condition == "Pluie faible"
    assert days[0].rain_pct == 60
