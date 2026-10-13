"""Choix des articles de l'edition une feuille.

Trois regles, appliquees sans comprendre le texte :

- deux articles de flux differents qui racontent le meme fait ne sont imprimes
  qu'une fois, dans leur version la plus fournie ;
- un sujet repris par plusieurs medias le meme jour est juge plus important ;
- ce qui a ete imprime la veille passe en dernier, et le gros titre change de sujet
  d'un jour a l'autre quand un autre candidat existe.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .models import MorningEdition, NewsItem, PrintedRecord

# Nombre d'articles de l'edition une feuille : peu, pour laisser respirer la page.
SHEET_NEWS_COUNT = 5      # France & monde, gros titre compris
SHEET_FRONT_NEWS = 3      # dont ceux du recto ; le reste ouvre le verso
SHEET_CULTURE_COUNT = 3   # culture & sciences
SHEET_WATCH_COUNT = 3     # par colonne de veille (IA, puis dev)
SHEET_CULTURE_CATEGORIES = {"science", "sciences", "culture"}
SHEET_AI_CATEGORIES = {"ia", "ai", "data", "data science", "intelligence artificielle"}

# Seuils regles sur des editions reelles : au-dessus de STRONG, deux textes parlent du
# meme fait ; entre les deux, il faut en plus que les titres se recoupent.
SIMILARITY_STRONG = 0.28
SIMILARITY_WEAK = 0.13
RICH_TEXT = 620
HISTORY_DAYS = 7

_STOPWORDS = set(
    "pour dans avec sans plus moins apres avant entre contre leur leurs cette sont etre "
    "fait tout tous comme face deux trois selon quand comment pourquoi direct aussi mais "
    "donc ainsi alors depuis encore tres peut ont ete avait avoir fois lors dont elle elles "
    "nous vous ils les des une aux sur par pas que qui est son ses malgre vers chez sous "
    "that with from this have what will your about into their more the and for are was has "
    "been its not".split()
)


def _tokens(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()
    # Six premieres lettres : « lyceen » et « lyceennes » comptent pour le meme mot.
    return [
        word[:6] for word in re.findall(r"[a-z0-9]{3,}", plain)
        if word not in _STOPWORDS and not word.isdigit()
    ]


def _url(item: NewsItem) -> str:
    return str(item.source.url or "")


def _feed(item: NewsItem) -> str:
    return f"{item.source.name}|{item.category}".casefold()


def _richness(item: NewsItem) -> int:
    return min(RICH_TEXT, len(item.expanded_summary or item.summary))


class Similarity:
    """Compare des articles par leurs mots, les mots rares du jour pesant le plus lourd."""

    def __init__(self, texts: list[tuple[str, str]]) -> None:
        counts = [self._counts(title, body) for title, body in texts]
        frequency = Counter(word for count in counts for word in count)
        self._size = len(counts)
        self._idf = {
            word: math.log((self._size + 1) / (seen + 1)) + 1 for word, seen in frequency.items()
        }
        self.titles = [_tokens(title) for title, _ in texts]
        self.vectors = [self._vector(count) for count in counts]

    @staticmethod
    def _counts(title: str, body: str) -> Counter[str]:
        counts: Counter[str] = Counter()
        for word in _tokens(title):
            counts[word] += 3
        for word in _tokens(body[:400]):
            counts[word] += 1
        return counts

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        unseen = math.log(self._size + 1) + 1
        return {
            word: (1 + math.log(count)) * self._idf.get(word, unseen)
            for word, count in counts.items()
        }

    def describe(self, title: str, body: str) -> tuple[list[str], dict[str, float]]:
        """Titre et vecteur d'un texte exterieur au lot, comme le gros titre de la veille."""
        return _tokens(title), self._vector(self._counts(title, body))

    @staticmethod
    def cosine(first: dict[str, float], second: dict[str, float]) -> float:
        dot = sum(first[word] * second[word] for word in first.keys() & second.keys())
        norms = math.sqrt(sum(v * v for v in first.values())) * math.sqrt(
            sum(v * v for v in second.values()))
        return dot / norms if norms else 0.0

    @staticmethod
    def title_overlap(first: list[str], second: list[str]) -> int:
        """Mots communs aux deux titres ; un nom en deux mots (« Donald Trump ») compte pour un."""
        shared = set(first) & set(second)
        pairs = set(zip(first, first[1:])) & set(zip(second, second[1:]))
        return max(len(shared) - len(pairs), 1 if shared else 0)

    def same_story(
        self, first: tuple[list[str], dict[str, float]], second: tuple[list[str], dict[str, float]],
    ) -> bool:
        score = self.cosine(first[1], second[1])
        return score >= SIMILARITY_STRONG or (
            score >= SIMILARITY_WEAK and self.title_overlap(first[0], second[0]) >= 2)

    def entry(self, index: int) -> tuple[list[str], dict[str, float]]:
        return self.titles[index], self.vectors[index]


@dataclass(frozen=True)
class SheetPlan:
    """Ce que l'edition une feuille imprime, et ou."""

    lead: NewsItem | None = None
    front_news: list[NewsItem] = field(default_factory=list)   # recto, apres le gros titre
    back_news: list[NewsItem] = field(default_factory=list)
    culture: list[NewsItem] = field(default_factory=list)
    watch_front: list[NewsItem] = field(default_factory=list)  # l'article de veille du recto
    ai: list[NewsItem] = field(default_factory=list)           # verso
    dev: list[NewsItem] = field(default_factory=list)          # verso
    market: NewsItem | None = None

    def items(self) -> list[NewsItem]:
        """Tous les articles retenus, le gros titre en premier."""
        ordered = [
            self.lead, *self.front_news, *self.back_news, *self.culture,
            *self.watch_front, *self.ai, *self.dev, self.market,
        ]
        return [item for item in ordered if item is not None]


def _interleave(groups: list[list[NewsItem]]) -> list[NewsItem]:
    """Alterne entre les rubriques pour ne pas en laisser une seule passer devant."""
    queues = [list(group) for group in groups]
    merged: list[NewsItem] = []
    while any(queues):
        for queue in queues:
            if queue:
                merged.append(queue.pop(0))
    return merged


def _sections(edition: MorningEdition) -> list[list[NewsItem]]:
    """Les quatre rubriques, de la plus prioritaire a la moins prioritaire."""
    bundle = edition.news
    news = _interleave([bundle.france, bundle.world, bundle.economy, bundle.society])
    culture = _interleave([bundle.culture, bundle.science])
    if bundle.lead:
        target = culture if bundle.lead.category.casefold() in SHEET_CULTURE_CATEGORIES else news
        target.insert(0, bundle.lead)
    return [news, culture, list(edition.tech_news), list(edition.market_news)]


def _clusters(similarity: Similarity, items: list[NewsItem]) -> list[list[int]]:
    """Regroupe les articles de flux differents qui racontent le meme fait."""
    parent = list(range(len(items)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for first in range(len(items)):
        for second in range(first + 1, len(items)):
            same_article = _url(items[first]) and _url(items[first]) == _url(items[second])
            if same_article or (
                _feed(items[first]) != _feed(items[second])
                and similarity.same_story(similarity.entry(first), similarity.entry(second))
            ):
                parent[root(second)] = root(first)
    groups: dict[int, list[int]] = {}
    for index in range(len(items)):
        groups.setdefault(root(index), []).append(index)
    return list(groups.values())


def plan_sheet(edition: MorningEdition) -> SheetPlan:
    """Choisit et range les articles : un seul par sujet, les plus importants en une."""
    sections = _sections(edition)
    items = [item for section in sections for item in section]
    if not items:
        return SheetPlan()
    section_of = [index for index, section in enumerate(sections) for _ in section]
    position = [index for section in sections for index in range(len(section))]
    similarity = Similarity([(item.title, item.summary) for item in items])
    previous = edition.previous
    printed = set(previous.urls) if previous else set()
    old_lead = (
        similarity.describe(previous.lead_title, previous.lead_text)
        if previous and previous.lead_title else None
    )
    headline = edition.news.lead

    ranked: list[list[tuple[tuple, NewsItem, bool]]] = [[] for _ in sections]
    for cluster in _clusters(similarity, items):
        # Un sujet present dans plusieurs rubriques est imprime dans la plus prioritaire.
        home = min(section_of[index] for index in cluster)
        members = [index for index in cluster if section_of[index] == home]
        fresh = [index for index in members if _url(items[index]) not in printed]
        best = max(fresh or members, key=lambda index: (_richness(items[index]), -index))
        first = min(position[index] for index in members)
        media = {items[index].source.name for index in cluster}
        score = 3 * (len(media) - 1) + (1 - first / max(1, len(sections[home])))
        if headline is not None and any(items[index] is headline for index in cluster):
            score += 1.5
        repeats_lead = bool(old_lead) and any(
            similarity.same_story(similarity.entry(index), old_lead) for index in cluster)
        # Deja imprime la veille : en dernier, quelle que soit son importance.
        ranked[home].append(((not fresh, -score, first), items[best], repeats_lead))
    for section in ranked:
        section.sort(key=lambda entry: entry[0])

    news = ranked[0]
    # Le gros titre ne reprend pas le sujet de la veille si un autre candidat existe.
    for index, (_, _, repeats_lead) in enumerate(news):
        if not repeats_lead:
            news.insert(0, news.pop(index))
            break
    news_items = [item for _, item, _ in news][:SHEET_NEWS_COUNT]
    lead = news_items[0] if news_items else None
    front_count = max(0, SHEET_FRONT_NEWS - (1 if lead else 0))

    tech = [item for _, item, _ in ranked[2]]
    ai = [item for item in tech if item.category.casefold() in SHEET_AI_CATEGORIES]
    dev = [item for item in tech if item.category.casefold() not in SHEET_AI_CATEGORIES]
    ai, dev = ai[:SHEET_WATCH_COUNT], dev[:SHEET_WATCH_COUNT]
    watch_front = [item for item in tech if item in ai or item in dev][:1]
    market = [item for _, item, _ in ranked[3]]
    return SheetPlan(
        lead=lead,
        front_news=news_items[1:1 + front_count],
        back_news=news_items[1 + front_count:],
        culture=[item for _, item, _ in ranked[1]][:SHEET_CULTURE_COUNT],
        watch_front=watch_front,
        ai=[item for item in ai if item not in watch_front],
        dev=[item for item in dev if item not in watch_front],
        market=market[0] if market else None,
    )


def printed_record(plan: SheetPlan) -> PrintedRecord:
    """Memoire de l'edition, relue le lendemain."""
    lead = plan.lead
    return PrintedRecord(
        lead_title=lead.title if lead else "",
        lead_text=(lead.summary if lead else "")[:1600],
        urls=[url for url in dict.fromkeys(_url(item) for item in plan.items()) if url][:60],
    )


def load_previous(data_dir: Path, date: dt.date) -> PrintedRecord | None:
    """Ce que la derniere edition precedente a imprime, si elle date de moins d'une semaine."""
    candidates: list[tuple[dt.date, Path]] = []
    for path in data_dir.glob("*-signal-matin.json"):
        try:
            day = dt.date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if dt.timedelta(0) < date - day <= dt.timedelta(days=HISTORY_DAYS):
            candidates.append((day, path))
    for _, path in sorted(candidates, reverse=True):
        try:
            edition = MorningEdition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        # Une edition anterieure a cette memoire : on recalcule ce qu'elle a imprime.
        return edition.printed or printed_record(plan_sheet(edition))
    return None


def remember(edition: MorningEdition, data_dir: Path) -> MorningEdition:
    """Rattache a l'edition la memoire de la veille, puis note ce qu'elle imprime elle-meme."""
    edition = edition.model_copy(update={"previous": load_previous(data_dir, edition.edition.date)})
    return edition.model_copy(update={"printed": printed_record(plan_sheet(edition))})
