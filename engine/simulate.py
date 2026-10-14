"""逐日電量模擬（SPEC.md §7.2）。純函式，不碰 Claude、不碰檔案系統。

輸入一份行程（跟 personas/*.json 的 schedule 欄位同格式，不管是哪個人、
是手寫的範例還是從對話組出來的，只要格式一樣就能跑），輸出每天的電量
變化、顏色標記，以及全月的用電／費用彙總。
"""
from . import constants as C


def _round(x):
    return round(x + 1e-9)


def simulate_month(schedule, home_charging, overnight_charge_hours=None, params=None):
    """逐日模擬一個月的電量。

    schedule: list of day dict，每筆至少有 km；可選 overnight（預設 'home'）、
        midway_fast_charge_min、public_charge_kwh。
    home_charging: 'wallbox' | 'outlet' | 'none' —— 只影響 overnight == 'home' 的那幾天；
        其他過夜地點（例如借宿台南老家）用該筆資料自己標的充電方式，不受這個影響。
    overnight_charge_hours: dict，非 home 的過夜地點要用插座充幾小時，
        例如 {'tainan': 10}（SPEC §8：台南老家每晚 10 小時）。沒給的地點視為不能充。
    params: 覆寫 constants 用的參數 dict——電池容量、電效（情境 5「夏天塞車開冷氣」用
        85 折後的電效重算）、油價／電價，之後多車款時可以再擴充。
    """
    overnight_charge_hours = overnight_charge_hours or {}
    params = params or {}
    battery_kwh = params.get('battery_kwh', C.BATTERY_KWH)
    eff = params.get('efficiency_km_per_kwh', C.ACTUAL_EFFICIENCY_KM_PER_KWH)
    gas_km_per_l = params.get('gas_km_per_l', C.GAS_KM_PER_L_DEFAULT)
    gas_price_per_l = params.get('gas_price_per_l', C.GAS_PRICE_PER_L_DEFAULT)
    home_elec_price = params.get('home_elec_price', C.HOME_ELEC_PRICE_PER_KWH_DEFAULT)

    soc = battery_kwh  # 月初滿電出發（SPEC §8 陳先生案例的假設）
    days = []
    dc_total = 0.0
    ac_total = 0.0
    pending_fast_charge = False  # 住家無法充電時，隔天要補一次快充

    for day in schedule:
        km = float(day.get('km', 0))
        overnight = day.get('overnight', 'home')
        start_pct = soc / battery_kwh * 100

        need_kwh = km / eff
        soc -= need_kwh / 2  # 先扣到「半路」

        dc_kwh_today = 0.0
        dc_min_today = 0.0
        public_kwh_today = 0.0

        # 1) 長途中途快充（資料裡已經標好要不要快充、充幾分鐘）
        midway_min = day.get('midway_fast_charge_min')
        if midway_min:
            dc_min_today += float(midway_min)
            add_kwh = float(midway_min) * C.DC_FAST_CHARGE_KWH_PER_MIN
            soc = min(battery_kwh, soc + add_kwh)
            dc_kwh_today += add_kwh

        # 2) 補一次「住家無法充電」觸發的快充（安排在前一天電量過低的隔天）
        if pending_fast_charge:
            add_kwh = C.NO_HOME_CHARGING_FAST_CHARGE_MIN * C.DC_FAST_CHARGE_KWH_PER_MIN
            soc = min(battery_kwh, soc + add_kwh)
            dc_kwh_today += add_kwh
            dc_min_today += C.NO_HOME_CHARGING_FAST_CHARGE_MIN
            pending_fast_charge = False

        soc -= need_kwh / 2  # 扣完剩下半路

        # 3) 計畫中的外出充電（例如百貨公司順手充）——算進快充／公共電價那一類
        public_kwh = day.get('public_charge_kwh')
        if public_kwh:
            public_kwh_today += float(public_kwh)
            soc = min(battery_kwh, soc + float(public_kwh))
            dc_kwh_today += float(public_kwh)

        arrive_pct = max(0.0, soc / battery_kwh * 100)
        low_pct = arrive_pct  # 這裡還沒算晚上充電，就是當天跑完後的最低點

        # 4) 晚上依停車地點充電
        ac_kwh_today = 0.0
        if overnight == 'home':
            kw = C.HOME_CHARGING_KW.get(home_charging)
            if home_charging == 'wallbox':
                ac_kwh_today = max(0.0, battery_kwh - soc)  # 充到 100%
                soc = battery_kwh
            elif home_charging == 'outlet':
                ac_kwh_today = min(C.HOME_OUTLET_110V_KW * 8, battery_kwh - soc)  # 假設在家一晚約 8 小時
                soc = min(battery_kwh, soc + ac_kwh_today)
            else:  # none：今晚不能充，但如果電量過低，標記明天要補一次公共快充
                if arrive_pct < C.NO_HOME_CHARGING_TRIGGER_PCT:
                    pending_fast_charge = True
        else:
            hours = overnight_charge_hours.get(overnight)
            if hours:
                ac_kwh_today = min(C.HOME_OUTLET_110V_KW * hours, battery_kwh - soc)
                soc = min(battery_kwh, soc + ac_kwh_today)

        end_pct = soc / battery_kwh * 100

        # 5) 顏色：紅 > 黃 > 綠
        if low_pct < C.SAFE_SOC_FLOOR_PCT:
            color = 'red'
        elif dc_kwh_today > 0 or public_kwh_today > 0:
            color = 'yellow'
        else:
            color = 'green'

        dc_total += dc_kwh_today
        ac_total += ac_kwh_today

        days.append({
            'date': day.get('date'),
            'activity': day.get('activity', ''),
            'km': km,
            'start_pct': _round(start_pct),
            'low_pct': _round(low_pct),
            'end_pct': _round(end_pct),
            'dc_kwh': round(dc_kwh_today, 1),
            'dc_min': dc_min_today,
            'ac_kwh': round(ac_kwh_today, 1),
            'color': color,
        })

    total_km = sum(d['km'] for d in days)
    total_kwh = round(dc_total + ac_total, 1)
    cost_ev = _round(ac_total * home_elec_price + dc_total * C.DC_PUBLIC_PRICE_PER_KWH)
    cost_gas = _round(total_km / gas_km_per_l * gas_price_per_l)

    return {
        'days': days,
        'total_km': total_km,
        'total_kwh': total_kwh,
        'dc_kwh': round(dc_total, 1),
        'ac_kwh': round(ac_total, 1),
        'cost_ev': cost_ev,
        'cost_gas': cost_gas,
        'save_ntd': cost_gas - cost_ev,
        'min_pct': min(d['low_pct'] for d in days) if days else 100,
        'green_days': sum(1 for d in days if d['color'] == 'green'),
        'yellow_days': sum(1 for d in days if d['color'] == 'yellow'),
        'red_days': sum(1 for d in days if d['color'] == 'red'),
    }
