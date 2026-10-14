"""5 年持有成本測試（SPEC.md §7.3）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.cost import cost_5yr


def test_gas_cost_matches_formula():
    r = cost_5yr(annual_km=18000, gas_km_per_l=12, gas_price_per_l=30, years=5)
    assert r['gas_energy_cost'] == round(18000 / 12 * 30 * 5)


def test_ev_cost_home_charging_cheaper_than_no_home_charging():
    with_home = cost_5yr(annual_km=18000, home_charging='wallbox')
    no_home = cost_5yr(annual_km=18000, home_charging='none')
    assert with_home['ev_energy_cost'] < no_home['ev_energy_cost']


def test_ev_cheaper_than_gas_for_chen_scenario():
    r = cost_5yr(annual_km=1500 * 12, home_charging='wallbox')
    assert r['ev_energy_cost'] < r['gas_energy_cost']


def test_maintenance_is_not_invented_a_number():
    r = cost_5yr(annual_km=18000)
    assert isinstance(r['maintenance_note'], str) and '依和泰' in r['maintenance_note']
