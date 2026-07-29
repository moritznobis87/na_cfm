"""
Erzeugt aus `rechenmodell.md` das PDF `Rechenmodell.pdf` (beides in
diesem Verzeichnis).

Warum ein eigener Konverter und kein LaTeX/Pandoc?
- Die Dokumentation soll aus EINER Quelle entstehen, die auch direkt im
  Repository (GitHub rendert Markdown inklusive $$-Formeln) lesbar ist.
- Das PDF soll ohne zusaetzliche Systemabhaengigkeiten baubar sein.
  Verwendet werden ausschliesslich Pakete, die das Projekt ohnehin
  mitbringt: `reportlab` (Satz) und `matplotlib` (Formelsatz ueber die
  eingebaute mathtext-Engine, ein TeX-Subset ohne TeX-Installation).

Unterstuetzte Markdown-Teilmenge (bewusst klein und streng - der
Konverter bricht bei allem ab, was er nicht sicher setzen kann):

    # ... #### Ueberschriften (H1 beginnt eine neue Seite)
    Absaetze mit **fett**, *kursiv*, `code` und Inline-Formeln $...$
    $$ ... $$        Abgesetzte Formeln (jede Zeile eine Formel)
    - / * Listen     (eine Verschachtelungsebene ueber zwei Leerzeichen)
    1. Listen        (nummeriert)
    | a | b |        GFM-Tabellen mit Trennzeile
    > Hinweis        Merkkasten
    ```             Codeblock
    <!-- ... -->     Kommentar (wird nicht gesetzt)

Aufruf:  python docs/rechenmodell/build_pdf.py  (oder: make dokumentation)
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import font_manager, mathtext  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    XPreformatted,
)
from reportlab.platypus.tableofcontents import TableOfContents  # noqa: E402

HIER = Path(__file__).resolve().parent
QUELLE = HIER / "rechenmodell.md"
ZIEL = HIER / "Rechenmodell.pdf"
LOGO = HIER.parent.parent / "assets" / "nobis_logo.png"

# Markenfarben - identisch zu app/report.py (dort bewusst ohne
# Streamlit-Import dupliziert, hier ohne App-Import).
BRAND = colors.HexColor("#167B88")
INK = colors.HexColor("#14304F")
INK_SOFT = colors.HexColor("#2B4F77")
MUTED = colors.HexColor("#5C636A")
LINE = colors.HexColor("#E1E4E8")
WASH = colors.HexColor("#F6F7F9")

SEITE_B, SEITE_H = A4
RAND_L = RAND_R = 2.0 * cm
RAND_O, RAND_U = 2.2 * cm, 1.8 * cm
INHALT_B = SEITE_B - RAND_L - RAND_R

BASIS_SCHRIFT = 9.4
MATH_DPI = 300


# ---------------------------------------------------------------------------
# Formelsatz (matplotlib mathtext -> PNG)
# ---------------------------------------------------------------------------

_MATH_PARSER = mathtext.MathTextParser("path")


@dataclass(frozen=True)
class MathBild:
    pfad: Path
    breite_pt: float
    hoehe_pt: float
    tiefgang_pt: float          # Unterlaenge unter der Grundlinie


class Formelsetzer:
    """Rendert `$...$`-Ausdruecke einmalig in PNG-Dateien und liefert die
    exakten Masse in Punkt (inklusive Unterlaenge, damit Inline-Formeln
    auf der Grundlinie des Fliesstexts sitzen)."""

    def __init__(self, arbeitsverzeichnis: Path) -> None:
        self.dir = arbeitsverzeichnis
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[tuple[str, float], MathBild] = {}

    def render(self, ausdruck: str, schriftgroesse: float) -> MathBild:
        schluessel = (ausdruck, schriftgroesse)
        if schluessel in self._cache:
            return self._cache[schluessel]

        formel = f"${ausdruck}$"
        prop = font_manager.FontProperties(size=schriftgroesse)
        try:
            breite_px, hoehe_px, tiefgang_px, *_ = _MATH_PARSER.parse(
                formel, dpi=MATH_DPI, prop=prop
            )
        except Exception as fehler:  # pragma: no cover - Autorenfehler
            raise SystemExit(
                f"Formel nicht setzbar: {formel}\n{fehler}\n"
                "Hinweis: mathtext kennt \\leq/\\geq (nicht \\le/\\ge)."
            ) from fehler

        name = hashlib.sha1(
            f"{ausdruck}|{schriftgroesse}".encode()
        ).hexdigest()[:16]
        pfad = self.dir / f"formel_{name}.png"
        if not pfad.exists():
            mathtext.math_to_image(
                formel, str(pfad), prop=prop, dpi=MATH_DPI, format="png"
            )

        skala = 72.0 / MATH_DPI
        bild = MathBild(
            pfad=pfad,
            breite_pt=breite_px * skala,
            hoehe_pt=hoehe_px * skala,
            tiefgang_pt=tiefgang_px * skala,
        )
        self._cache[schluessel] = bild
        return bild


# ---------------------------------------------------------------------------
# Absatzformate
# ---------------------------------------------------------------------------


def _stile() -> dict[str, ParagraphStyle]:
    fliess = ParagraphStyle(
        "fliess",
        fontName="Helvetica",
        fontSize=BASIS_SCHRIFT,
        leading=BASIS_SCHRIFT * 1.55,
        textColor=INK,
        alignment=TA_JUSTIFY,
        spaceAfter=5,
    )
    return {
        "fliess": fliess,
        "h1": ParagraphStyle(
            "h1", parent=fliess, fontName="Helvetica-Bold", fontSize=17,
            leading=21, textColor=INK, spaceBefore=0, spaceAfter=10,
            alignment=0,
        ),
        "h2": ParagraphStyle(
            "h2", parent=fliess, fontName="Helvetica-Bold", fontSize=12.5,
            leading=16, textColor=BRAND, spaceBefore=14, spaceAfter=5,
            alignment=0,
        ),
        "h3": ParagraphStyle(
            "h3", parent=fliess, fontName="Helvetica-Bold", fontSize=10.4,
            leading=13.5, textColor=INK_SOFT, spaceBefore=10, spaceAfter=3,
            alignment=0,
        ),
        "h4": ParagraphStyle(
            "h4", parent=fliess, fontName="Helvetica-Oblique", fontSize=9.6,
            leading=13, textColor=INK_SOFT, spaceBefore=8, spaceAfter=2,
            alignment=0,
        ),
        "liste": ParagraphStyle(
            "liste", parent=fliess, leftIndent=10, bulletIndent=1,
            spaceAfter=2, alignment=0,
        ),
        "liste2": ParagraphStyle(
            "liste2", parent=fliess, leftIndent=24, bulletIndent=14,
            spaceAfter=1, alignment=0,
        ),
        "tabelle": ParagraphStyle(
            "tabelle", parent=fliess, fontSize=8.0, leading=10.6,
            alignment=0, spaceAfter=0,
        ),
        "tabelle_kopf": ParagraphStyle(
            "tabelle_kopf", parent=fliess, fontName="Helvetica-Bold",
            fontSize=8.0, leading=10.6, alignment=0, spaceAfter=0,
            textColor=colors.white,
        ),
        "hinweis": ParagraphStyle(
            "hinweis", parent=fliess, fontSize=8.8, leading=13,
            textColor=INK_SOFT, spaceAfter=0,
        ),
        "code": ParagraphStyle(
            "code", parent=fliess, fontName="Courier", fontSize=7.6,
            leading=10, textColor=INK, alignment=0, spaceAfter=0,
        ),
        "titel": ParagraphStyle(
            "titel", parent=fliess, fontName="Helvetica-Bold", fontSize=27,
            leading=32, textColor=INK, alignment=TA_CENTER, spaceAfter=6,
        ),
        "untertitel": ParagraphStyle(
            "untertitel", parent=fliess, fontSize=12.5, leading=17,
            textColor=BRAND, alignment=TA_CENTER, spaceAfter=4,
        ),
        "deckzeile": ParagraphStyle(
            "deckzeile", parent=fliess, fontSize=9.2, leading=14,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=0,
        ),
    }


# ---------------------------------------------------------------------------
# Inline-Auszeichnung
# ---------------------------------------------------------------------------

#: Listenpunkt (fuer die Fortsetzung einer bereits laufenden Liste) und
#: Listenbeginn (der einen Absatz unterbrechen darf). Wie in CommonMark
#: darf eine nummerierte Liste einen Absatz nur mit "1." beginnen - sonst
#: wuerde eine Umbruchzeile wie "31. Dezember ..." zum Listenpunkt.
_LISTE_PUNKT = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_LISTE_BEGINN = re.compile(r"^(\s*)([-*]|1\.)\s+")


def _ist_neuer_punkt(treffer: re.Match, letzte_nummer: int | None) -> bool:
    """Ein Treffer ist ein neuer Listenpunkt, wenn er ein Aufzaehlungs-
    zeichen traegt, mit 1. beginnt oder die laufende Nummerierung
    fortsetzt. Alles andere ist Fliesstext einer Umbruchzeile."""
    marke = treffer.group(2)
    if not marke[0].isdigit():
        return True
    nummer = int(marke[:-1])
    return nummer == 1 or (letzte_nummer is not None and nummer == letzte_nummer + 1)


_INLINE_MATH = re.compile(r"(?<!\\)\$(.+?)(?<!\\)\$")
_CODE = re.compile(r"`([^`]+)`")
_FETT = re.compile(r"\*\*(.+?)\*\*")
_KURSIV = re.compile(r"(?<![*\w])\*([^*]+?)\*(?![*\w])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


#: Kleiner LaTeX-zu-Unicode-Ersatz fuer Klartextfassungen (Inhalts-
#: verzeichnis, PDF-Lesezeichen) - dort steht kein Formelsatz zur
#: Verfuegung, roher Quelltext waere aber unlesbar.
_MATH_KLARTEXT = {
    r"\geq": "≥", r"\leq": "≤", r"\cdot": "·", r"\times": "×",
    r"\approx": "≈", r"\rightarrow": "→", r"\Leftrightarrow": "⇔",
    r"\in": "∈", r"\sum": "Σ", r"\mu": "μ", r"\kappa": "κ",
    r"\sigma": "σ", r"\varepsilon": "ε", r"\,": " ", r"\;": " ",
    r"\ ": " ",
}


def _klartext(text: str) -> str:
    """Fassung ohne Auszeichnung - fuer Inhaltsverzeichnis und Lesezeichen."""
    text = _INLINE_MATH.sub(lambda m: m.group(1), text)
    text = _CODE.sub(r"\1", text).replace("**", "")
    text = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    for befehl, zeichen in _MATH_KLARTEXT.items():
        text = text.replace(befehl, zeichen)
    return re.sub(r"\s+", " ", text).strip()


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def inline(text: str, setzer: Formelsetzer, schriftgroesse: float) -> str:
    """Wandelt eine Markdown-Zeile in reportlab-Markup. Inline-Formeln
    werden als Bild eingebettet und ueber `valign` auf die Grundlinie des
    umgebenden Textes gesetzt."""
    platzhalter: dict[str, str] = {}

    def merke(markup: str) -> str:
        schluessel = f"\x00{len(platzhalter)}\x00"
        platzhalter[schluessel] = markup
        return schluessel

    def math_ersetzen(treffer: re.Match) -> str:
        bild = setzer.render(treffer.group(1).strip(), schriftgroesse)
        return merke(
            f'<img src="{bild.pfad}" width="{bild.breite_pt:.2f}" '
            f'height="{bild.hoehe_pt:.2f}" valign="{-bild.tiefgang_pt:.2f}"/>'
        )

    def code_ersetzen(treffer: re.Match) -> str:
        return merke(
            f'<font face="Courier" size="{schriftgroesse - 0.9:.1f}">'
            f"{_escape(treffer.group(1))}</font>"
        )

    text = _INLINE_MATH.sub(math_ersetzen, text)
    text = _CODE.sub(code_ersetzen, text)
    text = _LINK.sub(lambda m: merke(f'<link href="{m.group(2)}" '
                                     f'color="#167B88">{_escape(m.group(1))}'
                                     f"</link>"), text)
    text = _escape(text)
    text = _FETT.sub(r"<b>\1</b>", text)
    text = _KURSIV.sub(r"<i>\1</i>", text)
    text = text.replace("\\$", "$")
    for schluessel, markup in platzhalter.items():
        text = text.replace(schluessel, markup)
    return text


# ---------------------------------------------------------------------------
# Markdown -> Flowables
# ---------------------------------------------------------------------------


def _spaltenbreiten(zeilen: list[list[str]], spalten: int,
                    schriftgroesse: float) -> list[float]:
    """Spaltenbreiten: proportional zur Textmenge, aber nie schmaler als
    das laengste unteilbare Wort der Spalte - sonst zerlegt reportlab
    Kopfzeilen wie 'Equity-CF' mitten im Wort. Reicht die Seitenbreite
    nicht, wird zuerst der Spielraum der grosszuegigen Spalten
    abgeschmolzen und erst danach global skaliert."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    polster = 9.0
    laengen, mindest = [], []
    for i in range(spalten):
        texte = [_klartext(zeile[i]) for zeile in zeilen if i < len(zeile)]
        laengen.append(max((len(t) for t in texte), default=1) or 1)
        woerter = [w for t in texte for w in t.split()] or [""]
        mindest.append(
            max(stringWidth(w, "Helvetica-Bold", schriftgroesse) for w in woerter)
            + polster
        )

    summe_laengen = sum(laengen)
    breiten = [
        max(INHALT_B * laenge / summe_laengen, m)
        for laenge, m in zip(laengen, mindest, strict=True)
    ]

    ueberschuss = sum(breiten) - INHALT_B
    if ueberschuss > 0:
        spielraum = [b - m for b, m in zip(breiten, mindest, strict=True)]
        if sum(spielraum) > 0:
            anteil = min(1.0, ueberschuss / sum(spielraum))
            breiten = [
                b - s * anteil for b, s in zip(breiten, spielraum, strict=True)
            ]
        if sum(breiten) > INHALT_B:      # Notfall: harte Skalierung
            faktor = INHALT_B / sum(breiten)
            breiten = [b * faktor for b in breiten]
    return breiten


class Ueberschrift(Paragraph):
    """Paragraph, der sich beim Satz fuer Inhaltsverzeichnis und
    PDF-Lesezeichen meldet (siehe DokumentVorlage.afterFlowable)."""

    def __init__(self, text: str, stil: ParagraphStyle, ebene: int,
                 klartext: str, marke: str) -> None:
        super().__init__(text, stil)
        self.toc_ebene = ebene
        self.toc_text = klartext
        self.toc_marke = marke


@dataclass
class Konverter:
    setzer: Formelsetzer
    stile: dict[str, ParagraphStyle]

    def __post_init__(self) -> None:
        self._marken = 0

    # -- Bausteine ---------------------------------------------------------

    def _ueberschrift(self, ebene: int, text: str) -> list:
        self._marken += 1
        marke = f"h{self._marken}"
        stil = self.stile[f"h{min(ebene, 4)}"]
        klartext = _klartext(text)
        absatz = Ueberschrift(
            inline(text, self.setzer, stil.fontSize),
            stil, ebene, klartext, marke,
        )
        if ebene == 1:
            return [PageBreak(), absatz]
        return [CondPageBreak(3.2 * cm), absatz]

    def _formelblock(self, zeilen: list[str]) -> list:
        """Abgesetzte Formeln: jede Quellzeile wird eigenstaendig gesetzt
        und zentriert; mehrere Zeilen bleiben als Block zusammen."""
        flowables = [Spacer(1, 3)]
        for zeile in zeilen:
            ausdruck = zeile.strip()
            if not ausdruck:
                continue
            bild = self.setzer.render(ausdruck, BASIS_SCHRIFT + 3.0)
            breite, hoehe = bild.breite_pt, bild.hoehe_pt
            if breite > INHALT_B - 10:            # zu breite Formel skalieren
                faktor = (INHALT_B - 10) / breite
                breite, hoehe = breite * faktor, hoehe * faktor
            grafik = Image(str(bild.pfad), width=breite, height=hoehe)
            grafik.hAlign = "CENTER"
            flowables += [grafik, Spacer(1, 3)]
        flowables.append(Spacer(1, 3))
        return [KeepTogether(flowables)]

    def _tabelle(self, zeilen: list[str]) -> list:
        raster = [
            [z.strip() for z in zeile.strip().strip("|").split("|")]
            for zeile in zeilen
        ]
        kopf, koerper = raster[0], raster[2:]     # raster[1] = Trennzeile
        spalten = len(kopf)
        koerper = [z + [""] * (spalten - len(z)) for z in koerper]

        stil_kopf = self.stile["tabelle_kopf"]
        stil_zelle = self.stile["tabelle"]
        daten = [[Paragraph(inline(z, self.setzer, stil_kopf.fontSize),
                            stil_kopf) for z in kopf]]
        daten += [
            [Paragraph(inline(z, self.setzer, stil_zelle.fontSize), stil_zelle)
             for z in zeile]
            for zeile in koerper
        ]

        breiten = _spaltenbreiten(raster[:1] + koerper, spalten,
                                  stil_zelle.fontSize)

        tabelle = Table(daten, colWidths=breiten, repeatRows=1, hAlign="LEFT")
        tabelle.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), INK),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, WASH]),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ]
            )
        )
        # Kurze Tabellen nicht ueber einen Seitenwechsel zerreissen; lange
        # muessen umbrechen duerfen (repeatRows wiederholt den Kopf).
        if len(daten) <= 14:
            return [Spacer(1, 3), KeepTogether(tabelle), Spacer(1, 7)]
        return [Spacer(1, 3), tabelle, Spacer(1, 7)]

    def _hinweis(self, zeilen: list[str]) -> list:
        stil = self.stile["hinweis"]
        text = " ".join(z.strip() for z in zeilen)
        absatz = Paragraph(inline(text, self.setzer, stil.fontSize), stil)
        tabelle = Table([[absatz]], colWidths=[INHALT_B])
        tabelle.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), WASH),
                    ("LINEBEFORE", (0, 0), (0, -1), 2.2, BRAND),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return [Spacer(1, 3), tabelle, Spacer(1, 7)]

    def _code(self, zeilen: list[str]) -> list:
        stil = self.stile["code"]
        text = "\n".join(_escape(z) for z in zeilen)
        block = XPreformatted(text, stil)
        tabelle = Table([[block]], colWidths=[INHALT_B])
        tabelle.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), WASH),
                    ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return [Spacer(1, 3), tabelle, Spacer(1, 7)]

    # -- Hauptschleife -----------------------------------------------------

    def konvertiere(self, markdown: str) -> list:
        zeilen = markdown.replace("\t", "    ").split("\n")
        flowables: list = []
        i = 0
        while i < len(zeilen):
            zeile = zeilen[i]
            blank = zeile.strip()

            if not blank:
                i += 1
                continue

            if blank.startswith("<!--"):
                while i < len(zeilen) and "-->" not in zeilen[i]:
                    i += 1
                i += 1
                continue

            if blank.startswith("#"):
                ebene = len(blank) - len(blank.lstrip("#"))
                flowables += self._ueberschrift(ebene, blank[ebene:].strip())
                i += 1
                continue

            if blank.startswith("$$"):
                rest = blank[2:].strip()
                if rest.endswith("$$"):              # $$ ... $$ in einer Zeile
                    flowables += self._formelblock([rest[:-2].strip()])
                    i += 1
                    continue
                block: list[str] = [rest] if rest else []
                i += 1
                while i < len(zeilen) and not zeilen[i].strip().startswith("$$"):
                    block.append(zeilen[i])
                    i += 1
                i += 1
                flowables += self._formelblock(block)
                continue

            if blank.startswith("```"):
                i += 1
                block = []
                while i < len(zeilen) and not zeilen[i].strip().startswith("```"):
                    block.append(zeilen[i])
                    i += 1
                i += 1
                flowables += self._code(block)
                continue

            if blank.startswith("|"):
                block = []
                while i < len(zeilen) and zeilen[i].strip().startswith("|"):
                    block.append(zeilen[i])
                    i += 1
                flowables += self._tabelle(block)
                continue

            if blank.startswith(">"):
                block = []
                while i < len(zeilen) and zeilen[i].strip().startswith(">"):
                    block.append(zeilen[i].strip()[1:])
                    i += 1
                flowables += self._hinweis(block)
                continue

            if _LISTE_BEGINN.match(zeile):
                listen_flowables, i = self._liste(zeilen, i)
                flowables += listen_flowables
                continue

            # Absatz: bis zur naechsten Leerzeile oder Blockmarkierung.
            block = []
            while i < len(zeilen):
                akt = zeilen[i].strip()
                if not akt or akt.startswith(("#", "|", ">", "```", "$$")):
                    break
                if _LISTE_BEGINN.match(zeilen[i]):
                    break
                block.append(akt)
                i += 1
            stil = self.stile["fliess"]
            flowables.append(
                Paragraph(inline(" ".join(block), self.setzer, stil.fontSize),
                          stil)
            )
        return flowables

    def _liste(self, zeilen: list[str], start: int) -> tuple[list, int]:
        flowables: list = []
        i = start
        letzte_nummer: int | None = None
        while i < len(zeilen):
            treffer = _LISTE_PUNKT.match(zeilen[i])
            if treffer is None or not _ist_neuer_punkt(treffer, letzte_nummer):
                break
            einzug, marke, text = treffer.groups()
            letzte_nummer = (
                int(marke[:-1]) if marke[0].isdigit() else None
            )
            i += 1
            # Fortsetzungszeilen anhaengen: eingerueckt und kein neuer Punkt.
            while i < len(zeilen) and zeilen[i].strip() and zeilen[i].startswith(" "):
                folge = _LISTE_PUNKT.match(zeilen[i])
                if folge is not None and _ist_neuer_punkt(folge, letzte_nummer):
                    break
                text += " " + zeilen[i].strip()
                i += 1
            stil = self.stile["liste2"] if len(einzug) >= 2 else self.stile["liste"]
            aufzaehlung = marke if marke[0].isdigit() else "•"
            flowables.append(
                Paragraph(
                    inline(text, self.setzer, stil.fontSize), stil,
                    bulletText=aufzaehlung,
                )
            )
        return flowables, i


# ---------------------------------------------------------------------------
# Dokumentvorlage: Kopf-/Fusszeile, Inhaltsverzeichnis, Lesezeichen
# ---------------------------------------------------------------------------


class DokumentVorlage(BaseDocTemplate):
    def __init__(self, ziel: Path, titel: str, **kwargs) -> None:
        super().__init__(
            str(ziel), pagesize=A4, title=titel, author="Nobis Analytics",
            subject="Rechenweg und mathematische Modellvorschrift",
            leftMargin=RAND_L, rightMargin=RAND_R,
            topMargin=RAND_O, bottomMargin=RAND_U, **kwargs,
        )
        self.kapitel = ""
        rahmen_titel = Frame(
            RAND_L, RAND_U, INHALT_B, SEITE_H - RAND_O - RAND_U, id="titel"
        )
        rahmen_inhalt = Frame(
            RAND_L, RAND_U, INHALT_B, SEITE_H - RAND_O - RAND_U, id="inhalt"
        )
        self.addPageTemplates(
            [
                PageTemplate(id="Titel", frames=[rahmen_titel]),
                # onPageEnd statt onPage: Die Kolumnentitel sollen das
                # Kapitel DIESER Seite nennen. Da jedes Kapitel auf einer
                # neuen Seite beginnt, ist es am Seitenende bekannt - bei
                # onPage stuende dort noch das vorherige Kapitel.
                PageTemplate(
                    id="Inhalt", frames=[rahmen_inhalt],
                    onPageEnd=self._kopf_und_fuss,
                ),
            ]
        )

    def _kopf_und_fuss(self, canvas, dokument) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.4)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            RAND_L, SEITE_H - RAND_O + 12,
            "TEA-CFM · Rechenmodell und Berechnungsvorschrift",
        )
        if self.kapitel:
            canvas.drawRightString(
                SEITE_B - RAND_R, SEITE_H - RAND_O + 12, self.kapitel[:70]
            )
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(
            RAND_L, SEITE_H - RAND_O + 7, SEITE_B - RAND_R, SEITE_H - RAND_O + 7
        )
        canvas.line(RAND_L, RAND_U - 10, SEITE_B - RAND_R, RAND_U - 10)
        canvas.drawCentredString(
            SEITE_B / 2, RAND_U - 20, f"Seite {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    def beforeDocument(self) -> None:
        # multiBuild laeuft die Story zweimal durch - die Kopfzeile darf
        # nicht mit dem Kapitel des vorherigen Durchlaufs starten.
        self.kapitel = ""

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Ueberschrift):
            return
        self.notify(
            "TOCEntry",
            (flowable.toc_ebene - 1, flowable.toc_text, self.page,
             flowable.toc_marke),
        )
        self.canv.bookmarkPage(flowable.toc_marke)
        self.canv.addOutlineEntry(
            flowable.toc_text[:110], flowable.toc_marke,
            level=min(flowable.toc_ebene - 1, 3), closed=(flowable.toc_ebene > 2),
        )
        if flowable.toc_ebene == 1:
            self.kapitel = flowable.toc_text


def _deckblatt(stile: dict[str, ParagraphStyle], untertitel: str) -> list:
    flowables: list = [Spacer(1, 2.6 * cm)]
    if LOGO.exists():
        logo = Image(str(LOGO), width=4.6 * cm, height=4.6 * cm * 0.28)
        logo._restrictSize(4.6 * cm, 2.2 * cm)
        logo.hAlign = "CENTER"
        flowables += [logo, Spacer(1, 1.6 * cm)]
    flowables += [
        Paragraph("Rechenmodell", stile["titel"]),
        Paragraph(
            "Vollständige Dokumentation des Rechenweges",
            stile["untertitel"],
        ),
        Spacer(1, 0.5 * cm),
        Paragraph(untertitel, stile["deckzeile"]),
        Spacer(1, 1.4 * cm),
    ]
    strich = Table([[""]], colWidths=[6 * cm], rowHeights=[2])
    strich.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    strich.hAlign = "CENTER"
    flowables += [strich, Spacer(1, 1.4 * cm)]
    flowables += [
        Paragraph(
            "TEA-CFM – Wirtschaftlichkeitsrechnung für "
            "PV-Projekte<br/>nach dem österreichischen "
            "EAG-Marktprämienmodell", stile["deckzeile"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph(
            f"Stand: {date.today().strftime('%d.%m.%Y')} · "
            "erzeugt aus <font face='Courier' size='8'>"
            "docs/rechenmodell/rechenmodell.md</font>",
            stile["deckzeile"],
        ),
    ]
    return flowables


def _inhaltsverzeichnis(stile: dict[str, ParagraphStyle]) -> list:
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "toc0", fontName="Helvetica-Bold", fontSize=9.8, leading=16,
            textColor=INK, spaceBefore=6,
        ),
        ParagraphStyle(
            "toc1", fontName="Helvetica", fontSize=9.0, leading=13,
            textColor=INK_SOFT, leftIndent=14, firstLineIndent=-2,
        ),
        ParagraphStyle(
            "toc2", fontName="Helvetica", fontSize=8.4, leading=12,
            textColor=MUTED, leftIndent=30, firstLineIndent=-2,
        ),
        ParagraphStyle(
            "toc3", fontName="Helvetica", fontSize=8.0, leading=11,
            textColor=MUTED, leftIndent=44, firstLineIndent=-2,
        ),
    ]
    return [
        Paragraph("Inhalt", stile["h1"]),
        Spacer(1, 6),
        toc,
    ]


def baue_pdf(quelle: Path = QUELLE, ziel: Path = ZIEL) -> Path:
    markdown = quelle.read_text(encoding="utf-8")

    # Ein optionaler YAML-artiger Kopf (erste Zeile "% Untertitel") setzt
    # die Zeile auf dem Deckblatt.
    untertitel = "Von der Projektmaske zum Cashflow, zu den Kennzahlen "\
                 "und zum Auktionsmodell"
    if markdown.startswith("% "):
        kopf, _, markdown = markdown.partition("\n")
        untertitel = kopf[2:].strip()

    stile = _stile()
    with tempfile.TemporaryDirectory(prefix="rechenmodell-formeln-") as tmp:
        setzer = Formelsetzer(Path(tmp))
        konverter = Konverter(setzer=setzer, stile=stile)
        inhalt = konverter.konvertiere(markdown)

        story = _deckblatt(stile, untertitel)
        story += [NextPageTemplate("Inhalt"), PageBreak()]
        story += _inhaltsverzeichnis(stile)
        story += inhalt

        dokument = DokumentVorlage(ziel, titel="TEA-CFM – Rechenmodell")
        # multiBuild: zwei Durchlaeufe, damit die Seitenzahlen im
        # Inhaltsverzeichnis stimmen.
        dokument.multiBuild(story)
    return ziel


if __name__ == "__main__":
    pfad = baue_pdf()
    groesse_kb = pfad.stat().st_size / 1024
    print(f"geschrieben: {pfad} ({groesse_kb:,.0f} kB)".replace(",", "."))
    sys.exit(0)
