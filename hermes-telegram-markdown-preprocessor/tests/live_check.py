"""Live check against Telegram's own parser: every case is normalized, sent with sendRichMessage
(silent) to CHAT_ID and deleted at once. Usage: TELEGRAM_BOT_TOKEN=... CHAT_ID=... python tests/live_check.py"""
import json, os, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tgmd

TOKEN, CHAT = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["CHAT_ID"]


def api(method, payload):
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def parse(md):
    r = api("sendRichMessage", {"chat_id": CHAT, "rich_message": {"markdown": md}, "disable_notification": True})
    if not r.get("ok"):
        return {"error": r.get("description")}
    api("deleteMessage", {"chat_id": CHAT, "message_id": r["result"]["message_id"]})
    time.sleep(0.4)
    return r["result"].get("rich_message") or {}


def types(rm): return [b["type"] for b in rm.get("blocks", [])] if "error" not in rm else ["ERROR:" + rm["error"]]
def flat(rm): return json.dumps(rm, ensure_ascii=False)


EXPECT = {
 "table_no_blank_before": lambda r: types(r) == ['paragraph', 'table'],
 "table_col_mismatch": lambda r: types(r) == ['table'],
 "setext_dash": lambda r: types(r) == ['paragraph', 'divider', 'paragraph'],
 "olist_after_para_not1": lambda r: types(r) == ['paragraph', 'list'],
 "quote_lazy": lambda r: types(r) == ['blockquote', 'paragraph'],
 "code_unclosed": lambda r: types(r) == ['paragraph', 'pre'] and r['blocks'][1]['text'].strip() == 'ls -la',
 "underscore_ident": lambda r: '__init__' in flat(r) and '"bold"' not in flat(r),
 "star_math": lambda r: 'italic' not in flat(r) .split('a"')[0] and '5 * 3 * 2' in flat(r),
 "bold_then_table": lambda r: types(r) == ['paragraph', 'table'],
 "list_then_text": lambda r: types(r) == ['list', 'paragraph'],
 "table_after_list_item": lambda r: types(r) == ['list', 'table'],
 "quote_then_list": lambda r: types(r) == ['blockquote', 'list'],
 "dash_line_after_list": lambda r: types(r) == ['list', 'divider', 'paragraph'],
 "placeholder_plain": lambda r: '<pod>' in flat(r) and '<namespace>' in flat(r),
 "generic_types": lambda r: 'List<String>' in flat(r),
 "lt_in_table": lambda r: '<id>' in flat(r),
 "tilde_fence": lambda r: types(r) == ['pre'] and r['blocks'][0]['text'] == 'code',
 "hash_issue": lambda r: types(r) == ['paragraph'] and '#89' in flat(r),
 # must stay as they were
 "heading_after_text": lambda r: types(r) == ['paragraph', 'heading', 'paragraph'],
 "tags_known": lambda r: '"bold"' in flat(r) and '"spoiler"' in flat(r),
 "email_like": lambda r: 'email_address' in flat(r),
 "link_parens": lambda r: 'Foo_(bar)' in flat(r),
 "details": lambda r: types(r) == ['details'],
 "math_inline": lambda r: 'mathematical_expression' in flat(r),
 "checkbox": lambda r: 'has_checkbox' in flat(r),
 "nested_list_2sp": lambda r: types(r) == ['list'],
 "nested_olist_3sp": lambda r: types(r) == ['list'],
 "olist_after_para_1": lambda r: types(r) == ['paragraph', 'list'],
 "year_dot": lambda r: types(r) == ['paragraph'],
 "numbers_with_dot_in_text": lambda r: types(r) == ['paragraph'],
 "hash_tag": lambda r: types(r) == ['paragraph'],
 "code_after_para": lambda r: types(r) == ['paragraph', 'pre', 'paragraph'],
 "table_pipe_in_code": lambda r: '"a|b"' in flat(r),
 "inline_html": lambda r: '"bold"' in flat(r),
 "arrow": lambda r: 'a -> b => c <- d' in flat(r),
 "html_lt": lambda r: '<tag>' in flat(r) and 'a < b' in flat(r),
}

if __name__ == "__main__":
    cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    bad = 0
    for name, md in cases.items():
        fixed = tgmd.normalize(md)
        if tgmd.normalize(fixed) != fixed:
            bad += 1
            print("not idempotent:", name)
        rm = parse(fixed)
        if "error" in rm or (name in EXPECT and not EXPECT[name](rm)):
            bad += 1
            print("FAIL", name, types(rm), repr(fixed))
    print(f"{len(cases)} cases, {bad} failures")
    sys.exit(1 if bad else 0)
