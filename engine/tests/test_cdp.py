"""CDP 相似車主查詢測試（SPEC.md §9 情境 6 的退回邏輯）。"""
import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.cdp import find_similar_owners, load_owners

TODAY = datetime.date(2026, 10, 11)


def test_loads_all_3037_rows():
    assert len(load_owners()) == 3037


def test_chen_scenario_uses_city_plus_age_tier():
    r = find_similar_owners('桃園市', 52, today=TODAY)
    assert r['count'] == 152
    assert '桃園市' in r['basis']
    assert '退回' not in r['basis']


def test_chen_median_matches_deck_number():
    """簡報「持有一年以上車主的年定保中位數：2 次」。"""
    r = find_similar_owners('桃園市', 52, today=TODAY)
    assert r['median_visits_paid_service'] == 2


def test_rare_city_falls_back_to_age_only():
    r = find_similar_owners('連江縣', 52, today=TODAY)
    assert '退回' in r['basis']
    assert r['count'] > 152  # 比桃園那層樣本大很多


def test_sample_count_never_zero():
    r = find_similar_owners('連江縣', 52, today=TODAY)
    assert r['count'] > 0
