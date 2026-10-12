"""Citation du jour lue dans un flux RSS, par exemple celui de Dicocitations."""
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET

from ..models import DataSourceStatus, DataState, QuoteBlock
from .rss import _date, _payload, _plain, _tag, _text

# Au-dela, le bandeau du journal couperait la citation : mieux vaut celle de secours.
MAX_LENGTH = 190
_NAME = "Citation du jour"


def _unavailable(detail: str) -> tuple[None, DataSourceStatus]:
    return None, DataSourceStatus(name=_NAME, state=DataState.UNAVAILABLE, detail=detail)


def collect_quote(url: str, now: dt.datetime) -> tuple[QuoteBlock | None, DataSourceStatus]:
    """Derniere citation du flux, au format « texte — auteur, source »."""
    try:
        root = ET.fromstring(_payload(url))
    except Exception as error:
        return _unavailable(f"Flux illisible: {type(error).__name__}.")
    node = next((node for node in root.iter() if _tag(node) in {"item", "entry"}), None)
    if node is None:
        return _unavailable("Flux vide.")
    published = _date(node)
    if published and published < now - dt.timedelta(hours=48):
        return _unavailable("Flux non mis a jour.")
    # Le titre du flux est abrege : le texte complet est dans la description.
    full = _plain(_text(node, {"description", "summary", "content"}) or _text(node, {"title"}))
    text, separator, author = full.rpartition(" — ")
    if not separator:
        text, author = full, ""
    text = text.strip(" «»\"")
    if not text:
        return _unavailable("Citation absente du flux.")
    if len(text) > MAX_LENGTH:
        return _unavailable("Citation trop longue pour le bandeau.")
    return QuoteBlock(text=text, author=author.strip()[:120]), DataSourceStatus(
        name=_NAME, state=DataState.LIVE, detail="Flux lu", item_count=1,
    )
