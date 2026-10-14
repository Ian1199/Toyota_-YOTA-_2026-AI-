# 電量Yota顧｜Demo

TOYOTA bZ4X 油轉電 AI 顧問的互動 Demo。完整規格見 `../SPEC.md`。

左側面板切換 6 個情境，右側是 iPhone（情境 6 是 iPad 橫式）。**數字一律由
`engine/` 底下的純函式算出來，Claude 只負責對話、分類、把數字講成人話**——
AI 不會自己編里程、電量、金額或車主統計。

## 安裝

```bash
cd demo
python3 -m venv ../.venv        # 已經建立過就跳過這行
source ../.venv/bin/activate
pip install -r requirements.txt
```

## 設定 .env

```bash
cp .env.example .env
```

打開 `.env`，把 `ANTHROPIC_API_KEY` 換成你自己的金鑰（去
[console.anthropic.com](https://console.anthropic.com) 申請）。`CLAUDE_MODEL`
預設是 `claude-sonnet-5`，不確定自己的帳號能不能用這個模型的話，先跑：

```bash
python3 -c "
import os
from dotenv import load_dotenv; load_dotenv()
import anthropic
c = anthropic.Anthropic()
r = c.messages.create(model=os.environ['CLAUDE_MODEL'], max_tokens=20,
                       messages=[{'role':'user','content':'hi'}])
print(r.content)
"
```

沒報錯就代表金鑰跟模型都能用。

## 啟動

```bash
python3 app.py
```

預設開在 `http://localhost:5050`（故意不用 5000，macOS 的 AirPlay 接收器會佔
用那個 port）。想換 port 就在 `.env` 裡設 `PORT=xxxx`，或啟動前
`export PORT=xxxx`。

打開網頁後，左側「情境」依序點 01-07 就能看完整個流程；左側「狀態」欄的
住家充電／油價／家用電價改了之後，月曆、適配度、持有成本、焦慮雷達的證據卡
都會跟著重算。「重置」會把這些設定和情境 2 的對話紀錄都清掉，回到剛打開網
頁的狀態。

## 跑測試

```bash
python3 -m pytest engine/tests/ -v
```

這些測試直接對照 `SPEC.md` §7.4 列出的期望值寫的，涵蓋逐日電量模擬、適配度
評分、5 年持有成本、CDP 相似車主查詢、行程組裝、最長一趟行程的平常／夏天打折
對照。改動 `engine/` 底下任何計算邏輯後，先確認這組測試全過再動 `app.py`。

## 專案結構

```
demo/
├── app.py                 Flask 路由；串 engine/ 的計算結果跟 Claude API
├── claude_client.py        呼叫 Claude 的共用包裝（統一錯誤處理、工具呼叫）
├── engine/                 純函式計算引擎，不碰 Claude、不碰網路
│   ├── constants.py         所有引擎參數（電池容量、電效、城市里程表…）
│   ├── simulate.py          逐日電量模擬（情境 4 共用）
│   ├── fit_score.py         適配度評分規則（情境 3）
│   ├── cost.py               5 年持有成本（情境 4、5）
│   ├── cdp.py                 CDP 相似車主查詢（情境 5），讀 ../../TOYOTA EV新生活 競賽數據/
│   ├── itinerary.py           把情境 2 對話組出的 profile 轉成逐日行程
│   ├── stress.py               最長一趟行程的平常／夏天打折對照，被適配度評分
│   │                           跟焦慮雷達（情境 5）共用，不是獨立情境
│   └── tests/                 對應上面每個模組的 pytest
├── data/
│   ├── personas/chen.json    陳先生——「範例資料」，不是唯一資料來源
│   └── vehicles/bz4x.json    bZ4X 規格（型錄數字）
├── templates/index.html
└── static/{style.css,app.js}
```

**關於「範例資料」**：`chen.json` 只是情境 2 對話還沒做完之前的預設顯示，
不是寫死的唯一資料來源。情境 2 問完之後，情境 3/4/6/7 讀的是真的從對話抽出
來、現場組出行程、現場算出來的結果（左側「顧客」欄位文字會從「示範資料」
變成「由對話建立」）；任何符合 `engine/itinerary.py` 輸入格式的 profile 都
能直接餵給整套引擎跑，不綁死特定一個人。

## 兩層假設都有標示

- **型錄/引擎假設**（電效打 75 折、快充速率、城市間距離簡表）在畫面上都有
  「試算依據」「示意」字樣標出來，`engine/constants.py` 裡每個數字也都寫了
  來源或理由。
- **對話沒問到的欄位**（例如年齡、長途目的地能不能充電）用有憑有據的預設值
  頂著（例如 CDP 車主平均年齡 50 歲），畫面上會註明「先用…估算」，不會假
  裝那是顧客自己講的。

## 關於多車款

`engine/simulate.py`、`cost.py`、`fit_score.py` 的電池容量／電效都能透過
`params`／函式參數覆寫，不是寫死只能算 bZ4X。但目前 `app.py` 還是固定讀
`data/vehicles/bz4x.json` 只為了拿保固文字（情境 5 的財務證據卡），沒有接
「依車款切換引擎參數」的邏輯——比賽範圍本來就只有 bZ4X 一款車，這段還沒
寫、也還沒有第二款車的真實數據可以驗證，所以沒有先做。真的要加新車款時，
除了新增 `data/vehicles/*.json`，還要在 `app.py` 把對應的
`battery_kwh`／`efficiency_km_per_kwh` 傳進上面那三個函式的覆寫參數。

## 已知限制

- 比賽資料夾裡 104 萬筆的全車系 CDP 檔案沒有用到：疑似在匯出時被截在 Excel
  的 104 萬列上限，而且兩個檔案的「編號」都只是各自檔案內的流水號，沒辦法
  跨檔案串回同一個顧客，所以只用 3,037 筆 bZ4X 專屬補充資料檔。
- 花東三天兩夜（情境 5）的城市間里程是概估值，不是實際導航距離。

## 關於比賽提供的 CDP 資料（沒有放進這個 repo）

`engine/cdp.py` 讀的是 `../../TOYOTA EV新生活 競賽數據/` 底下兩個 CSV（和一份
品牌調查 PDF）——這是黑客松主辦方（和泰汽車）提供的真實車主去個資化資料，
屬於比賽限定、不公開散布的資料，所以**沒有**包含在這個公開 repo 裡。少了這
個資料夾，情境 5（焦慮雷達 × 車主反饋）會因為讀不到檔案而噴錯；其他情境都
不受影響。有合法取得這份比賽資料的人，把資料夾放在跟 `demo/` 同一層（也就是
`demo/` 的上一層）就能跑完整功能。
