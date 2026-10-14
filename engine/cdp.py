"""CDP bZ4X 車主資料：載入＋相似車主查詢（SPEC.md §6.2、§9 情境 6）。

只用 3,037 筆 bZ4X 專屬檔案，不碰那份疑似被截斷的 104 萬筆全車系檔案
（細節見跟使用者討論紀錄：全車系檔剛好卡在 Excel 104 萬列上限，而且
兩個檔案的「編號」都只是各自檔案內的流水號，沒辦法跨檔案對同一個人）。
"""
import csv
import datetime
import statistics
from pathlib import Path

CSV_PATH = (
    Path(__file__).resolve().parents[2]
    / 'TOYOTA EV新生活 競賽數據'
    / '2026 AI黑客松CDP 電動車主補充資料資料 (T車輛).csv'
)

# 欄位用位置對應，不用檔案裡的欄位名稱當 key——補充資料檔的第一欄表頭是
# 「4.3」這種明顯錯位的殘留字串，不是「編號」，位置才是可靠的依據。
COL_AGE = 2
COL_CITY = 3
COL_VISITS_ANY = 5          # 近一年回廠次數（不論原因，不論是否有花費）
COL_VISITS_PAID = 7         # 近一年回廠有費定保次數
COL_DELIVERY_DATE = 11      # 現保有車交車日期_T

_cache = None


def _parse_age(raw):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None  # 0 代表沒填，不是真的 0 歲


def _parse_date(raw):
    try:
        return datetime.datetime.strptime(raw.strip(), '%Y/%m/%d').date()
    except (ValueError, AttributeError):
        return None


def load_owners():
    """載入並快取全部 3,037 筆（一次，之後重複呼叫不重讀檔案）。"""
    global _cache
    if _cache is not None:
        return _cache
    rows = []
    with open(CSV_PATH, encoding='cp950') as f:
        reader = csv.reader(f)
        next(reader)  # 跳過表頭
        for r in reader:
            if len(r) <= COL_DELIVERY_DATE:
                continue
            rows.append({
                'age': _parse_age(r[COL_AGE]),
                'city': r[COL_CITY].strip(),
                'visits_any': int(r[COL_VISITS_ANY]) if r[COL_VISITS_ANY].strip().isdigit() else None,
                'visits_paid_service': int(r[COL_VISITS_PAID]) if r[COL_VISITS_PAID].strip().isdigit() else None,
                'delivery_date': _parse_date(r[COL_DELIVERY_DATE]),
            })
    _cache = rows
    return rows


def find_similar_owners(city, age, today=None, min_sample=30, hard_floor=10):
    """SPEC §9 情境 6：同縣市＋年齡±5；不足 min_sample 人只看年齡；
    （額外加的第二層兜底，SPEC 沒寫但討論時加的）再不足 hard_floor 人就看全體。
    回傳 {count, basis, median_visits_any, median_visits_paid, n_held_1yr_plus}。
    """
    owners = load_owners()
    today = today or datetime.date.today()
    one_year_ago = today.replace(year=today.year - 1)

    def age_match(o):
        return o['age'] is not None and abs(o['age'] - age) <= 5

    def city_match(o):
        return o['city'] == city

    same_city_age = [o for o in owners if city_match(o) and age_match(o)]
    if len(same_city_age) >= min_sample:
        pool, basis = same_city_age, f'{city}・年齡 {age}±5 歲'
    else:
        age_only = [o for o in owners if age_match(o)]
        if len(age_only) >= hard_floor:
            pool, basis = age_only, f'年齡 {age}±5 歲（{city}同縣市樣本不足，退回只看年齡）'
        else:
            pool, basis = owners, '全體 bZ4X 車主（縣市＋年齡樣本都不足，退回看全體）'

    held_1yr = [o for o in pool if o['delivery_date'] and o['delivery_date'] <= one_year_ago]
    visits_any = [o['visits_any'] for o in held_1yr if o['visits_any'] is not None]
    visits_paid = [o['visits_paid_service'] for o in held_1yr if o['visits_paid_service'] is not None]

    return {
        'count': len(pool),
        'basis': basis,
        'held_1yr_plus_count': len(held_1yr),
        'median_visits_any': statistics.median(visits_any) if visits_any else None,
        'median_visits_paid_service': statistics.median(visits_paid) if visits_paid else None,
        'source': f'和泰 CDP，n = {len(pool)}',
    }
