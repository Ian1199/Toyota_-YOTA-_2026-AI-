"""電量Yota顧 Demo —— Flask 入口。

第 1 步只搭骨架：左側面板＋iPhone 外框版面、設計樣式、情境清單。
計算引擎（第 2 步）、各情境內容與 Claude API（第 3–7 步）之後陸續補上。
"""
import datetime
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, render_template, request

from claude_client import ask_claude, ask_claude_tool
from engine import constants as C
from engine.cdp import find_similar_owners
from engine.cost import cost_5yr
from engine.fit_score import score_fit
from engine.itinerary import build_itinerary
from engine.simulate import simulate_month
from engine.stress import longest_trip_result, longest_trip_summer_derate_result

logging.basicConfig(level=logging.INFO)
log = logging.getLogger('bz-demo')

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-me')

CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5-5')
BUILD_VERSION = str(int(time.time()))  # 每次重啟伺服器就換號，逼瀏覽器重抓 CSS/JS，不會再卡舊快取
API_KEY_PRESENT = bool(os.environ.get('ANTHROPIC_API_KEY'))
if not API_KEY_PRESENT:
    log.warning('ANTHROPIC_API_KEY 未設定——情境 2/3/4/6/7 呼叫 Claude 的部分會失敗。')

# SPEC.md §4 情境清單；render 函式在後續步驟逐一掛上，目前先讓按鈕都看得到、點得動
SCENARIOS = [
    {'id': 'push', 'no': 1, 'label': '回廠推播'},
    {'id': 'chat', 'no': 2, 'label': '對話診斷'},
    {'id': 'fit', 'no': 3, 'label': '適配度'},
    {'id': 'calendar', 'no': 4, 'label': '電車月曆'},
    {'id': 'radar', 'no': 5, 'label': '焦慮雷達'},
    {'id': 'summary', 'no': 6, 'label': '業務摘要卡'},
]


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


@app.after_request
def no_cache(resp):
    # 開發階段：Chrome 的一般「重新整理」常常直接吃快取、連新版網頁都不跟伺服器要，
    # 這裡強制每個回應都不准瀏覽器快取，之後每次改完都保證看到最新版本。
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/')
def index():
    persona = load_json(DATA_DIR / 'personas' / 'chen.json')
    return render_template(
        'index.html',
        scenarios=SCENARIOS,
        persona=persona,
        claude_model=CLAUDE_MODEL,
        build_version=BUILD_VERSION,
    )


def _current_persona():
    return load_json(DATA_DIR / 'personas' / 'chen.json')


def _resolve_persona_and_profile(body):
    """情境 4/6 共用：有情境 2 對話組出的 profile 就用那份（還原成 persona 跑引擎），
    沒有就退回陳先生這份範例——兩種情況最後都回傳 (persona, profile) 一組。"""
    live_profile = body.get('profile')
    if live_profile:
        return _dynamic_persona(live_profile), live_profile
    persona = _current_persona()
    return persona, persona['profile']


def _dynamic_persona(profile):
    """把情境 2 對話組出來的 profile，轉成跟 personas/chen.json 同形狀的資料，
    讓情境 4 可以直接用同一套邏輯跑，不管讀到的是範例還是真的對話結果。"""
    return {
        'name': '您',
        'city': profile.get('city') or '—',
        'housing': profile.get('housing') or '',
        'current_car': {'fuel_km_per_l': profile.get('current_car_km_per_l') or C.GAS_KM_PER_L_DEFAULT},
        'concerns_raw': profile.get('concerns_raw') or [],
        'month': '2026-02',
        'month_label': '2026 年 2 月',
        'schedule': build_itinerary(profile, month='2026-02'),
        # 行程裡在外過夜（trip_dest）沒問過能充多少小時，先假設跟一般插座一樣充一晚 8 小時
        'overnight_charge_hours': {'trip_dest': C.TRIP_DEST_OVERNIGHT_HOURS},
    }


DIARY_SYSTEM = (
    '你是幫電動車主寫「電車日記」的助手，寫給他自己回顧這個月用車的心得。'
    '規則：(1) 只能使用使用者訊息裡 JSON 給的數字與地名，不可以自己編造任何數字、地名或情節；'
    '(2) 數字要講得像日常口語（例如「省下約 2,400 元」），不要條列、不要像在報告數據；'
    '(3) 繁體中文、最多 3 句話、第一人稱車主語氣；'
    '(4) 如果 notable_trips 裡有長途行程，挑最長的一筆講具體細節（幾公里、中途充幾分鐘、抵達剩多少電）。'
)


def _build_diary_payload(persona, result, cost5yr):
    highlight_days = sorted(
        (d for d in result['days'] if d['color'] in ('yellow', 'red') and d['km'] >= 100),
        key=lambda d: -d['km'],
    )
    return {
        'home_city': persona['city'],
        'green_days': result['green_days'],
        'yellow_days': result['yellow_days'],
        'red_days': result['red_days'],
        'total_km_this_month': result['total_km'],
        'save_ntd_this_month': result['save_ntd'],
        'notable_trips': [
            {'date': d['date'], 'activity': d['activity'], 'km': d['km'],
             'low_pct_after_trip': d['low_pct'], 'fast_charge_minutes': d['dc_min']}
            for d in highlight_days
        ],
        'save_ntd_over_5_years': cost5yr['save_energy_only'],
    }


@app.route('/api/calendar', methods=['POST'])
def api_calendar():
    body = request.get_json(silent=True) or {}
    home_charging = body.get('homeCharging', 'wallbox')
    fuel_price = float(body.get('fuelPrice') or 30)
    home_elec_price = float(body.get('homeElecPrice') or 3)

    persona, _profile = _resolve_persona_and_profile(body)
    gas_km_per_l = persona['current_car']['fuel_km_per_l']

    result = simulate_month(
        persona['schedule'],
        home_charging=home_charging,
        overnight_charge_hours=persona.get('overnight_charge_hours', {}),
        params={
            'gas_km_per_l': gas_km_per_l,
            'gas_price_per_l': fuel_price,
            'home_elec_price': home_elec_price,
        },
    )
    cost5yr = cost_5yr(
        annual_km=round(result['total_km'] * 12),
        gas_km_per_l=gas_km_per_l,
        gas_price_per_l=fuel_price,
        home_elec_price=home_elec_price,
        home_charging=home_charging,
    )

    diary = ask_claude(DIARY_SYSTEM, json.dumps(_build_diary_payload(persona, result, cost5yr), ensure_ascii=False))

    first_weekday = (datetime.date.fromisoformat(persona['schedule'][0]['date']).weekday() + 1) % 7  # 轉成週日=0

    return jsonify({
        'ok': True,
        'month_label': persona['month_label'],
        'first_weekday': first_weekday,
        'calendar': result,
        'cost5yr': cost5yr,
        'diary': diary,
        'assumptions': '試算依據：bZ4X 型錄；假設可在左側調整',
    })


CHAT_SYSTEM = (
    '你是 TOYOTA 電車顧問，用 LINE 聊天的口吻跟一位考慮換 bZ4X 的車主對話。'
    '目標是自然地問出以下「後勤欄位」（每次只問一個缺的項目，不要一次問好幾個，最多問 5 輪）：\n'
    '住的地方類型（housing）、有沒有固定車位（parking）、住家能不能裝充電設備（home_charging：'
    'wallbox＝可裝充電樁／outlet＝只有一般插座／none＝完全不能充電）、居住縣市（city）、'
    '平常通勤一天大約開幾公里（commute_km_per_day）、週末會不會額外開車出去、多遠（weekend_trips，'
    '每筆 {km, note}）、多久會有一次比較長途的行程、去哪裡、過幾夜（long_trips，每筆 '
    '{destination, nights, frequency_per_month}）、現在的車大概多少公里一公升（current_car_km_per_l）。\n'
    '不規則描述（例如「週末偶爾回彰化老家」）要自己換算成次數與里程估計，地名里程優先用這個內建簡表'
    '（單位 km，從桃園出發的概估單程距離）：' + json.dumps(C.CITY_DISTANCE_KM, ensure_ascii=False) + '，'
    '查不到的地名就先放地名、km 留空，由系統之後處理。已經問到的欄位不要重複問。\n'
    '後勤欄位問得差不多（或已經問了 5 輪）之後，不管還有沒有欄位缺，下一輪**一定要**單獨問一次'
    '「你會擔心電動車的哪些地方」這類開放式問題（講法可以口語化、不用照抄），把回答存進'
    'concerns_raw（字串陣列；顧客如果說沒有特別擔心，concerns_raw 存空陣列 []，不要編一句'
    '「沒有擔心」放進去）。這一題問過、拿到回答以後才能把 done 設成 true；不可以跳過這一題直接結束對話，也不可以在'
    '還沒問這一題之前就把 done 設成 true。done 設成 true 時，reply 改成邀請他看結果的一句話。\n'
    'quick_replies 給 2–3 個符合情境、顧客可能會直接點選回答的簡短選項（例如地名、「可以」'
    '「不行」這種，不要是問句）；問「會擔心哪些地方」那一輪，quick_replies 可以給幾個常見的'
    '擔心項目當範例（例如「充電方不方便」「保養/電池費用」「沒有特別擔心」）。\n'
    '每一輪都一定要呼叫 diagnose_turn 這個工具來回覆，不可以直接輸出文字訊息。'
)

CHAT_TOOL = {
    'name': 'diagnose_turn',
    'description': '回覆顧客一句話，並回傳目前為止抽出的顧客資料欄位',
    'input_schema': {
        'type': 'object',
        'properties': {
            'reply': {'type': 'string', 'description': '要對顧客說的一句話，口語、簡短'},
            'profile': {
                'type': 'object',
                'properties': {
                    'housing': {'type': 'string'},
                    'parking': {'type': 'string'},
                    'home_charging': {'type': 'string', 'enum': ['wallbox', 'outlet', 'none', '']},
                    'city': {'type': 'string'},
                    'commute_km_per_day': {'type': 'number'},
                    'weekend_trips': {
                        'type': 'array',
                        'items': {'type': 'object', 'properties': {
                            'km': {'type': 'number'}, 'note': {'type': 'string'},
                        }},
                    },
                    'long_trips': {
                        'type': 'array',
                        'items': {'type': 'object', 'properties': {
                            'destination': {'type': 'string'},
                            'km': {'type': ['number', 'null']},
                            'nights': {'type': 'number'},
                            'frequency_per_month': {'type': 'number'},
                        }},
                    },
                    'current_car_km_per_l': {'type': ['number', 'null']},
                    'concerns_raw': {'type': 'array', 'items': {'type': 'string'}},
                },
            },
            'done': {'type': 'boolean'},
            'quick_replies': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 3},
        },
        'required': ['reply', 'profile', 'done'],
    },
}


@app.route('/api/chat', methods=['POST'])
def api_chat():
    body = request.get_json(silent=True) or {}
    history = body.get('history') or []  # [{role:'user'|'assistant', text:str}]

    messages = [{'role': h['role'], 'content': h['text']} for h in history]
    if not messages:
        messages = [{'role': 'user', 'content': '（顧客剛點開通知，對話還沒開始，請你先主動打招呼並問第一個問題）'}]

    result = ask_claude_tool(CHAT_SYSTEM, messages, CHAT_TOOL)
    if not result['ok']:
        return jsonify({'ok': False, 'error': result['error']})

    data = result['input']
    return jsonify({
        'ok': True,
        'reply': data.get('reply', ''),
        'profile': data.get('profile', {}),
        'done': bool(data.get('done')),
        'quick_replies': data.get('quick_replies', []),
    })


def _longest_single_day_km(profile, itinerary_days):
    days_km = [d['km'] for d in itinerary_days]
    return max(days_km) if days_km else 0


def _default_profile():
    # 還沒跟顧客對話過時（例如一進頁面就直接點情境 3/7），先用陳先生這份範例資料。
    return _current_persona()['profile']


def _compute_fit_result(profile):
    home_charging = profile.get('home_charging') or 'none'
    itinerary_days = build_itinerary(profile)
    long_trips = profile.get('long_trips') or []
    long_trips_per_month = sum(float(t.get('frequency_per_month') or 1) for t in long_trips)

    # 「家裡完全不能充電」這條規則原本不管通勤多遠都固定扣 30 分，天天通勤跟偶爾開車
    # 風險差很多；這裡真的把行程跑一次模擬，用模擬出來「要靠外面快充幾天」反映嚴重程度
    # （simulate_month 對無法在家充電的模擬是電量過低就排隔天快充，很少真的見紅，
    # 但常常要去外面救援一樣是真實的負擔，所以用 yellow+red，不是只看 red）。
    rescue_charge_days = 0
    if home_charging == 'none' and itinerary_days:
        sim = simulate_month(itinerary_days, home_charging='none', overnight_charge_hours={'trip_dest': C.TRIP_DEST_OVERNIGHT_HOURS})
        rescue_charge_days = sim['yellow_days'] + sim['red_days']

    return score_fit(
        home_charging=home_charging,
        longest_single_day_km=_longest_single_day_km(profile, itinerary_days),
        long_trips_per_month=long_trips_per_month,
        # SPEC 沒有讓對話問「目的地能不能充電」，先假設長途景點通常找得到充電站；
        # 這是 demo 的已知假設，不是引擎亂猜的數字。
        long_trip_destination_can_charge=True,
        rescue_charge_days=rescue_charge_days,
    )


@app.route('/api/fit', methods=['POST'])
def api_fit():
    body = request.get_json(silent=True) or {}
    profile = body.get('profile') or _default_profile()

    result = _compute_fit_result(profile)

    phrase_system = (
        '你會收到一份電動車適配度的計算結果 JSON（分數、理由、建議都已經算好，不可更改）。'
        '把 reasons 陣列裡每一項改寫成口語、好懂的一句話，可以把「−30」這種記號講成白話，'
        '但數字本身不能變、不能新增或刪除項目。用換行分隔每一句，不要加編號、不要加其他說明文字。'
        '繁體中文。'
    )
    phrased = ask_claude(phrase_system, json.dumps(
        {'score': result['score'], 'reasons': result['reasons'], 'recommendation': result['recommendation']},
        ensure_ascii=False,
    ))
    reasons_for_display = result['reasons']
    if phrased['ok']:
        lines = [l.strip('-•  　') for l in phrased['text'].splitlines() if l.strip()]
        if len(lines) == len(result['reasons']):
            reasons_for_display = lines

    return jsonify({
        'ok': True,
        'score': result['score'],
        'reasons': reasons_for_display,
        'raw_reasons': result['reasons'],
        'recommendation': result['recommendation'],
        'actual_range_km': result['actual_range_km'],
    })


# SPEC.md §6.3：Kantar 市調 12 類不買純電車原因；情境 5（焦慮雷達）跟情境 6（業務摘要卡）共用同一份分類。
ANXIETY_REASONS = [
    {'reason': '擔心充電不方便', 'pct': 66, 'group': '基礎設施'},
    {'reason': '更換電池費用昂貴', 'pct': 58, 'group': '財務'},
    {'reason': '擔心電池壽命短', 'pct': 56, 'group': '財務'},
    {'reason': '車款價格較高', 'pct': 41, 'group': '財務'},
    {'reason': '擔心技術尚不成熟', 'pct': 40, 'group': '未知'},
    {'reason': '維修保養不方便', 'pct': 40, 'group': '未知'},
    {'reason': '擔心行駛里程不夠使用', 'pct': 40, 'group': '基礎設施'},
    {'reason': '充電速度較慢', 'pct': 34, 'group': '基礎設施'},
    {'reason': '擔心保固不佳', 'pct': 20, 'group': '財務'},
    {'reason': '馬力不足', 'pct': 14, 'group': '未知'},
    {'reason': '擔心中古車價', 'pct': 9, 'group': '財務'},
    {'reason': '不安全', 'pct': 1, 'group': '未知'},
]
REASON_GROUP = {r['reason']: r['group'] for r in ANXIETY_REASONS}
REASON_PCT = {r['reason']: r['pct'] for r in ANXIETY_REASONS}

CLASSIFY_SYSTEM = (
    '你是幫忙把顧客對電動車的顧慮，對應到市調 12 類原因的助手。'
    '每一條顧慮都要從以下 12 個原因裡，選語意最接近的一個（不可以自己發明新的類別、不可以漏掉任何一條顧慮）：'
    + '、'.join(r['reason'] for r in ANXIETY_REASONS) + '。\n'
    '另外依整體語氣判斷顧慮的強烈程度（低／中／高）。\n'
    '每一輪都一定要呼叫 classify_concerns 這個工具來回覆，不可以直接輸出文字訊息。'
)

CLASSIFY_TOOL = {
    'name': 'classify_concerns',
    'description': '把每一條顧客顧慮分類到市調 12 類原因之一，並給出整體強度',
    'input_schema': {
        'type': 'object',
        'properties': {
            'items': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'concern_raw': {'type': 'string'},
                        'reason': {'type': 'string', 'enum': [r['reason'] for r in ANXIETY_REASONS]},
                    },
                    'required': ['concern_raw', 'reason'],
                },
            },
            'intensity': {'type': 'string', 'enum': ['低', '中', '高']},
        },
        'required': ['items', 'intensity'],
    },
}


def classify_concerns(concerns):
    """回傳 {ok, items:[{concern_raw, reason, group}], group（整體最主要歸類）, intensity}。
    每條顧慮對應哪個原因是 AI 判斷（語意分類，沒有公式可套）；
    但「哪個歸類最主要」是看對應結果用 Python 數 pct 加總，不是再問 AI 一次。
    """
    if not concerns:
        return {'ok': True, 'items': [], 'group': None, 'intensity': None}

    result = ask_claude_tool(
        CLASSIFY_SYSTEM,
        [{'role': 'user', 'content': json.dumps({'concerns': concerns}, ensure_ascii=False)}],
        CLASSIFY_TOOL,
    )
    if not result['ok']:
        return {'ok': False, 'error': result['error']}

    data = result['input']
    items = [
        {'concern_raw': it.get('concern_raw', ''), 'reason': it.get('reason'),
         'group': REASON_GROUP.get(it.get('reason'))}
        for it in data.get('items', [])
        if it.get('reason') in REASON_GROUP
    ]
    group_pct = {}
    for it in items:
        group_pct[it['group']] = group_pct.get(it['group'], 0) + REASON_PCT[it['reason']]
    overall_group = max(group_pct, key=group_pct.get) if group_pct else None

    return {'ok': True, 'items': items, 'group': overall_group, 'intensity': data.get('intensity')}


# 簡報 A3（CDP 分析）：bZ4X 車主平均年齡 50 歲。對話沒問年齡時，用這個當合理預設，
# 不是引擎亂猜的數字，而是這批車主本身的統計平均值。
AVG_OWNER_AGE = 50


@app.route('/api/radar', methods=['POST'])
def api_radar():
    body = request.get_json(silent=True) or {}
    concerns = body.get('concerns') or []

    classification = classify_concerns(concerns)
    if not classification['ok']:
        return jsonify({'ok': False, 'error': classification['error']})

    group = classification['group']
    evidence = None

    if group == '基礎設施':
        home_charging = body.get('homeCharging', 'wallbox')
        fuel_price = float(body.get('fuelPrice') or 30)
        home_elec_price = float(body.get('homeElecPrice') or 3)
        persona, _profile = _resolve_persona_and_profile(body)
        overnight_hours = persona.get('overnight_charge_hours', {})
        result = simulate_month(
            persona['schedule'],
            home_charging=home_charging,
            overnight_charge_hours=overnight_hours,
            params={
                'gas_km_per_l': persona['current_car']['fuel_km_per_l'],
                'gas_price_per_l': fuel_price,
                'home_elec_price': home_elec_price,
            },
        )
        evidence = {
            'type': 'infra',
            'green_days': result['green_days'],
            'yellow_days': result['yellow_days'],
            'red_days': result['red_days'],
            'total_km': result['total_km'],
        }
        # 顧客提到的如果是長途／極端天氣這類情境（原本獨立壓力測試情境在秀的東西，
        # 併掉改成這裡的證據），額外附上「這趟行程平常 vs 夏天打折」的對照。
        longest_normal = longest_trip_result(persona['schedule'], home_charging, overnight_hours)
        longest_derated = longest_trip_summer_derate_result(persona['schedule'], home_charging, overnight_hours)
        if longest_normal and longest_derated:
            evidence['longest_trip'] = {
                'km': longest_normal['days'][0]['km'],
                'activity': longest_normal['days'][0]['activity'],
                'normal_low_pct': longest_normal['days'][0]['low_pct'],
                'summer_derate_low_pct': longest_derated['days'][0]['low_pct'],
            }

    if group == '財務':
        profile = body.get('profile') or _default_profile()
        fuel_price = float(body.get('fuelPrice') or 30)
        home_elec_price = float(body.get('homeElecPrice') or 3)
        home_charging = profile.get('home_charging') or body.get('homeCharging', 'wallbox')
        cost5yr = cost_5yr(
            gas_km_per_l=profile.get('current_car_km_per_l') or C.GAS_KM_PER_L_DEFAULT,
            gas_price_per_l=fuel_price,
            home_elec_price=home_elec_price,
            home_charging=home_charging,
        )
        vehicle = load_json(DATA_DIR / 'vehicles' / 'bz4x.json')
        evidence = {
            'type': 'money',
            'cost5yr': cost5yr,
            'warranty': vehicle['warranty'],
            'warranty_source': vehicle['source'],
        }

    if group == '未知':
        profile = body.get('profile') or _default_profile()
        city = profile.get('city') or _default_profile().get('city')
        age = profile.get('age') or AVG_OWNER_AGE
        age_is_assumed = not profile.get('age')
        cdp = find_similar_owners(city, age)
        evidence = {
            'type': 'unknown',
            'cdp': cdp,
            'age_used': age,
            'age_is_assumed': age_is_assumed,
        }

    return jsonify({'ok': True, 'classification': classification, 'group': group, 'evidence': evidence})


def _next_saturday_10am(today=None):
    today = today or datetime.date.today()
    days_ahead = (5 - today.weekday()) % 7  # Saturday=5
    d = today + datetime.timedelta(days=days_ahead)
    weekday_label = '日一二三四五六'[(d.weekday() + 1) % 7]
    return f'{d.month}/{d.day}（{weekday_label}）10:00'


TALKING_POINTS_SYSTEM = (
    '你是幫 TOYOTA 業務準備跟催話術的助手。只能使用使用者訊息裡 JSON 給的數字與事實，'
    '不可以自己編造任何數字、優惠或承諾。寫 3 句話，每句一行、每句不超過 40 字，'
    '是業務可以直接對著顧客講的一句話（不是書面說明），針對顧客的顧慮對症下藥。'
    '繁體中文，不要加編號、不要加任何其他說明文字。'
)


@app.route('/api/summary', methods=['POST'])
def api_summary():
    body = request.get_json(silent=True) or {}
    profile = body.get('profile') or _default_profile()

    fit = _compute_fit_result(profile)
    classification = classify_concerns(profile.get('concerns_raw') or [])

    talking_points_payload = {
        'city': profile.get('city'),
        'commute_km_per_day': profile.get('commute_km_per_day'),
        'home_charging': profile.get('home_charging'),
        'fit_score': fit['score'],
        'fit_recommendation': fit['recommendation'],
        'fit_reasons': fit['reasons'],
        'concern_classification': classification.get('items', []),
    }
    talking_points = ask_claude(TALKING_POINTS_SYSTEM, json.dumps(talking_points_payload, ensure_ascii=False))

    return jsonify({
        'ok': True,
        'profile': {
            'city': profile.get('city') or '—',
            'housing': profile.get('housing') or '—',
            'home_charging': profile.get('home_charging') or '—',
            'commute_km_per_day': profile.get('commute_km_per_day') or 0,
        },
        'fit': fit,
        'classification': classification,
        'talking_points': talking_points,
        'test_drive_route': {
            'from': profile.get('city') or '顧客住家',
            'via': '鄰近公共充電站（示意）',
            'to': 'TOYOTA 展示中心',
            'note': '示意路線，非實際導航結果',
        },
        'appointment': _next_saturday_10am(),
    })


@app.route('/api/health')
def health():
    return jsonify({'ok': True, 'api_key_present': API_KEY_PRESENT, 'model': CLAUDE_MODEL})


if __name__ == '__main__':
    # 5000 在這台 Mac 會撞到 AirPlay 接收器，預設改 5050
    app.run(debug=True, port=int(os.environ.get('PORT', 5050)))
