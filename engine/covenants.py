"""
Auswertung der DSCR-Kovenanten: Cash Trap (Ausschuettungssperre) und
Event of Default (Nachschusspflicht).

Der Schuldendienstdeckungsgrad wird in Kreditvertraegen ueblicherweise
mit zwei Schwellen belegt:

- **Cash Trap** (Lock-up, ueblich 1,10x): Unterschreitet der DSCR diese
  Schwelle, darf keine Ausschuettung mehr erfolgen; der freie Cashflow
  bleibt als Reserve in der Gesellschaft.
- **Event of Default** (ueblich 1,00x): Unterschreitet der DSCR diese
  Schwelle, liegt eine Vertragsverletzung vor. Sie wird ueblicherweise
  durch eine Eigenkapitaleinlage geheilt (Equity Cure) - in Hoehe des
  Betrags, der den DSCR gerade wieder auf die Schwelle hebt.

Dieses Modul veraendert die Cashflow-Rechnung NICHT. Es liest die
fertige Zeitreihe und beantwortet zwei Fragen:

1. In welchen Jahren werden die Schwellen unterschritten?
2. Kann ein notwendiger Nachschuss aus Mitteln gedeckt werden, die das
   Projekt zuvor selbst erwirtschaftet hat (einbehaltene Reserve oder
   bereits ausgeschuettetes Kapital), oder benoetigt die Gesellschaft
   zusaetzliches externes Kapital?

Die Auswertung ist bewusst SEQUENZIELL: Reserve und kumulierte
Ausschuettung sind Bestandsgroessen, die vom Vorjahr abhaengen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

KOVENANT_SPALTEN = [
    "jahr",
    "dscr",
    "cfads_eur",
    "schuldendienst_eur",
    "cash_trap_aktiv",
    "event_of_default_aktiv",
    "nachschuss_eur",
    "nachschuss_aus_reserve_eur",
    "nachschuss_aus_ausschuettung_eur",
    "nachschuss_extern_eur",
    "ausschuettung_eur",
    "reserve_eop_eur",
    "kumulierte_ausschuettung_eur",
]


@dataclass
class KovenantAnalyse:
    """Ergebnis der Kovenantenpruefung ueber die gesamte Laufzeit."""

    zeitreihe: pd.DataFrame
    schwelle_cash_trap: float
    schwelle_event_of_default: float
    dscr_min: float | None
    jahre_cash_trap: list[int] = field(default_factory=list)
    jahre_event_of_default: list[int] = field(default_factory=list)
    #: Summe aller notwendigen Eigenkapitalnachschuesse.
    nachschuss_gesamt_eur: float = 0.0
    #: Davon aus einbehaltener Reserve (Cash Trap) gedeckt.
    nachschuss_aus_reserve_eur: float = 0.0
    #: Davon aus bereits ausgeschuettetem, selbst erwirtschaftetem Kapital.
    nachschuss_aus_ausschuettung_eur: float = 0.0
    #: Davon durch zusaetzliches externes Kapital zu decken.
    nachschuss_extern_eur: float = 0.0

    @property
    def hat_cash_trap(self) -> bool:
        return bool(self.jahre_cash_trap)

    @property
    def hat_event_of_default(self) -> bool:
        return bool(self.jahre_event_of_default)

    @property
    def braucht_externes_kapital(self) -> bool:
        """True, wenn der Nachschuss die zuvor selbst erwirtschafteten
        Mittel uebersteigt - die Gesellschaft braucht dann waehrend der
        Laufzeit zusaetzliches Kapital von aussen."""
        return self.nachschuss_extern_eur > 0.01

    @property
    def nachschuss_intern_eur(self) -> float:
        """Aus eigener Kraft gedeckter Anteil des Nachschusses."""
        return self.nachschuss_aus_reserve_eur + self.nachschuss_aus_ausschuettung_eur


def analysiere_kovenanten(
    cashflow_df: pd.DataFrame,
    schwelle_cash_trap: float,
    schwelle_event_of_default: float,
) -> KovenantAnalyse:
    """Prueft beide DSCR-Schwellen Jahr fuer Jahr und verfolgt dabei die
    Deckungsquellen eines etwaigen Nachschusses.

    Reihenfolge der Deckung (Wasserfall):
    1. **Reserve** - wegen des Cash Traps einbehaltener Cashflow, der
       noch in der Gesellschaft liegt.
    2. **Bereits ausgeschuettetes Kapital** - Mittel, die das Projekt
       selbst erwirtschaftet und an die Gesellschafter ausgekehrt hat;
       sie koennen zurueckgefuehrt werden.
    3. **Externes Kapital** - alles, was darueber hinausgeht.

    Jahre ohne Schuldendienst (nach Kreditende) haben keinen definierten
    DSCR und bleiben von der Pruefung unberuehrt.
    """
    betrieb = cashflow_df[cashflow_df["jahr"] > 0]

    reserve = 0.0                     # einbehaltener Cashflow (Cash Trap)
    ausschuettung_verfuegbar = 0.0    # bereits ausgeschuettet, rueckfuehrbar
    kumulierte_ausschuettung = 0.0

    zeilen: list[dict] = []
    jahre_trap: list[int] = []
    jahre_eod: list[int] = []
    summe_reserve = summe_ausschuettung = summe_extern = 0.0

    for _, periode in betrieb.iterrows():
        jahr = int(periode["jahr"])
        schuldendienst = float(periode["zinsen_eur"]) + float(periode["tilgung_eur"])
        cfads = (
            float(periode["erloes_eur"])
            - float(periode["opex_gesamt_eur"])
            - float(periode["steuer_eur"])
        )
        frei = float(periode["cf_gesamt_eur"])     # Equity-Cashflow des Jahres

        if schuldendienst > 0:
            dscr = cfads / schuldendienst
            trap = dscr < schwelle_cash_trap
            eod = dscr < schwelle_event_of_default
            # Equity Cure: Betrag, der den DSCR gerade auf die Schwelle hebt.
            heilung = max(schwelle_event_of_default * schuldendienst - cfads, 0.0)
        else:
            dscr = float("nan")
            trap = eod = False
            heilung = 0.0

        # Die Liquiditaetsluecke ist immer zu decken - auch dann, wenn die
        # Schwelle so niedrig gesetzt ist, dass sie formal nicht greift.
        bedarf = max(heilung if eod else 0.0, max(-frei, 0.0))

        aus_reserve = min(bedarf, reserve)
        reserve -= aus_reserve
        rest = bedarf - aus_reserve
        aus_ausschuettung = min(rest, ausschuettung_verfuegbar)
        ausschuettung_verfuegbar -= aus_ausschuettung
        extern = rest - aus_ausschuettung

        ausschuettung = 0.0
        if frei > 0:
            if trap:
                reserve += frei          # Ausschuettungssperre: Geld bleibt drin
            else:
                ausschuettung = frei
                kumulierte_ausschuettung += frei
                ausschuettung_verfuegbar += frei

        if trap:
            jahre_trap.append(jahr)
        if eod:
            jahre_eod.append(jahr)
        summe_reserve += aus_reserve
        summe_ausschuettung += aus_ausschuettung
        summe_extern += extern

        zeilen.append(
            {
                "jahr": jahr,
                "dscr": dscr,
                "cfads_eur": cfads,
                "schuldendienst_eur": schuldendienst,
                "cash_trap_aktiv": trap,
                "event_of_default_aktiv": eod,
                "nachschuss_eur": bedarf,
                "nachschuss_aus_reserve_eur": aus_reserve,
                "nachschuss_aus_ausschuettung_eur": aus_ausschuettung,
                "nachschuss_extern_eur": extern,
                "ausschuettung_eur": ausschuettung,
                "reserve_eop_eur": reserve,
                "kumulierte_ausschuettung_eur": kumulierte_ausschuettung,
            }
        )

    zeitreihe = pd.DataFrame(zeilen, columns=KOVENANT_SPALTEN)
    gueltige_dscr = zeitreihe["dscr"].dropna()

    return KovenantAnalyse(
        zeitreihe=zeitreihe,
        schwelle_cash_trap=schwelle_cash_trap,
        schwelle_event_of_default=schwelle_event_of_default,
        dscr_min=float(gueltige_dscr.min()) if len(gueltige_dscr) else None,
        jahre_cash_trap=jahre_trap,
        jahre_event_of_default=jahre_eod,
        nachschuss_gesamt_eur=float(np.round(summe_reserve + summe_ausschuettung + summe_extern, 2)),
        nachschuss_aus_reserve_eur=float(np.round(summe_reserve, 2)),
        nachschuss_aus_ausschuettung_eur=float(np.round(summe_ausschuettung, 2)),
        nachschuss_extern_eur=float(np.round(summe_extern, 2)),
    )
