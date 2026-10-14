"""行程組裝測試：情境 2 對話抽出的 profile → 逐日 schedule（可直接餵給 simulate_month）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.itinerary import build_itinerary
from engine.simulate import simulate_month


def test_days_count_matches_month():
    sched = build_itinerary({'commute_km_per_day': 20}, month='2026-02')
    assert len(sched) == 28  # 2026 非閏年二月


def test_weekday_uses_commute_km():
    sched = build_itinerary({'commute_km_per_day': 25}, month='2026-02')
    weekdays = [d for d in sched if d['activity'] == '通勤']
    assert weekdays and all(d['km'] == 25 for d in weekdays)


def test_no_weekend_trip_means_zero_km():
    sched = build_itinerary({'commute_km_per_day': 20}, month='2026-02')
    by_date = {d['date']: d for d in sched}
    # 2026-02-07 是週六，沒給 weekend_trips 時應該是 0 公里
    assert by_date['2026-02-07']['km'] == 0


def test_weekend_trip_is_scheduled():
    sched = build_itinerary(
        {'commute_km_per_day': 20, 'weekend_trips': [{'km': 60, 'note': '陪家人出遊'}]},
        month='2026-02',
    )
    weekend_days = [d for d in sched if d['activity'] == '陪家人出遊']
    assert len(weekend_days) == 1
    assert weekend_days[0]['km'] == 60


def test_known_city_long_trip_uses_lookup_table():
    sched = build_itinerary(
        {'commute_km_per_day': 20, 'long_trips': [{'destination': '台南', 'nights': 1}]},
        month='2026-02',
    )
    depart = next(d for d in sched if '前往台南' in d['activity'])
    assert depart['km'] == 290  # constants.CITY_DISTANCE_KM['台南']
    assert depart['overnight'] == 'trip_dest'
    ret = next(d for d in sched if '返家' in d['activity'])
    assert ret['km'] == 290
    assert ret['overnight'] == 'home'


def test_unknown_city_falls_back_to_estimate_and_is_labeled():
    sched = build_itinerary(
        {'commute_km_per_day': 20, 'long_trips': [{'destination': '屏東市', 'nights': 0}]},
        month='2026-02',
    )
    depart = next(d for d in sched if '前往屏東市' in d['activity'])
    assert depart['km'] == 150  # UNKNOWN_CITY_CROSS_COUNTY_KM
    assert '粗估' in depart.get('note', '')


def test_far_long_trip_gets_midway_fast_charge():
    sched = build_itinerary(
        {'commute_km_per_day': 20, 'long_trips': [{'destination': '高雄', 'nights': 1}]},
        month='2026-02',
    )
    depart = next(d for d in sched if '前往高雄' in d['activity'])
    assert depart.get('midway_fast_charge_min', 0) > 0


def test_output_feeds_directly_into_simulate_month():
    sched = build_itinerary({'commute_km_per_day': 30}, month='2026-02')
    result = simulate_month(sched, home_charging='wallbox')
    assert result['total_km'] == 30 * 20  # 28 天中 20 個平日
    assert len(result['days']) == 28


def test_missing_fields_default_to_no_driving():
    sched = build_itinerary({}, month='2026-02')
    assert all(d['km'] == 0 for d in sched)
