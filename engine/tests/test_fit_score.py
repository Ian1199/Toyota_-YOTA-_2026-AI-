"""適配度評分測試（SPEC.md §9 情境 3 的 4 條規則）。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from engine.fit_score import score_fit


def test_chen_scenario_scores_95_after_summer_derate_rule():
    """陳先生：充電樁、長途目的地能充電，平常沒問題。但 290km 這一趟平常用掉
    290/300=97% 的「80% 安全續航」額度，夏天打 85 折後安全門檻降到 255km，
    290 > 255，會被新加的「夏天塞車開冷氣」規則扣 5 分，95 分（不再是 100）。
    （SPEC.md §9 寫「預期 88 分左右」跟文件自己定的扣分規則對不起來，
    88 不是這組規則湊得出來的數字，以規則為準。）"""
    r = score_fit(home_charging='wallbox', longest_single_day_km=290,
                  long_trips_per_month=1, long_trip_destination_can_charge=True)
    assert r['score'] == 95
    assert r['recommendation'] == 'bZ4X 純電完全適合'


def test_short_trip_has_no_summer_derate_penalty():
    """單日最長里程離門檻還很遠時，夏天打折也不會被扣分——不是只要有長途就扣。"""
    r = score_fit(home_charging='wallbox', longest_single_day_km=100,
                  long_trips_per_month=1, long_trip_destination_can_charge=True)
    assert r['score'] == 100


def test_no_home_charging_drops_30():
    """只知道「家裡不能充電」、沒有模擬結果可參考時，先用固定 −30（跟以前一樣）。"""
    r = score_fit(home_charging='none', longest_single_day_km=40,
                  long_trips_per_month=0, long_trip_destination_can_charge=True)
    assert r['score'] == 70


def test_no_home_charging_with_frequent_rescue_charging_drops_further():
    """家裡完全不能充電，而且天天通勤，模擬下來要常常靠外面快充救援（不是偶爾長途）——
    這是使用者截圖回報過的案例：路邊停車、完全不能充電、天天通勤 50km+，
    原本只會扣 30 分變成 70（適合純電），明顯低估了風險。"""
    r = score_fit(home_charging='none', longest_single_day_km=50,
                  long_trips_per_month=0, long_trip_destination_can_charge=True, rescue_charge_days=6)
    assert r['score'] < 70
    assert 'HEV' in r['recommendation']


def test_rescue_charge_days_extra_penalty_is_capped():
    r = score_fit(home_charging='none', longest_single_day_km=50,
                  long_trips_per_month=0, long_trip_destination_can_charge=True, rescue_charge_days=100)
    assert r['score'] == 40  # 100 - 30(無法充電) - 30(封頂)


def test_outlet_only_drops_10():
    r = score_fit(home_charging='outlet', longest_single_day_km=40,
                  long_trips_per_month=0, long_trip_destination_can_charge=True)
    assert r['score'] == 90


def test_long_day_over_80pct_range_drops_10():
    r = score_fit(home_charging='wallbox', longest_single_day_km=320,
                  long_trips_per_month=0, long_trip_destination_can_charge=True)
    assert r['score'] == 90


def test_frequent_long_trip_without_charging_drops_10():
    r = score_fit(home_charging='wallbox', longest_single_day_km=100,
                  long_trips_per_month=3, long_trip_destination_can_charge=False)
    assert r['score'] == 90


def test_worst_case_recommends_hev_phev():
    r = score_fit(home_charging='none', longest_single_day_km=320,
                  long_trips_per_month=3, long_trip_destination_can_charge=False)
    assert r['score'] == 50  # 100 - 30(無法充電) - 10(單日超範圍) - 10(長途頻繁且目的地不能充) = 50
    assert 'HEV' in r['recommendation']


def test_score_never_goes_below_zero():
    r = score_fit(home_charging='none', longest_single_day_km=320,
                  long_trips_per_month=3, long_trip_destination_can_charge=False)
    assert r['score'] >= 0
