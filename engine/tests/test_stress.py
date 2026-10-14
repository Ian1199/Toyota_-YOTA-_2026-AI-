"""最長一趟行程模擬的測試（engine/stress.py，被適配度評分跟焦慮雷達共用）。"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.stress import longest_trip_result, longest_trip_summer_derate_result

DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / 'data'


def _chen_schedule():
    persona = json.load(open(DATA_DIR / 'personas' / 'chen.json', encoding='utf-8'))
    return persona['schedule'], persona['overnight_charge_hours']


def test_longest_trip_picks_the_290km_day():
    schedule, hours = _chen_schedule()
    r = longest_trip_result(schedule, 'wallbox', hours)
    assert r['days'][0]['km'] == 290
    assert r['days'][0]['date'] == '2026-02-15'


def test_longest_trip_matches_0215_from_full_month():
    """單獨抓這一天出來跑，結果要跟情境 4 整月模擬裡的 2/15 一致（同一套引擎，不該有兩種答案）。"""
    schedule, hours = _chen_schedule()
    from engine.simulate import simulate_month
    full = simulate_month(schedule, home_charging='wallbox', overnight_charge_hours=hours)
    full_0215 = next(d for d in full['days'] if d['date'] == '2026-02-15')
    r = longest_trip_result(schedule, 'wallbox', hours)
    assert r['days'][0]['low_pct'] == full_0215['low_pct']


def test_summer_derate_uses_more_charging_than_normal():
    schedule, hours = _chen_schedule()
    normal = longest_trip_result(schedule, 'wallbox', hours)
    hot = longest_trip_summer_derate_result(schedule, 'wallbox', hours)
    assert hot['days'][0]['low_pct'] < normal['days'][0]['low_pct']


def test_empty_schedule_returns_none():
    assert longest_trip_result([], 'wallbox') is None
    assert longest_trip_summer_derate_result([], 'wallbox') is None
