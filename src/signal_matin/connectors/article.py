"""Debut du texte d'un article, lu sur sa page publique quand le site le permet."""
from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from ..models import NewsItem

_ARTICLE = re.compile(r"<article\b.*?</article>", re.S | re.I)
_PARAGRAPH = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def extract_excerpt(page: str, limit: int = 1500) -> str:
    """Premiers vrais paragraphes de la page, sans menus ni legendes."""
    scopes = _ARTICLE.findall(page)
    scope = max(scopes, key=len) if scopes else page
    kept: list[str] = []
    for raw in _PARAGRAPH.findall(scope):
        text = " ".join(html.unescape(_TAG.sub("", raw)).split())
        if len(text) < 80 or text in kept:
            continue
        kept.append(text)
        if sum(map(len, kept)) >= limit:
            break
    return " ".join(kept)


_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?\s*([\w-]+)", re.I)


def decode_page(raw: bytes, declared: str | None = None) -> str:
    """Decode la page dans l'encodage qu'elle annonce ; tous les sites ne sont pas en UTF-8."""
    meta = _META_CHARSET.search(raw[:4096])
    candidates = [declared, meta.group(1).decode("ascii", "ignore") if meta else None, "utf-8"]
    for charset in candidates:
        if not charset:
            continue
        try:
            return raw.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue
    # Ni annonce fiable ni UTF-8 valide : l'encodage historique des sites francais.
    return raw.decode("cp1252", errors="replace")


def public_addresses(host: str, port: int | None = None) -> list[str]:
    """Adresses IP d'un hote, toutes publiques ; sinon l'hote est refuse.

    Le lien d'un article vient du flux : il ne doit pas pouvoir faire interroger cette
    machine ou le reseau local (localhost, box, NAS, metadonnees d'un hebergeur).
    """
    addresses = list(dict.fromkeys(
        info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)))
    if not addresses or not all(
            ipaddress.ip_address(address.split("%")[0]).is_global for address in addresses):
        raise ValueError("adresse d'article interne refusee")
    return addresses


def require_public(url: str) -> None:
    """Refuse d'emblee un lien qui n'est pas une page web publique."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("adresse d'article non prise en charge")
    public_addresses(parts.hostname)


def _connect_public(address, timeout=socket.getdefaulttimeout(), source_address=None, **_):
    """Ouvre la connexion vers l'adresse qui vient d'etre verifiee, sans la resoudre a nouveau.

    Sinon le nom pourrait designer un site public au controle, puis une adresse interne
    a la connexion. Le nom d'hote reste utilise pour l'en-tete Host et le certificat.
    """
    host, port = address
    error: OSError | None = None
    for candidate in public_addresses(host, port):
        try:
            return socket.create_connection((candidate, port), timeout, source_address)
        except OSError as failure:
            error = failure
    raise error or OSError("connexion impossible")


class _PublicHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_public


class _PublicHTTP(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PublicHTTPConnection, req)


class _PublicHTTPS(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicHTTPSConnection, req, context=self._context)


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    """Une redirection est verifiee comme l'adresse de depart."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener() -> urllib.request.OpenerDirector:
    # Derriere un proxy, c'est lui qui se connecte au site : on ne peut pas imposer
    # l'adresse, et le controle du lien avant l'envoi reste la seule verification.
    if urllib.request.getproxies():
        return urllib.request.build_opener(_PublicRedirects)
    return urllib.request.build_opener(_PublicRedirects, _PublicHTTP, _PublicHTTPS)


_OPENER = _opener()


def _fetch(url: str) -> str:
    require_public(url)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Signal-Matin/1.0"})
    with _OPENER.open(request, timeout=8) as response:
        return decode_page(response.read(2_000_000), response.headers.get_content_charset())


def _enrich(item: NewsItem) -> NewsItem:
    # Un site qui refuse la lecture automatique garde simplement le resume de son flux.
    try:
        excerpt = extract_excerpt(_fetch(str(item.source.url)))
    except Exception:
        return item
    # Un texte encore abime par l'encodage vaut moins que le resume propre du flux.
    if len(excerpt) <= len(item.summary) + 80 or "\ufffd" in excerpt:
        return item
    return item.model_copy(update={"expanded_summary": excerpt[:3200]})


def enrich_articles(items: list[NewsItem], count: int = 16) -> list[NewsItem]:
    """Complete les premiers articles ; les suivants gardent le resume du flux."""
    head = [item for item in items[:count]]
    if not head:
        return items
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [*pool.map(_enrich, head), *items[count:]]
