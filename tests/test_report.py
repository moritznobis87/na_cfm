"""
Tests des PDF-Ergebnisberichts: Erzeugung aus den deterministischen
Fixtures, Grundstruktur (PDF-Header, Seitenzahl) und Kerninhalte
(Kapiteltitel, Kennzahlen) ueber die extrahierten Seitentexte.
"""

from __future__ import annotations

import io

import pytest

from engine import (
    break_even_zuschlag,
    calculate_lcoe,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
    run_valuation,
)
from engine.kpis import npv_at
from engine.sensitivity import run_eag_sensitivity


@pytest.fixture(scope="module")
def pdf_bytes(request):
    project = request.getfixturevalue("_projekt_modul")
    ga = request.getfixturevalue("_ga_modul")
    from app.report import ReportInputs, build_pdf_report

    result = run_valuation(project, ga)
    inputs = ReportInputs(
        project=project,
        global_assumptions=ga,
        result=result,
        tornado=run_tornado(project, ga),
        eag_sensitivitaet=run_eag_sensitivity(project, ga),
        monte_carlo=run_monte_carlo(project, ga, n_laeufe=40),
        szenarien=run_scenario_comparison(project, ga, 0.08),
        break_even_ct=break_even_zuschlag(project, ga, 0.08),
        lcoe_ct=calculate_lcoe(result.cashflow.data, 0.08),
        npv_eur=npv_at(result.cashflow, 0.08),
        diskontsatz_pct=0.08,
        logo_path=None,
    )
    return build_pdf_report(inputs)


# Modul-weite Kopien der Funktions-Fixtures (der Bericht ist teuer genug,
# um ihn nur einmal je Testmodul zu bauen).
@pytest.fixture(scope="module")
def _projekt_modul():
    from tests.conftest import _baue_projekt

    return _baue_projekt()


@pytest.fixture(scope="module")
def _ga_modul():
    from tests.conftest import _baue_global_assumptions

    return _baue_global_assumptions()


class TestPdfBericht:
    def test_pdf_header_und_groesse(self, pdf_bytes):
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 100_000

    def test_seitenzahl_und_kapitel(self, pdf_bytes):
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 12
        text = "\n".join(seite.extract_text() for seite in reader.pages)
        for erwartet in [
            "Wirtschaftlichkeitsanalyse",
            "Management Summary",
            "Ergebnisrechnung",
            "Sensitivitätsanalyse",
            "Monte-Carlo-Simulation",
            "Szenarienvergleich",
            "Annex: Annahmen der Berechnung",
            "Annex: Zeitreihen",
        ]:
            assert erwartet in text, erwartet

    def test_metadaten(self, pdf_bytes):
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert "Wirtschaftlichkeitsanalyse" in (reader.metadata.title or "")


@pytest.fixture(scope="module")
def pdf_text_freie_positionen(_projekt_modul, _ga_modul):
    """Bericht eines Projekts mit frei benannten Zusatzpositionen."""
    pypdf = pytest.importorskip("pypdf")
    from app.report import ReportInputs, build_pdf_report
    from engine import CapexPosition, OpexItem

    p = _projekt_modul.model_copy(deep=True)
    p.capex.zusatzpositionen = [
        CapexPosition(name="Wildschutzzaun", betrag_eur=25_000.0)
    ]
    p.zusatz_opex = [OpexItem(name="Fernueberwachung", basiswert_eur_kwp=2.0)]

    result = run_valuation(p, _ga_modul)
    inputs = ReportInputs(
        project=p,
        global_assumptions=_ga_modul,
        result=result,
        tornado=run_tornado(p, _ga_modul),
        eag_sensitivitaet=run_eag_sensitivity(p, _ga_modul),
        monte_carlo=run_monte_carlo(p, _ga_modul, n_laeufe=20),
        szenarien=run_scenario_comparison(p, _ga_modul, 0.08),
        break_even_ct=break_even_zuschlag(p, _ga_modul, 0.08),
        lcoe_ct=calculate_lcoe(result.cashflow.data, 0.08),
        npv_eur=npv_at(result.cashflow, 0.08),
        diskontsatz_pct=0.08,
        logo_path=None,
    )
    reader = pypdf.PdfReader(io.BytesIO(build_pdf_report(inputs)))
    return "\n".join(seite.extract_text() for seite in reader.pages)


class TestFreiePositionenImBericht:
    """Frei benannte Zusatzpositionen muessen im Bericht sichtbar sein -
    in der CAPEX-Aufstellung des Annex A und in der Positionsliste der
    Betriebskosten."""

    def test_zusatz_capex_erscheint(self, pdf_text_freie_positionen):
        assert "Wildschutzzaun" in pdf_text_freie_positionen

    def test_zusatz_opex_erscheint(self, pdf_text_freie_positionen):
        assert "Fernueberwachung" in pdf_text_freie_positionen
