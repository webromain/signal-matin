import datetime as dt
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader

from signal_matin.cli import build_parser
from signal_matin.ereader import generer_epub, generer_pdf_liseuse
from signal_matin.mock_data import construire_demo
from signal_matin.normalizer import normaliser_edition


def _edition():
    return normaliser_edition(
        construire_demo(dt.date(2026, 9, 26)), mode="standard")


def test_epub_is_reflowable_and_structurally_valid(tmp_path):
    path = generer_epub(_edition(), tmp_path / "signal-matin.epub")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert names[0] == "mimetype"
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert archive.read("mimetype") == b"application/epub+zip"
        required = {
            "META-INF/container.xml", "OEBPS/content.opf",
            "OEBPS/nav.xhtml", "OEBPS/toc.ncx", "OEBPS/stylesheet.css",
        }
        assert required.issubset(names)
        for name in names:
            if name.endswith((".xml", ".opf", ".xhtml", ".ncx")):
                ElementTree.fromstring(archive.read(name))
        text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in names if name.endswith(".xhtml")
        )
        assert "Actualités &amp; monde" in text
        assert "Technologie &amp; IA" in text
        assert "Jeux &amp; apprentissage" in text
        css = archive.read("OEBPS/stylesheet.css").decode("utf-8")
        assert "px" not in css
        assert "mm" not in css


def _edition_avec_brief():
    donnees = _edition().model_dump(mode="json")
    donnees["tech_brief"] = {
        "title": "Brief Tech & IA – 26 septembre 2026",
        "essentials": ["Un modèle fictif reste en accès restreint [1]."],
        "facts": [{
            "fact": "Un laboratoire fictif limite l'accès à son modèle [1].",
            "quote": "limiting access at first",
            "translation": "limite d'abord l'accès",
            "source_id": 1,
            "why": "Une annonce n'est pas une disponibilité [1].",
        }],
        "analyses": [{"subject": "Accès restreint", "facts": "Fait sourcé [1].",
                      "readings": "Lecture 1.\nLecture 2.", "confidence": "moyen"}],
        "threads": [{"text": "Lien établi [1].", "established": True}],
        "questions": ["Qui décide de l'accès ?"],
        "unknowns": ["Le calendrier."],
        "sources": [{"id": 1, "name": "Média fictif", "url": "https://example.org/article",
                     "published_at": "2026-09-26T07:00:00+02:00"}],
        "verification": "1 citation retrouvée.",
    }
    # Le JSON d'un pipeline externe (ex. Jarvis) doit etre accepte tel quel.
    return normaliser_edition(donnees, mode="standard")


def test_brief_tech_remplace_le_chapitre_tech_dans_l_epub(tmp_path):
    path = generer_epub(_edition_avec_brief(), tmp_path / "brief.epub")
    with zipfile.ZipFile(path) as archive:
        pages = [n for n in archive.namelist() if n.endswith(".xhtml")]
        for name in pages:
            ElementTree.fromstring(archive.read(name))
        text = "\n".join(archive.read(name).decode("utf-8") for name in pages)
    assert "Brief Tech &amp; IA – 26 septembre 2026" in text
    assert "« limiting access at first » (limite d&#x27;abord l&#x27;accès)" in text
    assert '<a href="https://example.org/article">Média fictif</a>' in text
    assert "Confiance : moyen" in text
    assert "[1]" not in text


def test_eink_pdf_uses_reader_ratio_instead_of_a4(tmp_path):
    path = generer_pdf_liseuse(
        _edition(), tmp_path / "signal-matin-eink.pdf", profile="medium")
    reader = PdfReader(str(path))
    assert len(reader.pages) >= 6
    width = float(reader.pages[0].mediabox.width)
    height = float(reader.pages[0].mediabox.height)
    assert abs(width - 306.14) < 1.0
    assert abs(height - 408.19) < 1.0
    assert abs((width / height) - 0.75) < 0.01


def test_cli_exposes_ereader_formats_and_screen_profiles():
    args = build_parser().parse_args([
        "ereader", "--demo", "--format", "both", "--screen", "small",
    ])
    assert args.command == "ereader"
    assert args.format == "both"
    assert args.screen == "small"


def test_cli_exposes_private_reader_server():
    args = build_parser().parse_args([
        "serve", "--live", "--host", "0.0.0.0", "--port", "8844",
        "--refresh-at", "08:00", "--show-url-only", "--input-dir", "daily-data",
    ])
    assert args.command == "serve"
    assert args.host == "0.0.0.0"
    assert args.port == 8844
    assert args.show_url_only is True
    assert args.input_dir == "daily-data"
