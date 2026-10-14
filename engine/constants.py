"""模擬引擎共用參數（SPEC.md §7.1）。所有情境共用同一組數字。"""

# 能耗 / 充電參數
ACTUAL_EFFICIENCY_KM_PER_KWH = 6.7 * 0.75  # ≈ 5.0；型錄 6.7 NEDC × 75% 保守估計
DC_FAST_CHARGE_KWH_PER_MIN = 1.87          # 28 分鐘充 74.7×70%=52.3 kWh 換算
HOME_WALLBOX_KW = 11
HOME_OUTLET_110V_KW = 1.3                   # 假設
SAFE_SOC_FLOOR_PCT = 15                     # 安全電量下限

# 費用參數（油價／家用電價在狀態面板可調，這裡放預設值）
GAS_KM_PER_L_DEFAULT = 12
GAS_PRICE_PER_L_DEFAULT = 30
HOME_ELEC_PRICE_PER_KWH_DEFAULT = 3
DC_PUBLIC_PRICE_PER_KWH = 10
ANNUAL_KM_FOR_5YR_COST = 15000

# 電池容量（陳先生情境使用 bZ4X；其他車款之後可依 vehicles/*.json 擴充）
BATTERY_KWH = 74.7

# 住家充電下拉選項對應的功率（None 代表不能充）
HOME_CHARGING_KW = {
    'wallbox': HOME_WALLBOX_KW,
    'outlet': HOME_OUTLET_110V_KW,
    'none': None,
}

# 無法在家充電時，改成電量低於這個比例的隔天安排一次公共快充
NO_HOME_CHARGING_TRIGGER_PCT = 40
NO_HOME_CHARGING_FAST_CHARGE_MIN = 15  # 假設：補到安全水位以上要花的快充時間

# 長途行程在外過夜（非住家）時，沒問到實際充電條件，先假設跟一般插座一樣每晚充幾小時
TRIP_DEST_OVERNIGHT_HOURS = 8

# 夏天塞車開冷氣：實際電效再打的折數（原本情境 5 壓力測試用的數字，
# 現在固定併進適配度評分的規則，不用再另外點一個情境才看得到這個風險）
SUMMER_AC_EFFICIENCY_DERATE = 0.85

# 情境 9：長途地名內建簡表（公里數，從桃園出發的概估單程距離）
CITY_DISTANCE_KM = {
    '台北': 45,
    '桃園': 0,
    '新竹': 70,
    '台中': 150,
    '彰化': 170,
    '台南': 290,
    '高雄': 330,
    '花蓮': 180,
}
# 查不到的地名，依是否同縣市做粗估（情境 2 對話組行程時使用）
UNKNOWN_CITY_SAME_COUNTY_KM = 30
UNKNOWN_CITY_CROSS_COUNTY_KM = 150
