/* 電量Yota顧 Demo —— 左側情境切換 + 狀態面板；每個情境在 SCENARIO_RENDERERS 登記一個 render 函式 */
(function () {
  'use strict';

  var screenBody = document.getElementById('screenBody');
  var ipadBody = document.getElementById('ipadScreenBody');
  var deviceIphone = document.getElementById('deviceIphone');
  var deviceIpad = document.getElementById('deviceIpad');
  var iphoneScreen = deviceIphone.querySelector('.screen');
  var scenarioList = document.getElementById('scenarioList');
  var resetBtn = document.getElementById('resetBtn');
  var homeChargingSel = document.getElementById('homeCharging');
  var fuelPriceInput = document.getElementById('fuelPrice');
  var homeElecPriceInput = document.getElementById('homeElecPrice');

  // { renderAsync(state, target, isStale), device: 'iphone'|'ipad', dark: bool }
  var SCENARIO_RENDERERS = {};

  var STATE = {
    homeCharging: homeChargingSel.value,
    fuelPrice: Number(fuelPriceInput.value),
    homeElecPrice: Number(homeElecPriceInput.value),
    persona: window.__INITIAL__.persona,
    claudeModel: window.__INITIAL__.claudeModel,
    // 情境 2 的對話狀態；問完之後 liveProfile 會被情境 4/3 拿去真的算數字，不是永遠讀 persona 範例
    chat: { history: [], profile: {}, done: false, waiting: false, quickReplies: [] },
    liveProfile: null,
  };

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function fmt(n) { return Number(n).toLocaleString('zh-Hant'); }
  function dayColorClass(color) { return color === 'green' ? 'cal-home' : color === 'yellow' ? 'cal-dc' : 'cal-low'; }
  function placeholder(text) { return '<p class="screen-placeholder">' + esc(text) + '</p>'; }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); });
  }

  // 共用的「載入中 → 成功渲染／失敗訊息」流程
  function loadInto(target, isStale, url, body, onData) {
    target.innerHTML = placeholder('計算中');
    postJson(url, body)
      .then(function (data) {
        if (isStale()) return;
        if (!data.ok) { target.innerHTML = placeholder('載入失敗：' + (data.error || '未知錯誤')); return; }
        onData(data);
      })
      .catch(function (err) {
        if (isStale()) return;
        target.innerHTML = placeholder('載入失敗：' + String(err));
      });
  }

  function currentScenario() {
    var btn = scenarioList.querySelector('[aria-current="true"]');
    return btn ? btn.dataset.scenario : null;
  }

  var renderToken = 0;

  function renderScenario(id) {
    scenarioList.querySelectorAll('.scenario-btn').forEach(function (b) {
      b.setAttribute('aria-current', b.dataset.scenario === id ? 'true' : 'false');
    });

    var entry = SCENARIO_RENDERERS[id];
    var useIpad = entry && entry.device === 'ipad';
    deviceIphone.classList.toggle('active', !useIpad);
    deviceIpad.classList.toggle('active', !!useIpad);
    iphoneScreen.classList.toggle('dark', !!(entry && entry.dark));

    var target = useIpad ? ipadBody : screenBody;
    var myToken = ++renderToken;
    function isStale() { return myToken !== renderToken; }

    if (entry) entry.renderAsync(STATE, target, isStale);
    else target.innerHTML = placeholder('尚未完成');

    target.classList.remove('fade-in');
    void target.offsetWidth; // 重新觸發動畫
    target.classList.add('fade-in');
  }

  scenarioList.addEventListener('click', function (e) {
    var btn = e.target.closest('.scenario-btn');
    if (!btn || btn.disabled) return;
    renderScenario(btn.dataset.scenario);
  });

  function onStateChange() {
    STATE.homeCharging = homeChargingSel.value;
    STATE.fuelPrice = Number(fuelPriceInput.value) || 0;
    STATE.homeElecPrice = Number(homeElecPriceInput.value) || 0;
    var cur = currentScenario();
    if (cur) renderScenario(cur);
  }
  homeChargingSel.addEventListener('change', onStateChange);
  fuelPriceInput.addEventListener('input', onStateChange);
  homeElecPriceInput.addEventListener('input', onStateChange);

  function setStatusCustomer(text, isSample) {
    document.getElementById('statusCustomer').textContent = text;
    document.getElementById('statusCustomerTag').hidden = !isSample;
  }

  resetBtn.addEventListener('click', function () {
    homeChargingSel.value = 'wallbox';
    fuelPriceInput.value = 30;
    homeElecPriceInput.value = 3;

    // 整個 demo 回到剛打開網頁的狀態：對話、對話組出的 profile、面板上的顧客/適配度顯示都清空
    STATE.chat = { history: [], profile: {}, done: false, waiting: false, quickReplies: [] };
    STATE.liveProfile = null;
    setStatusCustomer(STATE.persona.name + ' · ' + STATE.persona.city, true);
    document.getElementById('fitScoreDisplay').textContent = '—';

    onStateChange();
    renderScenario(scenarioList.querySelector('.scenario-btn').dataset.scenario);
  });

  var ICON_ARROW_UP = '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>';
  var ICON_BOLT = '<svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>';

  // ---------- 情境 1：回廠推播（鎖定畫面） ----------
  (function () {
    var clockInterval = null;

    function pad2(n) { return n < 10 ? '0' + n : String(n); }

    function updateClock(target) {
      var timeEl = target.querySelector('#lockClock');
      var dateEl = target.querySelector('#lockDate');
      if (!timeEl) { clearInterval(clockInterval); return; }
      var now = new Date();
      timeEl.textContent = now.getHours() + ':' + pad2(now.getMinutes());
      var weekday = ['日', '一', '二', '三', '四', '五', '六'][now.getDay()];
      dateEl.textContent = (now.getMonth() + 1) + '月' + now.getDate() + '日 星期' + weekday;
    }

    SCENARIO_RENDERERS.push = {
      dark: true,
      renderAsync: function (state, target) {
        if (clockInterval) clearInterval(clockInterval);
        target.innerHTML =
          '<div class="scn-lock">' +
            '<div class="lock-date" id="lockDate"></div>' +
            '<div class="lock-time" id="lockClock">--:--</div>' +
            '<button type="button" class="lock-notif" id="lockNotifBtn">' +
              '<span class="lock-notif-icon">' + ICON_BOLT + '</span>' +
              '<span class="lock-notif-body">' +
                '<span class="lock-notif-head">TOYOTA<span>現在</span></span>' +
                '<span class="lock-notif-text">保養快到期，順便預演 bZ4X 的一個月？</span>' +
              '</span>' +
            '</button>' +
          '</div>';
        updateClock(target);
        clockInterval = setInterval(function () { updateClock(target); }, 1000);
        target.querySelector('#lockNotifBtn').addEventListener('click', function () {
          clearInterval(clockInterval);
          renderScenario('chat');
        });
      },
    };
  })();

  // ---------- 情境 2：對話診斷 ----------
  (function () {
    function bubbleHtml(role, text) {
      return '<div class="chat-bubble ' + (role === 'user' ? 'chat-user' : 'chat-ai') + '">' + esc(text) + '</div>';
    }

    function renderChatScreen(target) {
      var msgsHtml = STATE.chat.history.map(function (h) { return bubbleHtml(h.role, h.text); }).join('');
      if (STATE.chat.waiting) msgsHtml += '<div class="chat-bubble chat-ai chat-typing"><span></span><span></span><span></span></div>';

      var belowHtml = '';
      if (!STATE.chat.waiting) {
        if (STATE.chat.done) {
          var hasConcerns = (STATE.chat.profile.concerns_raw || []).length > 0;
          belowHtml = '<div class="chat-done">' +
            '<button type="button" class="btn-primary btn-block" id="chatGoFit">看適配度</button>' +
            (hasConcerns ? '<button type="button" class="btn-secondary btn-block" id="chatGoRadar">深入看我擔心的地方</button>' : '') +
            '</div>';
        } else if (STATE.chat.quickReplies.length) {
          belowHtml = '<div class="chat-quickreplies">' + STATE.chat.quickReplies.map(function (q) {
            return '<button type="button" class="chat-qr-btn" data-qr="' + esc(q) + '">' + esc(q) + '</button>';
          }).join('') + '</div>';
        }
      }

      var disabled = STATE.chat.waiting || STATE.chat.done ? ' disabled' : '';
      target.innerHTML =
        '<div class="scn-chat">' +
          '<div class="chat-header"><span class="chat-avatar"></span><b>電車顧問</b></div>' +
          '<div class="chat-messages" id="chatMessages">' + msgsHtml + '</div>' +
          belowHtml +
          '<div class="chat-inputbar">' +
            '<input type="text" id="chatInput" placeholder="訊息"' + disabled + '>' +
            '<button type="button" class="chat-send" id="chatSend" aria-label="送出"' + disabled + '>' + ICON_ARROW_UP + '</button>' +
          '</div>' +
        '</div>';

      var messagesEl = target.querySelector('#chatMessages');
      messagesEl.scrollTop = messagesEl.scrollHeight;

      target.querySelectorAll('.chat-qr-btn').forEach(function (b) {
        b.addEventListener('click', function () { sendChat(b.dataset.qr, target); });
      });
      var input = target.querySelector('#chatInput');
      function doSend() {
        var v = input.value.trim();
        if (v) sendChat(v, target);
      }
      target.querySelector('#chatSend').addEventListener('click', doSend);
      input.addEventListener('keydown', function (e) { if (e.key === 'Enter') doSend(); });

      var goFit = target.querySelector('#chatGoFit');
      if (goFit) goFit.addEventListener('click', function () { renderScenario('fit'); });
      var goRadar = target.querySelector('#chatGoRadar');
      if (goRadar) goRadar.addEventListener('click', function () { renderScenario('radar'); });
    }

    function afterReply(target, data) {
      STATE.chat.waiting = false;
      if (!data.ok) {
        STATE.chat.history.push({ role: 'assistant', text: '（暫時無法回覆：' + data.error + '）' });
        renderChatScreen(target);
        return;
      }
      STATE.chat.history.push({ role: 'assistant', text: data.reply });
      STATE.chat.profile = Object.assign({}, STATE.chat.profile, data.profile);
      STATE.chat.done = !!data.done;
      STATE.chat.quickReplies = data.quick_replies || [];
      if (STATE.chat.done) {
        STATE.liveProfile = STATE.chat.profile;
        setStatusCustomer('您 · ' + (STATE.liveProfile.city || '—'), false);
      }
      renderChatScreen(target);
    }

    function requestReply(target) {
      postJson('/api/chat', { history: STATE.chat.history })
        .then(function (data) { afterReply(target, data); })
        .catch(function (err) { afterReply(target, { ok: false, error: String(err) }); });
    }

    function sendChat(text, target) {
      STATE.chat.history.push({ role: 'user', text: text });
      STATE.chat.waiting = true;
      STATE.chat.quickReplies = [];
      renderChatScreen(target);
      requestReply(target);
    }

    SCENARIO_RENDERERS.chat = {
      renderAsync: function (state, target) {
        if (STATE.chat.history.length === 0 && !STATE.chat.waiting) {
          STATE.chat.waiting = true;
          renderChatScreen(target);
          requestReply(target);
          return;
        }
        renderChatScreen(target);
      },
    };
  })();

  // ---------- 情境 3：適配度 ----------
  (function () {
    // 引擎原始理由像「家裡只有一般插座，沒有充電樁（−10）」：把扣分拆到右側，文字比 AI 改寫版短
    function reasonRow(r) {
      var m = /（([−-]\d+)）$/.exec(r);
      if (!m) return '<li><span>' + esc(r) + '</span></li>';
      return '<li><span>' + esc(r.slice(0, m.index)) + '</span><b class="neg">' + m[1] + '</b></li>';
    }

    function renderFitScreen(target, data) {
      var reasons = data.raw_reasons || data.reasons;
      target.innerHTML =
        '<div class="page">' +
          '<div class="fit-hero">' +
            '<span class="label">適配度' + (STATE.liveProfile ? '' : '　<span class="tag">示範</span>') + '</span>' +
            '<div class="big-num">' + data.score + '<small>/ 100</small></div>' +
            '<span class="tag accent">' + esc(data.recommendation) + '</span>' +
          '</div>' +
          '<div class="section">' +
            '<span class="label">依據</span>' +
            '<ul class="list fit-reasons">' + reasons.map(reasonRow).join('') +
              '<li><span>實際續航（估）</span><b>' + data.actual_range_km + ' km</b></li>' +
            '</ul>' +
          '</div>' +
          '<button type="button" class="btn-primary btn-block" id="fitGoCalendar">預演一個月</button>' +
        '</div>';
      target.querySelector('#fitGoCalendar').addEventListener('click', function () { renderScenario('calendar'); });
      document.getElementById('fitScoreDisplay').textContent = data.score + ' 分';
    }

    SCENARIO_RENDERERS.fit = {
      renderAsync: function (state, target, isStale) {
        loadInto(target, isStale, '/api/fit', { profile: STATE.liveProfile }, function (data) {
          renderFitScreen(target, data);
        });
      },
    };
  })();

  // ---------- 情境 4：電車月曆 ----------
  (function () {
    var DOW = ['日', '一', '二', '三', '四', '五', '六'];

    function dayDetailHtml(d) {
      var rows = [
        ['里程', fmt(d.km) + ' km'],
        ['電量', d.start_pct + '% → ' + d.low_pct + '% → ' + d.end_pct + '%'],
      ];
      if (d.dc_min > 0) rows.push(['快充', d.dc_min + ' 分 · ' + d.dc_kwh + ' kWh']);
      if (d.ac_kwh > 0) rows.push(['夜充', d.ac_kwh + ' kWh']);
      return (
        '<div class="cal-detail-title">' + esc(d.date.slice(5).replace('-', '/')) + '　' + esc(d.activity) + '</div>' +
        '<ul class="list">' + rows.map(function (r) { return '<li>' + r[0] + '<b>' + r[1] + '</b></li>'; }).join('') + '</ul>'
      );
    }

    function buildCalendarHtml(data) {
      var cal = data.calendar;
      var c = data.cost5yr;
      var cells = [];
      for (var i = 0; i < data.first_weekday; i++) cells.push('<div></div>');
      cal.days.forEach(function (d) {
        cells.push(
          '<button type="button" class="cal-cell ' + dayColorClass(d.color) + '" data-date="' + d.date + '">' +
          Number(d.date.slice(-2)) + '</button>'
        );
      });

      var diaryBlock = data.diary.ok
        ? '<p class="diary">' + esc(data.diary.text) + '</p>'
        : '<p class="diary err">日記暫時無法產生</p>';

      return (
        '<div class="page">' +
          '<div class="cal-head">' +
            '<div class="stat"><span class="lbl">電不夠</span><div class="big-num">' + cal.red_days + '<small>天</small></div></div>' +
            '<div class="stat-row">' +
              '<div class="stat"><span class="num">' + cal.green_days + '</span><span class="lbl">在家充</span></div>' +
              '<div class="stat"><span class="num">$' + fmt(cal.save_ntd) + '</span><span class="lbl">本月省</span></div>' +
            '</div>' +
          '</div>' +
          '<div class="section">' +
            '<div class="cal-grid">' +
              DOW.map(function (w) { return '<div class="cal-dow">' + w + '</div>'; }).join('') +
              cells.join('') +
            '</div>' +
            '<div class="cal-legend">' +
              '<span><i class="dot cal-home"></i>在家</span>' +
              '<span><i class="dot cal-dc"></i>快充</span>' +
              '<span><i class="dot cal-low"></i>不足</span>' +
            '</div>' +
          '</div>' +
          '<div class="cal-detail" id="calDetail" hidden></div>' +
          '<div class="section"><span class="label">日記</span>' + diaryBlock + '</div>' +
          '<div class="section"><span class="label">5 年能源費（估）</span>' +
            '<ul class="list">' +
              '<li>油車<b>$' + fmt(c.gas_energy_cost) + '</b></li>' +
              '<li>bZ4X<b>$' + fmt(c.ev_energy_cost) + '</b></li>' +
              '<li class="total">省下<b>$' + fmt(c.save_energy_only) + '</b></li>' +
            '</ul>' +
          '</div>' +
          '<p class="footnote">' + esc(data.assumptions) + '</p>' +
        '</div>'
      );
    }

    function wireDayClicks(target, cal) {
      var detail = target.querySelector('#calDetail');
      target.querySelectorAll('.cal-cell[data-date]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var day = cal.days.find(function (d) { return d.date === btn.dataset.date; });
          var already = target.querySelector('.cal-cell.selected');
          if (already) already.classList.remove('selected');
          if (already === btn) { detail.hidden = true; return; }
          btn.classList.add('selected');
          detail.innerHTML = dayDetailHtml(day);
          detail.hidden = false;
        });
      });
    }

    SCENARIO_RENDERERS.calendar = {
      renderAsync: function (state, target, isStale) {
        loadInto(target, isStale, '/api/calendar', {
          homeCharging: state.homeCharging,
          fuelPrice: state.fuelPrice,
          homeElecPrice: state.homeElecPrice,
          profile: STATE.liveProfile,
        }, function (data) {
          target.innerHTML = buildCalendarHtml(data);
          wireDayClicks(target, data.calendar);
        });
      },
    };
  })();

  // ---------- 情境 5／6 共用：顧慮分類 ----------
  var GROUP_CLASS = { '基礎設施': 'grp-infra', '財務': 'grp-money', '未知': 'grp-unknown' };

  function concernsHtml(classification) {
    if (!classification.items.length) return '<p class="footnote">沒有偵測到具體顧慮</p>';
    return '<ul class="list concerns">' + classification.items.map(function (it) {
      return (
        '<li>' +
          '<span class="q">' + esc(it.concern_raw) + '</span>' +
          '<span class="tags"><span class="tag ' + (GROUP_CLASS[it.group] || '') + '">' + esc(it.reason) + '</span>' +
          '<span class="tag">' + esc(it.group) + '</span></span>' +
        '</li>'
      );
    }).join('') + '</ul>';
  }

  // ---------- 情境 5：焦慮雷達 ----------
  (function () {
    function defaultConcernsText() {
      var arr = (STATE.liveProfile && STATE.liveProfile.concerns_raw && STATE.liveProfile.concerns_raw.length)
        ? STATE.liveProfile.concerns_raw
        : (STATE.persona.concerns_raw || []);
      return arr.join('\n');
    }

    function evidenceHtml(ev) {
      if (!ev) return '';
      if (ev.type === 'infra') {
        var lt = ev.longest_trip;
        return (
          '<div class="section"><span class="label">證據 · 本月月曆</span>' +
            '<div class="big-num">' + ev.red_days + '<small>天電不夠</small></div>' +
            '<div class="stat-row">' +
              '<div class="stat"><span class="num">' + ev.green_days + '</span><span class="lbl">在家充</span></div>' +
              '<div class="stat"><span class="num">' + ev.yellow_days + '</span><span class="lbl">快充</span></div>' +
              '<div class="stat"><span class="num">' + fmt(ev.total_km) + '</span><span class="lbl">km</span></div>' +
            '</div>' +
          '</div>' +
          (lt ? (
            '<div class="section"><span class="label">最長一趟 · ' + esc(lt.activity) + '（' + fmt(lt.km) + ' km）</span>' +
              '<ul class="list">' +
                '<li>平常電效<b>剩 ' + lt.normal_low_pct + '%</b></li>' +
                '<li>夏天塞車開冷氣（電效打 85 折）<b>剩 ' + lt.summer_derate_low_pct + '%</b></li>' +
              '</ul>' +
            '</div>'
          ) : '')
        );
      }
      if (ev.type === 'money') {
        var c = ev.cost5yr;
        return (
          '<div class="section"><span class="label">證據 · 5 年能源費（估）</span>' +
            '<ul class="list">' +
              '<li>油車<b>$' + fmt(c.gas_energy_cost) + '</b></li>' +
              '<li>bZ4X<b>$' + fmt(c.ev_energy_cost) + '</b></li>' +
              '<li class="total">省下<b>$' + fmt(c.save_energy_only) + '</b></li>' +
              '<li>保固<b>' + esc(ev.warranty) + '</b></li>' +
            '</ul>' +
            '<p class="footnote">來源：' + esc(ev.warranty_source) + '</p>' +
          '</div>'
        );
      }
      if (ev.type === 'unknown') {
        var cdp = ev.cdp;
        return (
          '<div class="section"><span class="label">證據 · 相似車主</span>' +
            '<div class="kv">' +
              '<div class="stat"><span class="num">' + cdp.count + '</span><span class="lbl">車主數</span></div>' +
              '<div class="stat"><span class="num">' + (cdp.median_visits_any == null ? '—' : cdp.median_visits_any) + '</span><span class="lbl">年回廠</span></div>' +
              '<div class="stat"><span class="num">' + (cdp.median_visits_paid_service == null ? '—' : cdp.median_visits_paid_service) + '</span><span class="lbl">年定保</span></div>' +
            '</div>' +
            '<p class="footnote">' + esc(cdp.basis) + (ev.age_is_assumed ? '（年齡假設 ' + ev.age_used + '）' : '') + ' · ' + esc(cdp.source) + '</p>' +
          '</div>'
        );
      }
      return '';
    }

    function analyze(target) {
      var concerns = target.querySelector('#radarInput').value
        .split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
      var resultEl = target.querySelector('#radarResult');
      resultEl.innerHTML = placeholder('分析中');

      postJson('/api/radar', {
        concerns: concerns,
        profile: STATE.liveProfile,
        homeCharging: STATE.homeCharging,
        fuelPrice: STATE.fuelPrice,
        homeElecPrice: STATE.homeElecPrice,
      })
        .then(function (data) {
          if (!data.ok) { resultEl.innerHTML = placeholder('載入失敗：' + data.error); return; }
          resultEl.innerHTML =
            '<div class="section"><span class="label">歸類' +
              (data.classification.intensity ? '　<span class="tag">強度 ' + esc(data.classification.intensity) + '</span>' : '') +
            '</span>' + concernsHtml(data.classification) + '</div>' +
            evidenceHtml(data.evidence);
        })
        .catch(function (err) { resultEl.innerHTML = placeholder('載入失敗：' + String(err)); });
    }

    SCENARIO_RENDERERS.radar = {
      renderAsync: function (state, target) {
        target.innerHTML =
          '<div class="page">' +
            '<h2 class="page-title">焦慮雷達</h2>' +
            '<div class="section">' +
              '<textarea id="radarInput" class="radar-textarea" rows="3" aria-label="顧客顧慮">' + esc(defaultConcernsText()) + '</textarea>' +
              '<button type="button" class="btn-primary btn-block" id="radarAnalyze">分析</button>' +
            '</div>' +
            '<div class="stack" id="radarResult"></div>' +
          '</div>';
        target.querySelector('#radarAnalyze').addEventListener('click', function () { analyze(target); });
        analyze(target);
      },
    };
  })();

  // ---------- 情境 6：業務摘要卡（iPad 橫式） ----------
  (function () {
    var CHARGING_LABEL = { wallbox: '充電樁', outlet: '一般插座', none: '無法充電' };

    function stat(label, value) {
      return '<div class="stat"><span class="lbl">' + label + '</span><span class="num">' + esc(value) + '</span></div>';
    }

    function buildSummaryHtml(data) {
      var p = data.profile;
      var r = data.test_drive_route;

      var talkHtml = data.talking_points.ok
        ? '<ol class="talk-list">' + data.talking_points.text.split('\n').filter(function (l) { return l.trim(); })
            .map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ol>'
        : '<p class="footnote">話術暫時無法產生</p>';

      return (
        '<div class="scn-summary">' +
          '<div class="summary-col">' +
            '<div class="panel-card">' +
              '<span class="label">顧客</span>' +
              '<div class="kv-2">' +
                stat('縣市', p.city) +
                stat('住家', p.housing) +
                stat('充電', CHARGING_LABEL[p.home_charging] || p.home_charging) +
                stat('日通勤', p.commute_km_per_day + ' km') +
              '</div>' +
            '</div>' +
            '<div class="panel-card">' +
              '<span class="label">顧慮' +
                (data.classification.intensity ? '　<span class="tag">強度 ' + esc(data.classification.intensity) + '</span>' : '') +
              '</span>' +
              concernsHtml(data.classification) +
            '</div>' +
            '<div class="panel-card"><span class="label">話術</span>' + talkHtml + '</div>' +
          '</div>' +
          '<div class="summary-col">' +
            '<div class="panel-card">' +
              '<span class="label">適配度</span>' +
              '<div class="fit-mini">' +
                '<div class="big-num">' + data.fit.score + '<small>/ 100</small></div>' +
                '<span class="tag accent">' + esc(data.fit.recommendation) + '</span>' +
              '</div>' +
            '</div>' +
            '<div class="panel-card">' +
              '<span class="label">試駕路線　<span class="tag">示意</span></span>' +
              '<div class="route">' +
                '<span class="route-node"><i></i>' + esc(r.from) + '</span>' +
                '<span class="route-line"></span>' +
                '<span class="route-node charge"><i></i>充電站</span>' +
                '<span class="route-line"></span>' +
                '<span class="route-node"><i></i>展示中心</span>' +
              '</div>' +
            '</div>' +
            '<div class="panel-card">' +
              '<span class="label">試乘預約　<span class="tag">示意</span></span>' +
              '<div class="appt">' + esc(data.appointment) + '</div>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    }

    SCENARIO_RENDERERS.summary = {
      device: 'ipad',
      renderAsync: function (state, target, isStale) {
        loadInto(target, isStale, '/api/summary', { profile: STATE.liveProfile }, function (data) {
          target.innerHTML = buildSummaryHtml(data);
        });
      },
    };
  })();

  var first = scenarioList.querySelector('.scenario-btn');
  if (first) renderScenario(first.dataset.scenario);

  window.__bz = { SCENARIO_RENDERERS: SCENARIO_RENDERERS, STATE: STATE, renderScenario: renderScenario };
})();
