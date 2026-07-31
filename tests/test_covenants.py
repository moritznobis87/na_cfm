"""
Tests der DSCR-Kovenantenpruefung (engine/covenants.py).

Gerechnet wird gegen handgerechnete Erwartungswerte auf einer
synthetischen Cashflow-Zeitreihe: So haengen die Erwartungswerte an der
Vorschrift selbst und nicht an einer bestimmten Projektkonstellation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.covenants import analysiere_kovenanten  # noqa: E402


def _cashflow(jahre: list[dict]) -> pd.DataFrame:
    """Baut eine minimale Cashflow-Zeitreihe.

    Je Jahr werden Erloes, OPEX, Steuer, Zins und Tilgung vorgegeben;
    CFADS und Equity-Cashflow ergeben sich daraus wie in der Engine:
    CFADS = Erloes - OPEX - Steuer, CF = CFADS - Zins - Tilgung.
    """
    zeilen = [{"jahr": 0, "erloes_eur": 0.0, "opex_gesamt_eur": 0.0,
               "steuer_eur": 0.0, "zinsen_eur": 0.0, "tilgung_eur": 0.0,
               "cf_gesamt_eur": -1000.0}]
    for nummer, jahr in enumerate(jahre, start=1):
        cfads = jahr["erloes"] - jahr.get("opex", 0.0) - jahr.get("steuer", 0.0)
        zeilen.append(
            {
                "jahr": nummer,
                "erloes_eur": jahr["erloes"],
                "opex_gesamt_eur": jahr.get("opex", 0.0),
                "steuer_eur": jahr.get("steuer", 0.0),
                "zinsen_eur": jahr.get("zins", 0.0),
                "tilgung_eur": jahr.get("tilgung", 0.0),
                "cf_gesamt_eur": cfads - jahr.get("zins", 0.0) - jahr.get("tilgung", 0.0),
            }
        )
    return pd.DataFrame(zeilen)


class TestSchwellen:
    def test_ohne_unterschreitung_keine_ereignisse(self):
        # CFADS 150, Schuldendienst 100 -> DSCR 1,50x
        df = _cashflow([{"erloes": 150.0, "zins": 40.0, "tilgung": 60.0}] * 3)
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.dscr_min == pytest.approx(1.5)
        assert analyse.jahre_cash_trap == []
        assert analyse.jahre_event_of_default == []
        assert analyse.nachschuss_gesamt_eur == 0.0
        assert not analyse.braucht_externes_kapital

    def test_cash_trap_sperrt_ausschuettung(self):
        # DSCR 1,05x liegt unter dem Cash Trap (1,10), aber ueber EoD.
        df = _cashflow([{"erloes": 105.0, "zins": 40.0, "tilgung": 60.0}])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)
        zeile = analyse.zeitreihe.iloc[0]

        assert analyse.jahre_cash_trap == [1]
        assert analyse.jahre_event_of_default == []
        assert zeile["ausschuettung_eur"] == 0.0
        # Der freie Cashflow (105 - 100 = 5) bleibt als Reserve stehen.
        assert zeile["reserve_eop_eur"] == pytest.approx(5.0)
        assert analyse.nachschuss_gesamt_eur == 0.0

    def test_jahre_ohne_schuldendienst_bleiben_ungeprueft(self):
        df = _cashflow([
            {"erloes": 150.0, "zins": 40.0, "tilgung": 60.0},
            {"erloes": 150.0},                      # Kredit getilgt
        ])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.jahre_cash_trap == []
        assert pd.isna(analyse.zeitreihe.iloc[1]["dscr"])
        # Ohne Schuldendienst wird voll ausgeschuettet.
        assert analyse.zeitreihe.iloc[1]["ausschuettung_eur"] == pytest.approx(150.0)


class TestNachschuss:
    def test_hoehe_entspricht_dem_equity_cure(self):
        # CFADS 80, Schuldendienst 100 -> DSCR 0,80x.
        # Cure auf 1,00x: 1,00 * 100 - 80 = 20.
        df = _cashflow([{"erloes": 80.0, "zins": 40.0, "tilgung": 60.0}])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.jahre_event_of_default == [1]
        assert analyse.nachschuss_gesamt_eur == pytest.approx(20.0)
        # Ohne vorherige Ertraege gibt es nur externes Kapital.
        assert analyse.nachschuss_extern_eur == pytest.approx(20.0)
        assert analyse.braucht_externes_kapital

    def test_schwelle_unter_eins_deckt_mindestens_die_liquiditaetsluecke(self):
        # EoD-Schwelle 0,90: formal keine Verletzung bei DSCR 0,95 - die
        # Zahlungsluecke (100 - 95 = 5) muss trotzdem gedeckt werden.
        df = _cashflow([{"erloes": 95.0, "zins": 40.0, "tilgung": 60.0}])
        analyse = analysiere_kovenanten(df, 1.10, 0.90)

        assert analyse.jahre_event_of_default == []
        assert analyse.nachschuss_gesamt_eur == pytest.approx(5.0)

    def test_reserve_deckt_vor_ausschuettung_und_extern(self):
        # Jahr 1: DSCR 1,05x -> Cash Trap, 5 gehen in die Reserve.
        # Jahr 2: DSCR 0,80x -> Cure 20, davon 5 aus der Reserve.
        df = _cashflow([
            {"erloes": 105.0, "zins": 40.0, "tilgung": 60.0},
            {"erloes": 80.0, "zins": 40.0, "tilgung": 60.0},
        ])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.nachschuss_gesamt_eur == pytest.approx(20.0)
        assert analyse.nachschuss_aus_reserve_eur == pytest.approx(5.0)
        assert analyse.nachschuss_extern_eur == pytest.approx(15.0)

    def test_frueher_ausgeschuettetes_kapital_deckt_den_nachschuss(self):
        # Jahr 1: DSCR 1,50x -> 50 werden ausgeschuettet.
        # Jahr 2: DSCR 0,80x -> Cure 20, vollstaendig aus dem zuvor
        # ausgeschuetteten Kapital rueckfuehrbar: kein externes Kapital.
        df = _cashflow([
            {"erloes": 150.0, "zins": 40.0, "tilgung": 60.0},
            {"erloes": 80.0, "zins": 40.0, "tilgung": 60.0},
        ])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.nachschuss_gesamt_eur == pytest.approx(20.0)
        assert analyse.nachschuss_aus_ausschuettung_eur == pytest.approx(20.0)
        assert analyse.nachschuss_extern_eur == 0.0
        assert not analyse.braucht_externes_kapital
        assert analyse.nachschuss_intern_eur == pytest.approx(20.0)

    def test_ausgeschuettetes_kapital_wird_nicht_doppelt_verwendet(self):
        # 50 ausgeschuettet, danach zweimal ein Cure von je 20 und 40:
        # 50 intern, der Rest (10) extern.
        df = _cashflow([
            {"erloes": 150.0, "zins": 40.0, "tilgung": 60.0},
            {"erloes": 80.0, "zins": 40.0, "tilgung": 60.0},
            {"erloes": 60.0, "zins": 40.0, "tilgung": 60.0},
        ])
        analyse = analysiere_kovenanten(df, 1.10, 1.00)

        assert analyse.nachschuss_gesamt_eur == pytest.approx(60.0)
        assert analyse.nachschuss_intern_eur == pytest.approx(50.0)
        assert analyse.nachschuss_extern_eur == pytest.approx(10.0)


class TestIntegration:
    def test_bewertung_liefert_kovenanten_mit(self, project, global_assumptions):
        from engine import run_valuation

        analyse = run_valuation(project, global_assumptions).kovenanten

        assert analyse is not None
        assert analyse.schwelle_cash_trap == global_assumptions.dscr_cash_trap
        assert len(analyse.zeitreihe) == global_assumptions.betriebsdauer_jahre

    def test_schwellen_wirken_auf_die_ereignisse(self, project, global_assumptions):
        """Eine hoch angesetzte Cash-Trap-Schwelle muss Jahre markieren,
        die bei der Standardschwelle unauffaellig sind."""
        from engine import run_valuation

        ohne = run_valuation(project, global_assumptions).kovenanten
        global_assumptions.dscr_cash_trap = 99.0
        mit = run_valuation(project, global_assumptions).kovenanten

        assert not ohne.jahre_cash_trap
        assert len(mit.jahre_cash_trap) > 0
