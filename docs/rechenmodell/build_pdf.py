"""Erzeugt aus ``rechenmodell.md`` eine hochwertige PDF-Dokumentation.

Der Build verwendet eine einzige fachliche Markdown-Quelle, setzt die
Formeln aber mit echtem XeLaTeX statt als Rasterbilder. Zusätzlich werden

- ``rechenweg.png`` als reproduzierbares Ablaufdiagramm,
- ``Rechenmodell.tex`` als vollständig gesetzte LaTeX-Quelle und
- ``Rechenmodell.pdf`` als finales Dokument

erzeugt.

Voraussetzungen
---------------
- Python 3.10+
- Graphviz (``dot``)
- Pandoc
- XeLaTeX und latexmk (TeX Live oder MacTeX)

Aufruf
------
``python docs/rechenmodell/build_pdf.py``
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HIER = Path(__file__).resolve().parent
QUELLE = HIER / "rechenmodell.md"
TEX_ZIEL = HIER / "Rechenmodell.tex"
PDF_ZIEL = HIER / "Rechenmodell.pdf"
DIAGRAMM = HIER / "rechenweg.png"
LOGO = HIER.parent.parent / "assets" / "valyze_logo.png"

DOKUMENTTITEL = (
    "Dokumentation Cash-Flow-Model - "
    "Rechenmodell und Berechnungsvorschrift"
)

BRAND = "167B88"
INK = "14304F"
INK_SOFT = "2B4F77"
MUTED = "5C636A"
LINE = "DDE3E8"
WASH = "F4F7F8"


class BuildFehler(RuntimeError):
    """Lesbare Fehlermeldung für fehlende Werkzeuge oder Build-Abbrüche."""


def _werkzeug(name: str) -> str:
    pfad = shutil.which(name)
    if not pfad:
        raise BuildFehler(
            f"Benötigtes Werkzeug '{name}' wurde nicht gefunden. "
            "Installiere Pandoc, Graphviz und eine XeLaTeX-Distribution."
        )
    return pfad


def _run(befehl: list[str], cwd: Path, *, ausgabe: bool = False) -> str:
    prozess = subprocess.run(
        befehl,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if prozess.returncode != 0:
        kommando = " ".join(befehl)
        raise BuildFehler(
            f"Build-Schritt fehlgeschlagen:\n{kommando}\n\n{prozess.stdout}"
        )
    if ausgabe and prozess.stdout:
        print(prozess.stdout.rstrip())
    return prozess.stdout


def _diagramm_dot() -> str:
    """Graphviz-Quelle des Ablaufdiagramms in Markenfarben."""
    return f'''digraph Rechenweg {{
      graph [
        rankdir=TB,
        bgcolor="transparent",
        pad="0.16",
        nodesep="0.28",
        ranksep="0.38",
        splines=ortho
      ];
      node [
        shape=rect,
        style="rounded,filled",
        fontname="Lato",
        fontsize=11,
        color="#{LINE}",
        fontcolor="#{INK}",
        fillcolor="white",
        penwidth=1.2,
        margin="0.13,0.09"
      ];
      edge [
        color="#{INK_SOFT}",
        penwidth=1.25,
        arrowsize=0.72,
        fontname="Lato",
        fontsize=8.5,
        fontcolor="#{MUTED}"
      ];

      projekt [label=<
        <B>Projektmaske</B><BR/><FONT POINT-SIZE="9">PVProject</FONT>
      >, width=2.25];
      global [label=<
        <B>Globale Annahmen</B><BR/><FONT POINT-SIZE="9">GlobalAssumptions</FONT>
      >, width=2.25];
      {{ rank=same; projekt; global; }}

      resolve [label=<
        <FONT COLOR="white"><B>0 · Parameter auflösen</B></FONT><BR/>
        <FONT COLOR="white" POINT-SIZE="9">EffectiveAssumptions · Kapitel 4</FONT>
      >, fillcolor="#{BRAND}", color="#{BRAND}", width=3.25];

      timeline [label=<
        <B>1 · Zeitachse</B><BR/><FONT POINT-SIZE="9">Perioden und Anteilsfaktoren · Kapitel 5</FONT>
      >, width=3.45];
      energy [label=<
        <B>2 · Energieertrag</B><BR/><FONT POINT-SIZE="9">E<SUB>t</SUB> · Kapitel 6</FONT>
      >, width=3.45];
      revenue [label=<
        <B>3 · Erlöse</B><BR/><FONT POINT-SIZE="9">R<SUB>t</SUB>, m<SUB>t</SUB>, p<SUB>t</SUB> · Kapitel 7</FONT>
      >, width=3.45];
      opex [label=<
        <B>4 · Betriebskosten</B><BR/><FONT POINT-SIZE="9">C<SUB>t</SUB> · inkl. markt- und umsatzabhängiger Kosten · Kapitel 8</FONT>
      >, width=3.45];
      financing [label=<
        <B>5 · Finanzierung</B><BR/><FONT POINT-SIZE="9">Z<SUB>t</SUB>, T<SUB>t</SUB>, B<SUB>t</SUB> · separater Seitenzweig · Kapitel 9</FONT>
      >, fillcolor="#{WASH}", width=2.85];
      tax [label=<
        <B>6 · Ertragsteuern</B><BR/><FONT POINT-SIZE="9">A<SUB>t</SUB>, V<SUB>t</SUB>, S<SUB>t</SUB> · Kapitel 10</FONT>
      >, width=3.45];
      cashflow [label=<
        <FONT COLOR="white"><B>7 · Equity-Cashflow</B></FONT><BR/>
        <FONT COLOR="white" POINT-SIZE="9">CF<SUB>t</SUB>, kum. CF<SUB>t</SUB>, DSCR<SUB>t</SUB> · Kapitel 11</FONT>
      >, fillcolor="#{INK}", color="#{INK}", width=3.6];
      kpis [label=<
        <B>8 · Bewertungskennzahlen</B><BR/><FONT POINT-SIZE="9">XNPV, XIRR, Payback, DSCR<SUB>min</SUB> · Kapitel 12</FONT>
      >, fillcolor="#{WASH}", color="#{BRAND}", penwidth=1.8, width=3.6];

      projekt -> resolve;
      global -> resolve;
      resolve -> timeline;
      timeline -> energy;
      energy -> revenue;
      revenue -> opex;
      opex -> tax;
      tax -> cashflow;
      cashflow -> kpis;

      resolve -> financing [constraint=false];
      financing -> tax;
      financing -> cashflow [constraint=false];

      {{ rank=same; opex; financing; }}
    }}'''


def erzeuge_diagramm(ziel: Path = DIAGRAMM) -> Path:
    dot = _werkzeug("dot")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rechenweg-") as tmp:
        quelle = Path(tmp) / "rechenweg.dot"
        quelle.write_text(_diagramm_dot(), encoding="utf-8")
        _run(
            [dot, "-Tpng", "-Gdpi=230", str(quelle), "-o", str(ziel)],
            cwd=ziel.parent,
        )
    return ziel


def _logo_block() -> str:
    """Markenzeile des Deckblatts.

    Liegt das Logo unter ``assets/valyze_logo.png``, wird es gesetzt;
    andernfalls tritt der Schriftzug an seine Stelle, damit der Build
    auch ohne Bilddatei durchläuft. Der Pfad ist relativ zum
    Dokumentverzeichnis, damit die erzeugte ``Rechenmodell.tex``
    ausserhalb dieses Rechners uebersetzbar bleibt.
    """
    relativ = LOGO.relative_to(HIER.parent.parent)
    pfad = "/".join([".."] * 2 + list(relativ.parts))
    return (
        rf"\IfFileExists{{{pfad}}}"
        rf"{{\includegraphics[height=16mm]{{{pfad}}}}}"
        r"{\sffamily\bfseries\fontsize{16}{20}\selectfont\color{Brand}VALYZE}"
        r"\par"
    )


def _preamble(tagline: str) -> str:
    stand = date.today().strftime("%d.%m.%Y")
    logo_block = _logo_block()
    # Der Inhalt wird von Pandoc direkt in die erzeugte TeX-Datei kopiert.
    return rf'''
% --- Dokumentdesign -------------------------------------------------------
\usepackage{{microtype}}
\usepackage{{xcolor}}
\definecolor{{Brand}}{{HTML}}{{{BRAND}}}
\definecolor{{Ink}}{{HTML}}{{{INK}}}
\definecolor{{InkSoft}}{{HTML}}{{{INK_SOFT}}}
\definecolor{{Muted}}{{HTML}}{{{MUTED}}}
\definecolor{{Rule}}{{HTML}}{{{LINE}}}
\definecolor{{Wash}}{{HTML}}{{{WASH}}}
\color{{Ink}}

\usepackage[a4paper,left=19mm,right=19mm,top=24mm,bottom=21mm,
            headheight=18pt,headsep=8mm,footskip=12mm]{{geometry}}
\usepackage{{setspace}}
\setstretch{{1.08}}
\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{5.5pt plus 1pt minus 1pt}}
\emergencystretch=2.5em

\usepackage{{titlesec}}
\titleformat{{\section}}
  {{\sffamily\bfseries\fontsize{{20}}{{24}}\selectfont\color{{Ink}}}}
  {{}}{{0pt}}{{}}
\titleformat{{\subsection}}
  {{\sffamily\bfseries\fontsize{{13.2}}{{16}}\selectfont\color{{Brand}}}}
  {{}}{{0pt}}{{}}
\titleformat{{\subsubsection}}
  {{\sffamily\bfseries\fontsize{{10.7}}{{13.5}}\selectfont\color{{InkSoft}}}}
  {{}}{{0pt}}{{}}
\titlespacing*{{\section}}{{0pt}}{{0pt}}{{13pt}}
\titlespacing*{{\subsection}}{{0pt}}{{17pt}}{{6pt}}
\titlespacing*{{\subsubsection}}{{0pt}}{{12pt}}{{4pt}}
\newcommand{{\sectionbreak}}{{\clearpage}}

\usepackage{{fancyhdr}}
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\sffamily\fontsize{{6.6}}{{8}}\selectfont\color{{Muted}}Valyze · Dokumentation Cash-Flow-Model - Rechenmodell und Berechnungsvorschrift}}
\fancyhead[R]{{}}
\fancyfoot[L]{{\sffamily\fontsize{{6.6}}{{8}}\selectfont\color{{Muted}}\nouppercase{{\leftmark}}}}
\fancyfoot[R]{{\sffamily\fontsize{{7.6}}{{9}}\selectfont\color{{Muted}}Seite \thepage}}
\renewcommand{{\headrulewidth}}{{0.35pt}}
\renewcommand{{\footrulewidth}}{{0.35pt}}
\renewcommand{{\headrule}}{{\hbox to\headwidth{{\color{{Rule}}\leaders\hrule height \headrulewidth\hfill}}}}
\renewcommand{{\footrule}}{{\hbox to\headwidth{{\color{{Rule}}\leaders\hrule height \footrulewidth\hfill}}}}
\renewcommand{{\sectionmark}}[1]{{\markboth{{#1}}{{}}}}
\fancypagestyle{{plain}}{{%
  \fancyhf{{}}
  \fancyfoot[C]{{\sffamily\fontsize{{7.6}}{{9}}\selectfont\color{{Muted}}Seite \thepage}}
  \renewcommand{{\headrulewidth}}{{0pt}}
  \renewcommand{{\footrulewidth}}{{0.35pt}}
}}

\usepackage{{amsmath,amssymb}}
\setlength{{\abovedisplayskip}}{{10pt plus 2pt minus 2pt}}
\setlength{{\belowdisplayskip}}{{11pt plus 2pt minus 2pt}}
\setlength{{\abovedisplayshortskip}}{{8pt plus 2pt}}
\setlength{{\belowdisplayshortskip}}{{9pt plus 2pt}}
\setlength{{\jot}}{{6pt}}
\allowdisplaybreaks[1]
\newcommand{{\mathbox}}[1]{{%
  \begingroup\setlength{{\fboxsep}}{{8pt}}%
  \colorbox{{Wash}}{{\ensuremath{{\displaystyle #1}}}}\endgroup}}

\usepackage{{booktabs,longtable,array,tabularx,colortbl}}
\arrayrulecolor{{Rule}}
\renewcommand{{\arraystretch}}{{1.16}}
\setlength{{\tabcolsep}}{{5pt}}
\usepackage{{etoolbox}}
\AtBeginEnvironment{{longtable}}{{\small\rowcolors{{2}}{{Wash}}{{white}}}}
\AtBeginEnvironment{{table}}{{\small}}

\usepackage{{enumitem}}
\setlist[itemize]{{leftmargin=17pt,itemsep=2.5pt,topsep=4pt}}
\setlist[enumerate]{{leftmargin=19pt,itemsep=2.5pt,topsep=4pt}}
\setlist[itemize,1]{{label=\textcolor{{Brand}}{{\small\textbullet}}}}

\usepackage[most]{{tcolorbox}}
\renewenvironment{{quote}}
  {{\begin{{tcolorbox}}[
      enhanced,
      breakable,
      colback=Wash,
      colframe=Brand,
      boxrule=0pt,
      leftrule=2.2pt,
      arc=0pt,
      left=8pt,right=8pt,top=6pt,bottom=6pt,
      before skip=8pt,after skip=9pt
    ]\small\color{{InkSoft}}}}
  {{\end{{tcolorbox}}}}

\definecolor{{shadecolor}}{{HTML}}{{F4F7F8}}
\usepackage{{fvextra}}
\fvset{{fontsize=\scriptsize,breaklines=true,breakanywhere=true,
       frame=single,rulecolor=\color{{Rule}},framesep=5pt}}

\usepackage{{caption}}
\captionsetup{{font=small,labelfont={{bf,color=InkSoft}},textfont={{color=Muted}},skip=6pt}}
\usepackage{{graphicx}}
\setkeys{{Gin}}{{width=\linewidth,height=0.72\textheight,keepaspectratio}}

\usepackage{{hyperref}}
\usepackage{{xurl}}
\urlstyle{{tt}}
\Urlmuskip=0mu plus 1mu
\hypersetup{{
  pdftitle={{{DOKUMENTTITEL}}},
  pdfauthor={{Valyze}},
  pdfsubject={{Mathematische Spezifikation der Projektbewertung}},
  colorlinks=true,
  linkcolor=Brand,
  urlcolor=Brand,
  citecolor=Brand,
  bookmarksopen=true,
  bookmarksnumbered=false
}}

% --- Individuelles Deckblatt ---------------------------------------------
\makeatletter
\renewcommand{{\maketitle}}{{%
  \begin{{titlepage}}
    \thispagestyle{{empty}}
    \vspace*{{15mm}}
    {logo_block}
    \vspace{{10mm}}
    {{\sffamily\bfseries\fontsize{{25}}{{30}}\selectfont\color{{Ink}}
      Dokumentation Cash-Flow-Model -\par}}
    \vspace{{5mm}}
    {{\sffamily\bfseries\fontsize{{17}}{{21}}\selectfont\color{{Brand}}
      Rechenmodell und Berechnungsvorschrift\par}}
    \vspace{{11mm}}
    {{\color{{Brand}}\rule{{56mm}}{{2.2pt}}\par}}
    \vspace{{11mm}}
    {{\sffamily\fontsize{{12}}{{17}}\selectfont\color{{InkSoft}}
      {tagline}\par}}
    \vfill
    \begin{{tcolorbox}}[
      colback=Wash,colframe=Rule,boxrule=0.5pt,arc=1.5pt,
      left=9pt,right=9pt,top=8pt,bottom=8pt,width=\textwidth
    ]
      {{\sffamily\fontsize{{9.2}}{{13}}\selectfont\color{{InkSoft}}
      Wirtschaftlichkeitsrechnung für PV-Projekte nach dem
      österreichischen EAG-Marktprämienmodell\\[4pt]
      Stand: {stand} · erzeugt aus
      \texttt{{docs/rechenmodell/rechenmodell.md}}}}
    \end{{tcolorbox}}
  \end{{titlepage}}
  \setcounter{{page}}{{1}}
}}
\makeatother
'''


def _markdown_fuer_pandoc(quelle: Path) -> tuple[str, str]:
    markdown = quelle.read_text(encoding="utf-8")
    tagline = "Mathematische Spezifikation der Projektbewertung und Gebotsanalyse"
    if markdown.startswith("% "):
        kopf, _, markdown = markdown.partition("\n")
        tagline = kopf[2:].strip()

    metadata = f'''---
title: "{DOKUMENTTITEL}"
author: "Valyze"
date: "{date.today().strftime('%d.%m.%Y')}"
lang: de-DE
---

'''
    return metadata + markdown, tagline


_TEXTTT = re.compile(r"\\texttt\{([^{}]*)\}")


def _mache_codepfade_umbrechbar(tex_pfad: Path) -> None:
    """Ersetzt lange Dateipfade durch xurl-Ausdrücke mit Umbruchstellen.

    Pandoc setzt Inline-Code grundsätzlich als ``\\texttt``. In schmalen
    Tabellenspalten sind Pfade mit Unterstrichen dann untrennbar. ``xurl``
    erlaubt saubere Umbrüche an Slash, Punkt und Unterstrich, ohne den
    sichtbaren Text zu verändern.
    """
    tex = tex_pfad.read_text(encoding="utf-8")

    def ersetzen(treffer: re.Match[str]) -> str:
        inhalt = treffer.group(1)
        roh = inhalt.replace(r"\_", "_").replace(r"\ ", " ")
        if "/" not in roh:
            return treffer.group(0)

        if roh.startswith("python "):
            return r"\texttt{python }\nolinkurl{" + roh[7:] + "}"
        if ": " in roh:
            pfad, zusatz = roh.split(": ", 1)
            zusatz_tex = zusatz.replace("_", r"\_")
            return r"\nolinkurl{" + pfad + r"}: \texttt{" + zusatz_tex + "}"
        return r"\nolinkurl{" + roh + "}"

    tex_pfad.write_text(_TEXTTT.sub(ersetzen, tex), encoding="utf-8")


def baue_pdf(
    quelle: Path = QUELLE,
    tex_ziel: Path = TEX_ZIEL,
    pdf_ziel: Path = PDF_ZIEL,
) -> Path:
    pandoc = _werkzeug("pandoc")
    latexmk = _werkzeug("latexmk")
    _werkzeug("xelatex")
    erzeuge_diagramm(DIAGRAMM)

    markdown, tagline = _markdown_fuer_pandoc(quelle)
    with tempfile.TemporaryDirectory(prefix="rechenmodell-build-") as tmp:
        tmpdir = Path(tmp)
        md_tmp = tmpdir / "rechenmodell_build.md"
        preamble = tmpdir / "rechenmodell_preamble.tex"
        md_tmp.write_text(markdown, encoding="utf-8")
        preamble.write_text(_preamble(tagline), encoding="utf-8")

        tex_ziel.parent.mkdir(parents=True, exist_ok=True)
        _run(
            [
                pandoc,
                str(md_tmp),
                "--standalone",
                "--from=markdown+tex_math_dollars+raw_tex+link_attributes",
                "--to=latex",
                "--toc",
                "--toc-depth=3",
                "--top-level-division=section",
                "--resource-path",
                str(HIER),
                "--include-in-header",
                str(preamble),
                "--variable=documentclass:article",
                "--variable=classoption:10pt",
                "--variable=papersize:a4",
                "--variable=lang:de-DE",
                "--variable=mainfont:Lato",
                "--variable=sansfont:Lato",
                "--variable=monofont:DejaVu Sans Mono",
                "--variable=mathfont:STIXMath-Regular.otf",
                "--output",
                str(tex_ziel),
            ],
            cwd=HIER,
        )
        _mache_codepfade_umbrechbar(tex_ziel)

        # latexmk benötigt alle relativen Bilder aus dem Dokumentverzeichnis.
        _run(
            [
                latexmk,
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-outdir={tmpdir}",
                str(tex_ziel),
            ],
            cwd=HIER,
        )
        gebaut = tmpdir / f"{tex_ziel.stem}.pdf"
        if not gebaut.exists():
            raise BuildFehler("XeLaTeX wurde ausgeführt, aber kein PDF erzeugt.")
        shutil.copy2(gebaut, pdf_ziel)

    return pdf_ziel


def _argumente() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=QUELLE)
    parser.add_argument("--tex", type=Path, default=TEX_ZIEL)
    parser.add_argument("--pdf", type=Path, default=PDF_ZIEL)
    return parser.parse_args()


def main() -> int:
    args = _argumente()
    try:
        pdf = baue_pdf(args.source.resolve(), args.tex.resolve(), args.pdf.resolve())
    except BuildFehler as fehler:
        print(f"FEHLER: {fehler}", file=sys.stderr)
        return 1

    print(f"geschrieben: {TEX_ZIEL.name}")
    print(f"geschrieben: {DIAGRAMM.name}")
    print(f"geschrieben: {pdf.name} ({pdf.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
