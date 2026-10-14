"""所有情境呼叫 Claude API 共用的小包裝。

統一錯誤處理（SPEC.md §10 驗收項：「API 出錯時顯示清楚的錯誤訊息，不會整頁壞掉」）：
呼叫方一律拿到 {"ok": bool, "text" 或 "error"}，絕不會讓例外往上炸掉整個 request。
"""
import logging
import os

import anthropic

log = logging.getLogger('bz-demo')

CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-5-5')
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # 讀 ANTHROPIC_API_KEY 環境變數
    return _client


def ask_claude(system, user_text, max_tokens=1024):
    """回傳 {"ok": True, "text": str} 或 {"ok": False, "error": str}（給前端直接顯示的中文訊息）。"""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return {'ok': False, 'error': '伺服器沒有設定 ANTHROPIC_API_KEY，無法呼叫 AI。'}
    try:
        resp = _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{'role': 'user', 'content': user_text}],
        )
        text = ''.join(block.text for block in resp.content if block.type == 'text').strip()
        return {'ok': True, 'text': text}
    except anthropic.APIStatusError as e:
        log.warning('Claude API 錯誤 status=%s body=%s', e.status_code, e.body)
        return {'ok': False, 'error': f'AI 服務暫時出錯了（{e.status_code}），請稍後再試一次。'}
    except anthropic.APIConnectionError:
        log.warning('Claude API 連線失敗', exc_info=True)
        return {'ok': False, 'error': 'AI 服務連線失敗，請檢查網路後再試一次。'}
    except Exception:
        log.exception('呼叫 Claude 時發生未預期錯誤')
        return {'ok': False, 'error': 'AI 回覆時發生未預期的錯誤，請稍後再試一次。'}


def ask_claude_tool(system, messages, tool, max_tokens=1024):
    """強制呼叫一個 tool，拿結構化 JSON 回來（比要求 AI「只回傳 JSON」可靠很多）。
    回傳 {"ok": True, "input": dict} 或 {"ok": False, "error": str}。
    """
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return {'ok': False, 'error': '伺服器沒有設定 ANTHROPIC_API_KEY，無法呼叫 AI。'}
    try:
        resp = _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=[tool],
            tool_choice={'type': 'auto'},  # 這個模型不支援強制指定 tool，只能用 auto + 在 system prompt 裡強調一定要呼叫
        )
        tool_use = next((b for b in resp.content if b.type == 'tool_use'), None)
        if not tool_use:
            return {'ok': False, 'error': 'AI 沒有回傳預期的結構化資料，請再試一次。'}
        return {'ok': True, 'input': tool_use.input}
    except anthropic.APIStatusError as e:
        log.warning('Claude API 錯誤 status=%s body=%s', e.status_code, e.body)
        return {'ok': False, 'error': f'AI 服務暫時出錯了（{e.status_code}），請稍後再試一次。'}
    except anthropic.APIConnectionError:
        log.warning('Claude API 連線失敗', exc_info=True)
        return {'ok': False, 'error': 'AI 服務連線失敗，請檢查網路後再試一次。'}
    except Exception:
        log.exception('呼叫 Claude 時發生未預期錯誤')
        return {'ok': False, 'error': 'AI 回覆時發生未預期的錯誤，請稍後再試一次。'}
