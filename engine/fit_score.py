"""油轉電適配度評分（SPEC.md §9 情境 3）。純規則，不靠 AI 猜分數。"""
from . import constants as C

ACTUAL_RANGE_KM = C.BATTERY_KWH * C.ACTUAL_EFFICIENCY_KM_PER_KWH  # ≈ 373.5km


def score_fit(home_charging, longest_single_day_km, long_trips_per_month, long_trip_destination_can_charge,
              actual_range_km=None, rescue_charge_days=0):
    """回傳 {score, reasons, recommendation}。

    home_charging: 'wallbox' | 'outlet' | 'none'
    longest_single_day_km: 這個月單日最長里程（通常是來回其中一段，不是來回合計）
    long_trips_per_month: 這個月的長途次數
    long_trip_destination_can_charge: 長途目的地能不能充電（bool）
    actual_range_km: 換車款時覆寫用（目前 demo 只有 bZ4X，預設用模組常數）
    rescue_charge_days: 這個月模擬出「要靠外出快充才撐得過去」的天數
        （simulate_month 的 yellow_days + red_days；simulate_month 對「家裡不能充電」
        的模擬是電量低於 40% 就自動排隔天去快充，所以就算每天通勤也很少真的「電不夠」
        見紅，但那不代表沒事——是天天都要去外面找快充。家裡完全不能充電時，原本只
        固定扣 30 分，不管平常通勤多遠；這裡改用真正模擬出來、要靠外面救援幾次的天數
        （不是用猜的）按比例加扣，救援太頻繁的話分數會掉到建議 HEV/PHEV 的範圍。
    """
    actual_range_km = actual_range_km or ACTUAL_RANGE_KM
    score = 100
    reasons = []

    if home_charging == 'none':
        score -= 30
        reasons.append('家裡無法安排充電（−30）')
        if rescue_charge_days > 0:
            extra = min(30, rescue_charge_days * 3)
            score -= extra
            reasons.append(f'模擬一個月下來有 {rescue_charge_days} 天得靠外面快充才夠用，不是偶爾長途而已（−{extra}）')
    elif home_charging == 'outlet':
        score -= 10
        reasons.append('家裡只有一般插座，沒有充電樁（−10）')

    threshold = actual_range_km * 0.8
    derated_threshold = threshold * C.SUMMER_AC_EFFICIENCY_DERATE  # 夏天塞車開冷氣，電效打 85 折後的門檻
    if longest_single_day_km > threshold:
        score -= 10
        reasons.append(f'單日最長行程 {longest_single_day_km:.0f}km，超過實際續航的 80%（約 {threshold:.0f}km）（−10）')
    elif longest_single_day_km > derated_threshold:
        score -= 5
        reasons.append(
            f'單日最長行程 {longest_single_day_km:.0f}km 平常沒問題，但夏天塞車開冷氣電效打 85 折後，'
            f'安全門檻會降到約 {derated_threshold:.0f}km，屆時會偏緊（−5）'
        )

    if long_trips_per_month > 2 and not long_trip_destination_can_charge:
        score -= 10
        reasons.append('這個月長途超過 2 次，且目的地沒辦法充電（−10）')

    score = max(0, score)

    if score >= 80:
        recommendation = 'bZ4X 純電完全適合'
    elif score >= 60:
        recommendation = '適合純電，但長途要先規劃外部充電'
    else:
        recommendation = '誠實建議：改推薦 TOYOTA HEV／PHEV'

    if not reasons:
        reasons.append('住家充電條件好、單日里程在續航範圍內、長途目的地能充電，沒有扣分項目')

    return {'score': score, 'reasons': reasons, 'recommendation': recommendation, 'actual_range_km': round(actual_range_km)}
