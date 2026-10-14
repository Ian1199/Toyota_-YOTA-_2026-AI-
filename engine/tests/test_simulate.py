"""對照 SPEC.md §7.4 的 10 項檢查（住家充電＝可裝充電樁，其他用預設值）。"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.simulate import simulate_month

DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / 'data'


def _chen_result():
    persona = json.load(open(DATA_DIR / 'personas' / 'chen.json', encoding='utf-8'))
    return simulate_month(
        persona['schedule'],
        home_charging='wallbox',
        overnight_charge_hours={'tainan': 10},
    )


def test_color_day_counts():
    r = _chen_result()
    assert (r['green_days'], r['yellow_days'], r['red_days']) == (24, 4, 0)


def test_yellow_dates():
    r = _chen_result()
    dates = {d['date'] for d in r['days'] if d['color'] == 'yellow'}
    assert dates == {'2026-02-07', '2026-02-15', '2026-02-18', '2026-02-22'}


def test_total_km():
    r = _chen_result()
    assert r['total_km'] == 1500


def test_total_kwh_about_300():
    r = _chen_result()
    assert abs(r['total_kwh'] - 300) <= 5


def test_0215_arrival_no_stop_is_about_23pct():
    """去程不停站會抵達約 23%——驗算基礎算式：290km 不充電，100% 出發。
    用原始資料的副本把「中途快充」拿掉，才是真的在測「不停站」這個假設情境。"""
    persona = json.load(open(DATA_DIR / 'personas' / 'chen.json', encoding='utf-8'))
    day = dict(next(d for d in persona['schedule'] if d['date'] == '2026-02-15'))
    day.pop('midway_fast_charge_min', None)
    r = simulate_month([day], home_charging='wallbox')
    assert abs(r['days'][0]['low_pct'] - 23) <= 2


def test_0215_after_midway_charge_about_48pct():
    r = _chen_result()
    day = next(d for d in r['days'] if d['date'] == '2026-02-15')
    assert abs(day['low_pct'] - 48) <= 2


def test_0218_arrival_about_32pct():
    r = _chen_result()
    day = next(d for d in r['days'] if d['date'] == '2026-02-18')
    assert abs(day['low_pct'] - 32) <= 2


def test_monthly_ev_cost_about_1370():
    r = _chen_result()
    assert abs(r['cost_ev'] - 1370) <= 50


def test_monthly_gas_cost_is_3750():
    r = _chen_result()
    assert r['cost_gas'] == 3750


def test_monthly_save_about_2400():
    r = _chen_result()
    assert abs(r['save_ntd'] - 2400) <= 50


def test_no_home_charging_degrades_to_more_public_charging():
    """SPEC §7.2：住家無法充電時，改成低於 40% 隔天安排一次公共快充（記黃色）。"""
    persona = json.load(open(DATA_DIR / 'personas' / 'chen.json', encoding='utf-8'))
    r_none = simulate_month(persona['schedule'], home_charging='none', overnight_charge_hours={'tainan': 10})
    r_wallbox = _chen_result()
    assert r_none['yellow_days'] + r_none['red_days'] > r_wallbox['yellow_days'] + r_wallbox['red_days']
    assert r_none['dc_kwh'] > r_wallbox['dc_kwh']
