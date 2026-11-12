"""Board strings. Set settings.language: en | ru."""
STRINGS = {
    "en": {"caption": "Subagents", "min": "min", "left": "~{n} min left", "since": "since", "of": "of ~",
           "done": "done", "error": "error", "stopped": "stopped", "no_reply": "no reply", "reply": "replied",
           "empty": "no subagents yet", "hang": "stuck in {tool} for {n} min"},
    "ru": {"caption": "Субагенты", "min": "мин", "left": "ещё ~{n} мин", "since": "с", "of": "из ~",
           "done": "готово", "error": "ошибка", "stopped": "остановлена", "no_reply": "без ответа", "reply": "ответ",
           "empty": "субагентов пока не было", "hang": "висит в {tool} {n} мин"},
}


def strings(lang: str) -> dict:
    return STRINGS.get(str(lang or "en").lower()[:2], STRINGS["en"])
