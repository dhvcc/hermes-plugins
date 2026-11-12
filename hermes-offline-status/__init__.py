"""One silent status message in the Telegram home chat while the gateway is down: sent as the Telegram
connection stops, deleted when it connects again. Pair with platforms.telegram.gateway_restart_notification:
false so Hermes' own shutdown and online pings stay quiet."""
import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

log = logging.getLogger("hermes_offline_status")
TEXT = {"en": {"restart": "🔄 Hermes is restarting…", "stop": "⏸ Hermes stopped at {t}"},
        "ru": {"restart": "🔄 Hermes перезапускается…", "stop": "⏸ Hermes остановлен в {t}"}}


def _home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def _env(name):
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in (_home() / ".env").read_text().splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _state() -> Path:
    return _home() / "logs" / "offline-status.json"


def _api(method, body):
    token = _env("TELEGRAM_BOT_TOKEN")
    req = Request(f"https://api.telegram.org/bot{token}/{method}", json.dumps(body).encode(),
                  {"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _clear():
    """Delete the "off" message left by the previous stop, if any."""
    try:
        data = json.loads(_state().read_text())
    except Exception:
        return
    for _ in range(5):
        try:
            _api("deleteMessage", {"chat_id": data["chat"], "message_id": data["mid"]})
            break
        except Exception as exc:
            if "message to delete not found" in str(getattr(exc, "read", lambda: b"")()):
                break
            time.sleep(3)
    _state().unlink(missing_ok=True)


def register(ctx):
    chat = str(ctx.get_config("chat_id", None) or _env("TELEGRAM_HOME_CHANNEL") or "")
    lang = str(ctx.get_config("language", "en") or "en")[:2]
    if not chat:
        return

    def send_off():
        if _state().exists():
            return
        try:  # a planned restart (/restart, `hermes gateway restart`) leaves this marker
            from gateway.restart_notice import planned_restart_marker_path
            kind = "restart" if planned_restart_marker_path().exists() else "stop"
        except Exception:
            kind = "stop"
        text = TEXT.get(lang, TEXT["en"])[kind].format(t=time.strftime("%H:%M"))
        res = _api("sendMessage", {"chat_id": chat, "disable_notification": True, "text": text})
        _state().write_text(json.dumps({"chat": chat, "mid": res["result"]["message_id"]}))

    def telegram(app, adapter):
        threading.Thread(target=_clear, daemon=True).start()
        if getattr(adapter, "_offline_status_wrapped", False):
            return
        original = adapter.disconnect

        async def disconnect(*args, **kwargs):
            try:
                await asyncio.wait_for(asyncio.to_thread(send_off), 8)
            except Exception:
                log.exception("offline-status: send failed")
            return await original(*args, **kwargs)

        adapter.disconnect = disconnect
        adapter._offline_status_wrapped = True

    ctx.register_telegram_handler(telegram)
