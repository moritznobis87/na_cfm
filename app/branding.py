"""
Verdeckter Marken-Schalter: zwei vollstaendige Gestaltungen (Farben,
Logo, Favicon, Kopfzeilentexte) hinterlegt - die aktuelle
Valyze-Gestaltung (Standard) und die vorherige Trianel-Gestaltung.

Aktivierung ueber den URL-Parameter ?marke=trianel, z.B.
https://<app-url>/?marke=trianel - nirgends in der Oberflaeche
verlinkt oder dokumentiert, daher "verdeckt". Zurueck zu Valyze:
?marke=valyze oder den Parameter aus der URL entfernen und neu laden
(ein einmal gesetzter Wert bleibt sonst fuer die laufende Session
bestehen, siehe aktive_marke_code()).

Nutzung (frueh im Entry-Point, vor set_page_config/apply_theme):

    from app.branding import aktive_marke
    marke = aktive_marke()
    ... marke["app_titel"], marke["logo"], marke["favicon"],
        marke["farben"] (dict mit denselben Schluesseln wie
        app.theme.Colors: BRAND, INK, INK_SOFT, MUTED, NEUTRAL,
        LINE, WASH) ...

Bekannte Einschraenkung: app.theme.Colors (und die gespiegelten
Konstanten in app.report) sind PROZESSWEIT globaler Zustand, nicht
sitzungsspezifisch. Bei mehreren GLEICHZEITIGEN Nutzern auf demselben
Streamlit-Worker-Prozess koennte sich in seltenen, timing-abhaengigen
Faellen die Farbwahl einer Session kurzzeitig mit der einer anderen
ueberschneiden (kein Datenrisiko, rein optisch). Fuer eine verdeckte,
selten genutzte Vergleichsansicht ist das ein akzeptabler Kompromiss;
fuer produktiven Mehrnutzerbetrieb mit haeufigem Markenwechsel muesste
die Farbgebung stattdessen sitzungsspezifisch (z.B. per Parameter statt
globalem Zustand) durchgereicht werden.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

#: Beide Paletten wie in app.theme.Colors bzw. app.report dokumentiert;
#: siehe dort fuer Herleitung/Kontrastwerte. Trianel-Werte sind die vor
#: dem Rebrand (v4.15) verwendeten Originalwerte.
MARKEN: dict[str, dict] = {
    "valyze": {
        "app_titel": "Valyze",
        "kopfzeile_titel": "PV-Projektbewertung",
        "logo": _ASSETS_DIR / "valyze_logo.png",
        "logo_breite": 190,
        "favicon": _ASSETS_DIR / "valyze_favicon.png",
        "farben": {
            "BRAND": "#167B88", "INK": "#14304F", "INK_SOFT": "#2B4F77",
            "MUTED": "#5C636A", "NEUTRAL": "#8A97A6",
            "LINE": "#E1E4E8", "WASH": "#F6F7F9",
        },
    },
    "trianel": {
        "app_titel": "TEA PV-Projektbewertung",
        "kopfzeile_titel": "TEA PV-Projektbewertung",
        "logo": _ASSETS_DIR / "trianel" / "logo.png",
        "logo_breite": 84,
        "favicon": _ASSETS_DIR / "trianel" / "favicon.png",
        "farben": {
            "BRAND": "#BE172B", "INK": "#143530", "INK_SOFT": "#2E5A52",
            "MUTED": "#5B6B66", "NEUTRAL": "#8AA6A0",
            "LINE": "#E1E8E5", "WASH": "#F6F9F8",
        },
    },
}

STANDARD_MARKE = "valyze"
_SESSION_KEY = "aktive_marke"
_QUERY_PARAM = "marke"


def aktive_marke_code() -> str:
    """Ermittelt die aktive Marke: URL-Parameter > laufende Session >
    Standard (Valyze). Ein per URL gesetzter Wert wird in die
    Session uebernommen, damit er auch nach dem Wegfallen des
    Parameters (z.B. Klick auf einen internen Link) fuer den Rest der
    Sitzung bestehen bleibt."""
    try:
        param = st.query_params.get(_QUERY_PARAM)
    except Exception:
        param = None
    if param in MARKEN:
        st.session_state[_SESSION_KEY] = param
    return st.session_state.get(_SESSION_KEY, STANDARD_MARKE)


def aktive_marke() -> dict:
    return MARKEN[aktive_marke_code()]


#: Alles heller als dieser Wert gilt beim Beschnitt als Hintergrund. Eine
#: reine Weiss-Pruefung scheitert an der Kompressionsstreuung des PNG.
_HINTERGRUND_SCHWELLE = 240


@st.cache_data(show_spinner=False)
def _logo_beschnitten(pfad: str, mtime: float) -> bytes | None:
    """Logo ohne weissen Rand, als PNG-Bytes.

    Die gelieferte Marke steht auf einer grossen weissen Flaeche - der
    Schriftzug belegt nur etwa ein Viertel der Bildhoehe. Unbeschnitten
    bestimmt der Weissraum die Hoehe der Kopfzeile, waehrend die Marke
    selbst winzig bleibt und der Claim unleserlich wird. Der Beschnitt
    geschieht bewusst zur Laufzeit: Die Datei in ``assets/`` bleibt das
    unveraenderte Markenoriginal.

    (Der PDF-Build fuehrt denselben Beschnitt eigenstaendig aus, siehe
    ``docs/rechenmodell/build_pdf.py`` - er darf nicht von der
    UI-Schicht abhaengen.)

    None, wenn der Beschnitt nicht moeglich ist; die Aufrufer nutzen
    dann die Originaldatei.
    """
    try:
        import io

        import numpy as np
        from PIL import Image
    except ImportError:                       # pragma: no cover
        return None

    bild = Image.open(pfad).convert("RGB")
    maske = np.asarray(bild).min(axis=2) < _HINTERGRUND_SCHWELLE
    if not maske.any():
        return None
    zeilen, spalten = np.where(maske)
    rand = 4
    kasten = (
        max(int(spalten.min()) - rand, 0),
        max(int(zeilen.min()) - rand, 0),
        min(int(spalten.max()) + 1 + rand, bild.width),
        min(int(zeilen.max()) + 1 + rand, bild.height),
    )
    puffer = io.BytesIO()
    bild.crop(kasten).save(puffer, format="PNG")
    return puffer.getvalue()


def logo_bild(marke: dict) -> bytes | str:
    """Darstellbares Logo der Marke - beschnitten, wenn moeglich, sonst
    der Dateipfad als Rueckfall."""
    pfad = marke["logo"]
    beschnitten = _logo_beschnitten(str(pfad), pfad.stat().st_mtime)
    return beschnitten if beschnitten is not None else str(pfad)
