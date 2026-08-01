"""
Frei benannte Zusatzpositionen bei Invest- und Betriebskosten.

Geprueft werden drei Dinge: dass die Namensvalidierung die Spalten der
Cashflow-Zeitreihe schuetzt, dass die Zusatzpositionen rechnerisch
identisch zu den Standardpositionen behandelt werden, und dass sie die
Persistenz (YAML/Excel) unbeschadet ueberstehen.
"""

from __future__ import annotations

import pytest

from engine import CapexBreakdown, CapexPosition, OpexItem
from engine.io_excel import excel_to_projects, projects_to_excel
from engine.io_yaml import load_project_yaml, save_project_yaml
from engine.pipeline import resolve_assumptions, run_valuation


class TestNamensvalidierung:
    @pytest.mark.parametrize("name", ["", "   "])
    def test_leerer_name_wird_abgelehnt(self, name):
        with pytest.raises(ValueError):
            CapexPosition(name=name, betrag_eur=1000.0)

    @pytest.mark.parametrize("name", ["opex_gesamt_eur", "Erloes_EUR", "jahr"])
    def test_reservierter_spaltenname_wird_abgelehnt(self, name):
        with pytest.raises(ValueError):
            CapexPosition(name=name, betrag_eur=1000.0)
        with pytest.raises(ValueError):
            OpexItem(name=name, basiswert_eur_kwp=1.0)

    def test_name_wird_getrimmt(self):
        assert CapexPosition(name="  Zaun  ", betrag_eur=1.0).name == "Zaun"


class TestZusatzCapex:
    def test_summe_enthaelt_zusatzpositionen(self):
        capex = CapexBreakdown(
            epc_eur=1_000_000.0,
            zusatzpositionen=[
                CapexPosition(name="Zaun", betrag_eur=25_000.0),
                CapexPosition(name="Archaeologie", betrag_eur=15_000.0),
            ],
        )
        assert capex.summe_eur == 1_040_000.0

    def test_leere_liste_aendert_die_summe_nicht(self):
        assert CapexBreakdown(epc_eur=500_000.0).summe_eur == 500_000.0

    def test_wirkt_wie_eine_erhoehung_der_standardposition(
        self, project, global_assumptions
    ):
        """Der Betrag geht ausschliesslich ueber die Summe in die Rechnung
        ein - eine Zusatzposition von 40.000 EUR muss deshalb exakt dasselbe
        Ergebnis liefern wie 40.000 EUR mehr EPC."""
        mit_zusatz = project.model_copy(deep=True)
        mit_zusatz.capex.zusatzpositionen = [
            CapexPosition(name="Zaun", betrag_eur=40_000.0)
        ]
        im_epc = project.model_copy(deep=True)
        im_epc.capex.epc_eur += 40_000.0

        a = run_valuation(mit_zusatz, global_assumptions)
        b = run_valuation(im_epc, global_assumptions)
        assert a.effective_assumptions.capex_total_eur == pytest.approx(
            b.effective_assumptions.capex_total_eur
        )
        assert a.kpis.npv_eur == pytest.approx(b.kpis.npv_eur)


class TestZusatzOpex:
    def test_wird_an_die_standardliste_angehaengt(self, project, global_assumptions):
        p = project.model_copy(deep=True)
        p.zusatz_opex = [OpexItem(name="Monitoring", basiswert_eur_kwp=2.0)]
        ea = resolve_assumptions(p, global_assumptions)
        namen = [i.name for i in ea.opex_items]
        # Standardpositionen zuerst, Zusatzpositionen dahinter - die
        # Reihenfolge bestimmt die Stapelreihenfolge im Kostendiagramm.
        assert namen[-1] == "Monitoring"
        assert "Betriebsführung" in namen

    def test_erscheint_als_eigene_spalte_der_zeitreihe(
        self, project, global_assumptions
    ):
        p = project.model_copy(deep=True)
        p.zusatz_opex = [OpexItem(name="Monitoring", basiswert_eur_kwp=2.0)]
        result = run_valuation(p, global_assumptions)
        df = result.cashflow.data
        assert "Monitoring" in df.columns
        assert "Monitoring" in result.cashflow.opex_posten
        # Zeile 0 ist das Investitionsjahr; das erste Betriebsjahr steht in
        # Zeile 1: 2 EUR/kWp * 1000 kWp, keine Indexierung im Testfixture.
        assert df["Monitoring"].iloc[1] == pytest.approx(2000.0)

    def test_erhoeht_die_gesamten_betriebskosten(self, project, global_assumptions):
        ohne = run_valuation(project, global_assumptions)
        p = project.model_copy(deep=True)
        p.zusatz_opex = [OpexItem(name="Monitoring", basiswert_eur_kwp=2.0)]
        mit = run_valuation(p, global_assumptions)
        delta = (
            mit.cashflow.data["opex_gesamt_eur"].iloc[1]
            - ohne.cashflow.data["opex_gesamt_eur"].iloc[1]
        )
        assert delta == pytest.approx(2000.0)
        assert mit.kpis.npv_eur < ohne.kpis.npv_eur


class TestPersistenz:
    def _projekt_mit_positionen(self, project):
        p = project.model_copy(deep=True)
        p.capex.zusatzpositionen = [
            CapexPosition(name="Zaun", betrag_eur=25_000.0),
            CapexPosition(name="Archäologie", betrag_eur=15_000.0),
        ]
        p.zusatz_opex = [
            OpexItem(
                name="Monitoring",
                basiswert_eur_kwp=2.0,
                index_pct_pa=0.02,
                start_betriebsjahr=3,
            )
        ]
        return p

    def test_yaml_roundtrip(self, project, tmp_path):
        p = self._projekt_mit_positionen(project)
        pfad = tmp_path / "projekt.yaml"
        save_project_yaml(p, pfad)
        assert load_project_yaml(pfad) == p

    def test_excel_roundtrip(self, project):
        p = self._projekt_mit_positionen(project)
        geladen = excel_to_projects(projects_to_excel([p]))[0]
        assert [(z.name, z.betrag_eur) for z in geladen.capex.zusatzpositionen] == [
            ("Zaun", 25_000.0),
            ("Archäologie", 15_000.0),
        ]
        assert geladen.capex.summe_eur == p.capex.summe_eur
        assert geladen.zusatz_opex == p.zusatz_opex

    def test_excel_roundtrip_ohne_zusatzpositionen(self, project):
        geladen = excel_to_projects(projects_to_excel([project]))[0]
        assert geladen.capex.zusatzpositionen == []
        assert geladen.zusatz_opex == []
