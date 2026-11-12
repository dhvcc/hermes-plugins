"""The one user-facing notice: a worker stopped by the last-resort backstop. settings.language: en | ru."""
STRINGS = {
    "en": {"stopped_msg": "⏹ Stopped subagent “{goal}”: {el} with an ETA of ~{eta}, no progress for {quiet}. "
                          "Whatever it finished arrives separately.",
           "stop_failed": "⚠️ Could not stop a stuck subagent: {id}"},
    "ru": {"stopped_msg": "⏹ Остановил субагента «{goal}»: {el} при сроке ~{eta}, без прогресса {quiet}. "
                          "Что успел, придёт отдельным сообщением.",
           "stop_failed": "⚠️ Не смог остановить зависшего субагента: {id}"},
}


def strings(lang: str) -> dict:
    return STRINGS.get(str(lang or "en").lower()[:2], STRINGS["en"])
