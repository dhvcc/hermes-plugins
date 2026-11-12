"""User-facing strings (Telegram board and the rare direct notice). Set settings.language: en | ru."""
STRINGS = {
    "en": {"caption": "Subagents", "min": "min", "left": "~{n} min left", "since": "since", "of": "of ~",
           "done": "done", "error": "error", "stopped": "stopped", "no_reply": "no reply", "reply": "replied",
           "empty": "no subagents yet", "hang": "stuck in {tool} for {n} min",
           "stopped_msg": "⏹ Stopped subagent “{goal}”: {el} with an ETA of ~{eta}, no progress for {quiet}. "
                          "Whatever it finished arrives separately.",
           "stop_failed": "⚠️ Could not stop a stuck subagent: {id}"},
    "ru": {"caption": "Субагенты", "min": "мин", "left": "ещё ~{n} мин", "since": "с", "of": "из ~",
           "done": "готово", "error": "ошибка", "stopped": "остановлена", "no_reply": "без ответа", "reply": "ответ",
           "empty": "субагентов пока не было", "hang": "висит в {tool} {n} мин",
           "stopped_msg": "⏹ Остановил субагента «{goal}»: {el} при сроке ~{eta}, без прогресса {quiet}. "
                          "Что успел, придёт отдельным сообщением.",
           "stop_failed": "⚠️ Не смог остановить зависшего субагента: {id}"},
}


def strings(lang: str) -> dict:
    return STRINGS.get(str(lang or "en").lower()[:2], STRINGS["en"])
