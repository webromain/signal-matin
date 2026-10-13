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


def test_article_excerpt_keeps_real_paragraphs_only():
    from signal_matin.connectors.article import extract_excerpt

    page = (
        "<nav><p>" + "Menu du site sans rapport avec l'article, a ignorer totalement ici. " * 2 + "</p></nav>"
        "<article><p>Court.</p>"
        "<p>Premier <a href='#'>vrai</a> paragraphe de l&#39;article, assez long pour etre "
        "retenu par l'extraction du texte.</p>"
        "<p>Second paragraphe de l'article, lui aussi assez long pour etre retenu "
        "par l'extraction du texte.</p></article>"
    )
    excerpt = extract_excerpt(page)
    assert excerpt.startswith("Premier vrai paragraphe de l'article")
    assert "Second paragraphe" in excerpt
    assert "Menu du site" not in excerpt and "Court." not in excerpt


def test_article_page_decoding_follows_declared_charset():
    from signal_matin.connectors.article import decode_page

    latin = '<meta charset="iso-8859-1"><p>réunit des outils d\'entraînement</p>'.encode("iso-8859-1")
    assert "réunit des outils d'entraînement" in decode_page(latin)
    assert "déployé" in decode_page("<p>déployé</p>".encode("utf-8"))
    assert "accélérer" in decode_page("<p>accélérer</p>".encode("cp1252"), "utf-8")


QUOTE_RSS = """<?xml version="1.0" encoding="UTF-8"?><rss><channel>
<item><title>Une citation abregee... — Auteur Fictif</title>
<pubDate>{date}</pubDate>
<description>{text} — Auteur Fictif, Oeuvre de test</description></item>
<item><title>Citation de la veille — Autre</title>
<description>Citation de la veille. — Autre</description></item>
</channel></rss>"""


def _quote_feed(monkeypatch, text, date="Sat, 26 Sep 2026 00:05:00 +0000"):
    payload = QUOTE_RSS.format(text=text, date=date).encode("utf-8")
    monkeypatch.setattr("signal_matin.connectors.quote._payload", lambda _url: payload)


def test_daily_quote_is_read_from_feed(monkeypatch):
    from signal_matin.connectors.quote import collect_quote

    _quote_feed(monkeypatch, "Une citation fictive — avec un tiret — pour le test.")
    now = dt.datetime(2026, 9, 26, 8, tzinfo=dt.timezone.utc)
    quote, status = collect_quote("https://example.org/rss", now)
    assert quote.text == "Une citation fictive — avec un tiret — pour le test."
    assert quote.author == "Auteur Fictif, Oeuvre de test"
    assert status.state == DataState.LIVE


def test_daily_quote_too_long_or_stale_is_refused(monkeypatch):
    from signal_matin.connectors.quote import collect_quote

    now = dt.datetime(2026, 9, 26, 8, tzinfo=dt.timezone.utc)
    _quote_feed(monkeypatch, "mot " * 60)
    assert collect_quote("https://example.org/rss", now)[0] is None
    _quote_feed(monkeypatch, "Citation courte.", date="Mon, 21 Sep 2026 00:05:00 +0000")
    quote, status = collect_quote("https://example.org/rss", now)
    assert quote is None and status.state == DataState.UNAVAILABLE


def test_pipeline_falls_back_to_configured_quotes(monkeypatch):
    from signal_matin import pipeline

    def offline(_url):
        raise OSError("hors ligne")

    monkeypatch.setattr("signal_matin.connectors.quote._payload", offline)
    config = {
        "modules": {name: False for name in (
            "weather", "calendar", "tasks", "news", "tech", "rss", "markets")},
        "personal": {
            "quote_feed": "https://example.org/rss",
            "quotes": [{"text": "Citation de secours.", "author": "Auteur de secours"}],
        },
    }
    edition = pipeline.build_live(config, now=dt.datetime(2026, 9, 26, 8, tzinfo=dt.timezone.utc))
    assert edition.extras.quote.text == "Citation de secours."


def test_article_fetch_refuses_internal_addresses(monkeypatch):
    import pytest

    from signal_matin.connectors import article

    for url in (
        "http://127.0.0.1:5678/", "http://localhost/admin", "http://192.168.1.1/",
        "http://10.0.0.5/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
        "ftp://exemple.org/fichier", "file:///etc/hostname",
    ):
        with pytest.raises(ValueError):
            article.require_public(url)
    article.require_public("https://93.184.216.34/article")

    # Un article dont le lien est interne garde simplement le resume de son flux.
    def forbidden(*args, **kwargs):
        raise AssertionError("aucune requete ne doit partir")

    monkeypatch.setattr(article._OPENER, "open", forbidden)
    assert article.enrich_articles([]) == []
    with pytest.raises(ValueError):
        article._fetch("http://127.0.0.1:5678/")

    # Une redirection vers une adresse interne est refusee elle aussi.
    request = article.urllib.request.Request("https://93.184.216.34/")
    with pytest.raises(ValueError):
        article._PublicRedirects().redirect_request(
            request, None, 302, "Found", {}, "http://127.0.0.1:5678/")


def test_rss_keeps_a_feed_whose_summary_is_longer_than_the_model_allows(monkeypatch):
    from signal_matin.connectors import rss

    now = dt.datetime(2026, 9, 26, 8, tzinfo=dt.timezone.utc)
    feed = (
        "<rss><channel><item><title>Article fleuve</title>"
        "<link>https://exemple.org/fleuve</link>"
        "<pubDate>Sat, 26 Sep 2026 07:00:00 GMT</pubDate>"
        f"<description>{'Phrase tres longue. ' * 200}</description></item></channel></rss>"
    ).encode()
    monkeypatch.setattr(rss, "_payload", lambda url: feed)
    items, status = rss.collect_rss(
        [{"name": "Media", "category": "Dev", "url": "https://exemple.org/rss"}], now)
    assert status.item_count == 1
    assert 1500 < len(items[0].summary) <= 1600 and 3100 < len(items[0].expanded_summary) <= 3200


def test_article_connection_goes_to_the_address_that_was_checked(monkeypatch):
    import socket

    import pytest

    from signal_matin.connectors import article

    answers = iter(["93.184.216.34", "127.0.0.1"])

    def rebinding(host, port=None, **kwargs):
        # Un DNS piege : adresse publique au premier appel, interne au second.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (next(answers), port or 0))]

    opened = []
    monkeypatch.setattr(article.socket, "getaddrinfo", rebinding)
    monkeypatch.setattr(
        article.socket, "create_connection",
        lambda address, *args, **kwargs: opened.append(address) or "socket")

    # La connexion part vers l'adresse verifiee, sans redemander son adresse au nom.
    assert article._connect_public(("piege.exemple", 443), 8) == "socket"
    assert opened == [("93.184.216.34", 443)]
    # Au tour suivant le nom designe la machine locale : aucune connexion n'est ouverte.
    with pytest.raises(ValueError):
        article._connect_public(("piege.exemple", 443), 8)
    assert len(opened) == 1


def test_article_connections_are_pinned_unless_a_proxy_is_configured(monkeypatch):
    from signal_matin.connectors import article

    def handlers(opener):
        return {type(handler).__name__ for handler in opener.handlers}

    monkeypatch.setattr(article.urllib.request, "getproxies", lambda: {})
    assert {"_PublicHTTP", "_PublicHTTPS", "_PublicRedirects"} <= handlers(article._opener())
    assert not {"HTTPHandler", "HTTPSHandler", "HTTPRedirectHandler"} & handlers(article._opener())
    monkeypatch.setattr(
        article.urllib.request, "getproxies", lambda: {"https": "http://proxy.exemple:3128"})
    assert "_PublicHTTPS" not in handlers(article._opener())
    assert "_PublicRedirects" in handlers(article._opener())
