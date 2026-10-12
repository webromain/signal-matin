"""Debut du texte d'un article, lu sur sa page publique quand le site le permet."""
from __future__ import annotations

import html
import re
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


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Signal-Matin/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
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
