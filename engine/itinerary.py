"""把情境 2 對話抽出的欄位，組成一份跟 personas/chen.json 同格式的逐日行程。

這是跟使用者討論後加回來的範圍：陳先生／林小姐／王先生都只是「範例」，
情境 4-7 真正該讀的是這個函式組出來的行程，不是永遠讀寫死的 chen.json。
純規則組裝，不靠 AI：AI 只負責在情境 2 把對話整理成下面這份 profile，
行程怎麼變成逐日資料、要不要安排中途快充，全部是這裡的規則在決定。
"""
import calendar
import datetime

from . import constants as C

ACTUAL_RANGE_KM = C.BATTERY_KWH * C.ACTUAL_EFFICIENCY_KM_PER_KWH


def _city_distance_km(city):
    """查內建簡表；查不到時用「同縣市／跨縣市」粗估，並標記這是粗估。
    簡表 key 是「台北」「台中」這種不帶市/縣的簡稱，所以先去掉字尾再查一次。"""
    if city in C.CITY_DISTANCE_KM:
        return C.CITY_DISTANCE_KM[city], False
    bare = city[:-1] if city.endswith(('市', '縣')) else city
    if bare in C.CITY_DISTANCE_KM:
        return C.CITY_DISTANCE_KM[bare], False
    # 查不到：地名裡有「市」或「縣」字尾就當作跨縣市長途，其餘當同縣市內
    is_cross_county = city.endswith(('市', '縣'))
    km = C.UNKNOWN_CITY_CROSS_COUNTY_KM if is_cross_county else C.UNKNOWN_CITY_SAME_COUNTY_KM
    return km, True


def _needs_midway_charge(one_way_km, start_pct=100):
    """這一段如果會把電量拉到安全下限以下，就安排一次快充。
    start_pct 是出發當下的電量：去程從家裡出發，家充電樁充飽視為 100%；
    回程從過夜地點出發，電量要看那邊實際充了多少，不能也假設 100%
    （不然在外面只能用 110V 插座過夜、充不滿的情況會被忽略，見
    _long_trip_return_start_pct）。
    快充到「安全下限 + 10%」緩衝，換算成分鐘數（無條件進位）。"""
    need_kwh = one_way_km / C.ACTUAL_EFFICIENCY_KM_PER_KWH
    arrive_pct = start_pct - need_kwh / C.BATTERY_KWH * 100
    if arrive_pct >= C.SAFE_SOC_FLOOR_PCT:
        return None
    target_pct = C.SAFE_SOC_FLOOR_PCT + 10
    deficit_kwh = (target_pct - arrive_pct) / 100 * C.BATTERY_KWH
    minutes = deficit_kwh / C.DC_FAST_CHARGE_KWH_PER_MIN
    return max(5, round(minutes / 5) * 5)  # 湊整到 5 分鐘一個單位，比較像真實充電站的講法


def _long_trip_return_start_pct(one_way_km, nights):
    """回程出發當下的電量：去程耗掉的電，扣掉在外過夜用 110V 插座（非住家
    充電樁）充回來的部分。過夜晚數是「出發當晚 + nights 個整天」，跟
    build_itinerary 排進 schedule 的 overnight='trip_dest' 天數一致。"""
    need_kwh = one_way_km / C.ACTUAL_EFFICIENCY_KM_PER_KWH
    arrive_kwh = max(0.0, C.BATTERY_KWH - need_kwh)
    charging_nights = max(1, int(nights) + 1)
    nightly_kwh = C.HOME_OUTLET_110V_KW * C.TRIP_DEST_OVERNIGHT_HOURS
    charged_kwh = min(C.BATTERY_KWH - arrive_kwh, nightly_kwh * charging_nights)
    return (arrive_kwh + charged_kwh) / C.BATTERY_KWH * 100


def build_itinerary(profile, month='2026-02'):
    """profile 來自情境 2 抽出的結構化欄位：
    {"commute_km_per_day": float, "workdays_only": bool,
     "weekend_trips": [{"km": float}],
     "long_trips": [{"destination": str, "km": float|None, "nights": int}],
     ...}
    缺的欄位都有合理預設值，不會因為對話沒問到就爆炸。
    """
    year, mon = (int(x) for x in month.split('-'))
    days_in_month = calendar.monthrange(year, mon)[1]

    commute_km = float(profile.get('commute_km_per_day') or 0)
    weekend_trips = list(profile.get('weekend_trips') or [])
    long_trips = list(profile.get('long_trips') or [])

    # 把長途行程排進月份裡：平均分配在月中跟月底前，簡單但穩定的規則
    long_trip_days = {}
    if long_trips:
        slots = [days_in_month // (len(long_trips) + 1) * (i + 1) for i in range(len(long_trips))]
        for slot, trip in zip(slots, long_trips):
            slot = max(2, min(days_in_month - 1, slot))
            long_trip_days[slot] = trip

    weekend_trip_queue = list(weekend_trips)
    schedule = []
    skip_days = set()

    for slot, trip in long_trip_days.items():
        nights = int(trip.get('nights') or 0)
        for n in range(1, nights + 1):
            skip_days.add(slot + n)

    for day_num in range(1, days_in_month + 1):
        date = datetime.date(year, mon, day_num)
        weekday = date.weekday()  # 0=一 ... 6=日
        iso = date.isoformat()

        if day_num in long_trip_days:
            trip = long_trip_days[day_num]
            dest = trip.get('destination', '目的地')
            km, is_estimate = (trip['km'], False) if trip.get('km') else _city_distance_km(dest)
            nights = int(trip.get('nights') or 0)
            midway_min_out = _needs_midway_charge(km, start_pct=100)
            midway_min_back = _needs_midway_charge(km, start_pct=_long_trip_return_start_pct(km, nights))
            entry = {
                'date': iso, 'activity': f'出發前往{dest}', 'km': km,
                'overnight': 'trip_dest',
            }
            if midway_min_out:
                entry['midway_fast_charge_min'] = midway_min_out
            if is_estimate:
                entry['note'] = f'{dest} 距離依縣市粗估，非精確路線'
            schedule.append(entry)
            for n in range(1, nights + 1):
                schedule.append({'date': (date + datetime.timedelta(days=n)).isoformat(),
                                  'activity': f'在{dest}', 'km': 0, 'overnight': 'trip_dest'})
            return_date = date + datetime.timedelta(days=nights + 1)
            if return_date.month == mon:
                entry2 = {
                    'date': return_date.isoformat(), 'activity': f'從{dest}返家', 'km': km,
                    'overnight': 'home',
                }
                if midway_min_back:
                    entry2['midway_fast_charge_min'] = midway_min_back
                schedule.append(entry2)
                skip_days.add(return_date.day)
            continue

        if day_num in skip_days:
            continue

        if weekday < 5:  # 平日通勤
            schedule.append({'date': iso, 'activity': '通勤', 'km': commute_km, 'overnight': 'home'})
        else:  # 週末：輪流排進 weekend_trips，沒有就不開車
            if weekend_trip_queue:
                wk = weekend_trip_queue.pop(0)
                schedule.append({'date': iso, 'activity': wk.get('note', '週末出遊'),
                                  'km': float(wk.get('km') or 0), 'overnight': 'home'})
            else:
                schedule.append({'date': iso, 'activity': '不開車', 'km': 0, 'overnight': 'home'})

    schedule.sort(key=lambda d: d['date'])
    return schedule
