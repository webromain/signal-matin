import datetime as dt
import json

from signal_matin.mock_data import construire_demo
from signal_matin.models import MorningEdition, NewsBundle, PrintedRecord, SourceRef
from signal_matin.normalizer import ecrire_edition
from signal_matin.selection import load_previous, plan_sheet, printed_record, remember

DATE = dt.date(2026, 9, 26)


def _article(title, media, summary="Resume du flux.", category="France", url=None):
    base = construire_demo(DATE).tech_news[0]
    slug = "".join(char if char.isalnum() else "-" for char in title.lower())[:60]
    return base.model_copy(update={
        "title": title, "summary": summary, "expanded_summary": summary, "category": category,
        "source": SourceRef(
            name=media, url=url or f"https://exemple.org/{media.lower().replace(' ', '-')}/{slug}"),
    })


def _edition(france=(), world=(), tech=(), market=(), culture=(), lead=None, previous=None):
    demo = construire_demo(DATE)
    return demo.model_copy(update={
        "news": NewsBundle(lead=lead, france=list(france), world=list(world), culture=list(culture)),
        "tech_news": list(tech), "market_news": list(market), "previous": previous,
    })


AUBAGNE_A = _article(
    "Un eleve ouvre le feu dans un college d'Aubagne, le principal et une professeure blesses",
    "Media A", "Un collegien de 14 ans a tire sur le principal de son college a Aubagne.")
AUBAGNE_B = _article(
    "A Aubagne, un collegien blesse le principal et une professeure avec un fusil de chasse",
    "Media B", "Le principal du college d'Aubagne et une professeure ont ete blesses. " * 6)
TRUMP_TAX = _article(
    "Donald Trump annonce une nouvelle taxe sur l'acier europeen", "Media A",
    "La Maison Blanche releve les droits de douane sur l'acier importe.", "Monde")
TRUMP_FILM = _article(
    "Tribune : le cinema americain selon Donald Trump", "Media B",
    "Un critique revient sur les gouts cinematographiques du president.", "Monde")
BUDGET = _article(
    "Budget : le gouvernement presente ses arbitrages", "Media A",
    "Les ministres ont detaille les economies prevues pour l'an prochain.")


def test_same_story_from_two_feeds_is_printed_once_in_its_richest_version():
    plan = plan_sheet(_edition(france=[BUDGET, AUBAGNE_A, AUBAGNE_B]))
    titles = [item.title for item in plan.items()]
    # Deux medias sur le meme fait : le sujet monte en une, une seule fois.
    assert plan.lead == AUBAGNE_B
    assert AUBAGNE_A.title not in titles
    assert BUDGET.title in titles


def test_a_shared_proper_noun_is_not_enough_to_merge_two_articles():
    plan = plan_sheet(_edition(world=[TRUMP_TAX, TRUMP_FILM]))
    assert {TRUMP_TAX.title, TRUMP_FILM.title} <= {item.title for item in plan.items()}


def test_two_articles_of_the_same_feed_are_both_kept():
    second = _article(
        "College d'Aubagne : le recit de la matinee par les eleves", "Media A",
        "Des eleves du college d'Aubagne racontent les tirs et l'evacuation.")
    plan = plan_sheet(_edition(france=[AUBAGNE_A, second]))
    assert {AUBAGNE_A.title, second.title} <= {item.title for item in plan.items()}


def test_story_already_in_the_news_is_dropped_from_the_tech_watch():
    tech = _article(
        "Aubagne : apres les tirs au college, le debat sur les portiques connectes", "Media Tech",
        "Apres les tirs dans un college d'Aubagne ou le principal a ete blesse.", "Dev")
    other = _article("Python 3.15 accelere son interpreteur", "Media Tech", "Nouvelle version.", "Dev")
    plan = plan_sheet(_edition(france=[AUBAGNE_A], tech=[tech, other]))
    titles = [item.title for item in plan.items()]
    assert titles.count(AUBAGNE_A.title) == 1 and tech.title not in titles
    assert other.title in titles


def test_lead_changes_subject_from_one_day_to_the_next():
    yesterday = printed_record(plan_sheet(_edition(france=[AUBAGNE_A, AUBAGNE_B, BUDGET])))
    follow_up = _article(
        "Aubagne : le collegien qui a blesse le principal du college presente a un juge", "Media A",
        "Le collegien d'Aubagne auteur des tirs sur le principal a ete defere.")
    follow_up_b = _article(
        "Tirs au college d'Aubagne : le collegien defere, le principal toujours hospitalise", "Media B",
        "Le principal du college d'Aubagne blesse par un collegien reste hospitalise.")
    today = _edition(france=[follow_up, follow_up_b, BUDGET], previous=yesterday)
    plan = plan_sheet(today)
    # Le sujet de la veille reste le plus couvert, mais il ne refait pas la une.
    assert plan.lead == BUDGET
    assert plan.front_news and "Aubagne" in plan.front_news[0].title
    # Sans autre candidat, il garde la une plutot que de laisser la page vide.
    assert plan_sheet(_edition(france=[follow_up], previous=yesterday)).lead == follow_up


def test_articles_printed_the_day_before_come_last():
    yesterday = PrintedRecord(urls=[str(BUDGET.source.url)])
    fresh = [
        _article(f"Sujet inedit numero {index} sur un theme different", "Media A", f"Texte {index}.")
        for index in range(6)
    ]
    plan = plan_sheet(_edition(france=[BUDGET, *fresh], previous=yesterday))
    assert BUDGET.title not in [item.title for item in plan.items()]
    # Faute de mieux, un article deja imprime vaut mieux qu'un trou.
    assert plan_sheet(_edition(france=[BUDGET], previous=yesterday)).lead == BUDGET


def test_memory_is_read_from_the_previous_edition_file(tmp_path):
    day_one = remember(_edition(france=[AUBAGNE_A, BUDGET]), tmp_path)
    assert day_one.previous is None and day_one.printed.lead_title == AUBAGNE_A.title
    ecrire_edition(day_one, tmp_path / f"{DATE.isoformat()}-signal-matin.json")
    record = load_previous(tmp_path, DATE + dt.timedelta(days=1))
    assert record == day_one.printed
    # L'edition du jour meme n'est pas sa propre veille, et une vieille edition est oubliee.
    assert load_previous(tmp_path, DATE) is None
    assert load_previous(tmp_path, DATE + dt.timedelta(days=30)) is None


def test_memory_is_rebuilt_from_an_edition_saved_before_it_existed(tmp_path):
    old = _edition(france=[AUBAGNE_A, BUDGET])
    payload = json.loads(old.model_dump_json(exclude_none=True))
    payload.pop("printed", None)
    (tmp_path / f"{DATE.isoformat()}-signal-matin.json").write_text(json.dumps(payload))
    (tmp_path / "2026-09-25-signal-matin.json").write_text("{ illisible")
    record = load_previous(tmp_path, DATE + dt.timedelta(days=1))
    assert record.lead_title == AUBAGNE_A.title
    assert MorningEdition.model_validate(payload).printed is None
