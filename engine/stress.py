"""最長一趟行程的模擬：平常、夏天塞車開冷氣兩種算法（SPEC.md §9 情境 3／5）。

這裡原本是情境 5「壓力測試」三張固定卡片的邏輯。拿掉那個獨立情境後，
這兩個函式變成被共用的內部工具：適配度評分（engine/fit_score.py）用它判斷
要不要扣「夏天打折會變緊」那條規則，焦慮雷達（app.py 的 /api/radar）用它在
顧客提到長途／極端天氣時，附上這趟行程平常跟打折後的對照數字當證據。
純函式，不碰 Claude。
"""
from . import constants as C
from .simulate import simulate_month


def longest_trip_result(schedule, home_charging, overnight_charge_hours=None):
    """挑行程裡里程最長的那一天，單獨模擬（陳先生的情況就是 2/15 桃園→台南）。"""
    if not schedule:
        return None
    day = max(schedule, key=lambda d: d.get('km', 0))
    return simulate_month([day], home_charging=home_charging, overnight_charge_hours=overnight_charge_hours)


def longest_trip_summer_derate_result(schedule, home_charging, overnight_charge_hours=None, derate=None):
    """同一天，電效打折（預設夏天塞車開冷氣的折數）重算，給「平常 vs 打折後」的對照。"""
    if not schedule:
        return None
    derate = derate or C.SUMMER_AC_EFFICIENCY_DERATE
    day = max(schedule, key=lambda d: d.get('km', 0))
    derated_eff = C.ACTUAL_EFFICIENCY_KM_PER_KWH * derate
    return simulate_month(
        [day], home_charging=home_charging, overnight_charge_hours=overnight_charge_hours,
        params={'efficiency_km_per_kwh': derated_eff},
    )
