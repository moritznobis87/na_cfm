"""
Erzeugt die Zahlen des durchgerechneten Beispiels in Kapitel 13 der
Dokumentation (`rechenmodell.md`) - direkt aus der Engine, damit die
dort abgedruckten Werte nachvollziehbar reproduzierbar sind.

Aufruf:  python docs/rechenmodell/beispiel.py

Die Ausgabe ist fertiges Markdown und kann unveraendert in
`rechenmodell.md` uebernommen werden. `tests/test_dokumentation.py`
prueft, dass die dokumentierten Werte weiterhin dem Rechenergebnis
entsprechen.
"""

from __future__ import annotations

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WURZEL))

from engine import run_valuation  # noqa: E402
from engine.io_yaml import (  # noqa: E402
    load_global_assumptions_yaml,
    load_project_yaml,
)
from engine.pipeline import resolve_assumptions  # noqa: E402

PROJEKT = WURZEL / "data" / "projects" / "template-agri.yaml"
ANNAHMEN = WURZEL / "data" / "global_assumptions.yaml"


def _de(wert: float | None, stellen: int = 0) -> str:
    if wert is None:
        return "–"
    text = f"{wert:,.{stellen}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def lade():
    return (
        load_project_yaml(PROJEKT),
        load_global_assumptions_yaml(ANNAHMEN),
    )


def main() -> None:
    projekt, global_annahmen = lade()
    ea = resolve_assumptions(projekt, global_annahmen)
    ergebnis = run_valuation(projekt, global_annahmen)
    df = ergebnis.cashflow.data
    betrieb = df[df["jahr"] > 0]

    print("### Eingangsgrößen\n")
    print("| Größe | Wert |")
    print("| --- | --- |")
    for name, wert in [
        ("Nennleistung", f"{_de(ea.nennleistung_kwp)} kWp"),
        ("Spezifischer Ertrag", f"{_de(ea.vollbenutzungsstunden_kwh_kwp)} kWh/kWp"),
        ("Inbetriebnahme", f"{ea.inbetriebnahme_monat:02d}/{ea.inbetriebnahme_jahr}"),
        ("Investitionsvolumen", f"{_de(ea.capex_total_eur)} €"),
        ("Eigenkapitalquote", f"{_de(ea.eigenkapitalquote_pct * 100, 1)} %"),
        ("Fremdkapitalzins", f"{_de(ea.fremdkapitalzins_pct * 100, 2)} %"),
        ("EAG-Zuschlagswert (effektiv)",
         f"{_de(ea.eag_zuschlagswert_effektiv_ct_kwh, 2)} ct/kWh"),
        ("Degradation", f"{_de(ea.degradation_pct_pa * 100, 2)} %/a"),
        ("Szenario", ea.marktpreisszenario_name),
    ]:
        print(f"| {name} | {wert} |")

    print("\n### Zeitreihe (ausgewählte Betriebsjahre)\n")
    spalten = [
        ("jahr", "Jahr", 0),
        ("produktion_kwh", "Produktion (kWh)", 0),
        ("marktwert_nominal_ct_kwh", "Marktwert nom. (ct/kWh)", 3),
        ("verguetungssatz_ct_kwh", "Vergütungssatz (ct/kWh)", 3),
        ("erloes_eur", "Erlös (€)", 0),
        ("opex_gesamt_eur", "OPEX (€)", 0),
        ("zinsen_eur", "Zinsen (€)", 0),
        ("tilgung_eur", "Tilgung (€)", 0),
        ("steuer_eur", "Steuer (€)", 0),
        ("cf_gesamt_eur", "Equity-CF (€)", 0),
    ]
    print("| " + " | ".join(t for _, t, _ in spalten) + " |")
    print("| " + " | ".join("---" for _ in spalten) + " |")
    for jahr in (1, 2, 3, 20, 21, 30):
        zeile = betrieb[betrieb["jahr"] == jahr]
        if zeile.empty:
            continue
        z = zeile.iloc[0]
        print("| " + " | ".join(_de(float(z[s]), n) for s, _, n in spalten) + " |")

    kpis = ergebnis.kpis
    print("\n### Kennzahlen\n")
    print("| Kennzahl | Wert |")
    print("| --- | --- |")
    print(f"| Investitionsvolumen | {_de(kpis.capex_total_eur)} € |")
    print(f"| Eigenkapitaleinsatz (Jahr 0) | {_de(kpis.eigenkapital_eur)} € |")
    irr = None if kpis.equity_irr is None else kpis.equity_irr * 100
    print(f"| EK-Rendite (XIRR) | {_de(irr, 2)} % |")
    print(f"| NPV bei 8 % | {_de(kpis.npv_eur)} € |")
    print(f"| Minimaler DSCR | {_de(kpis.dscr_min, 2)} |")
    print(f"| Payback (kumulierter Equity-CF ≥ 0) | Jahr {_de(kpis.payback_jahre)} |")
    print(f"| Summe Erlöse über {ea.betriebsdauer_jahre} Jahre "
          f"| {_de(float(betrieb['erloes_eur'].sum()))} € |")


if __name__ == "__main__":
    main()
