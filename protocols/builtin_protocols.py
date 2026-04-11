"""Built-in protocol definitions shipped with JARVIS."""

from __future__ import annotations

from protocols.models import (
    ProtocolActionDefinition,
    ProtocolConfirmationPolicy,
    ProtocolDefinition,
    ProtocolTrigger,
)


BUILTIN_PROTOCOLS: tuple[ProtocolDefinition, ...] = (
    ProtocolDefinition(
        id="clean_slate",
        title="Clean Slate",
        description="Close a safe allowlist of apps after explicit confirmation.",
        triggers=(
            ProtocolTrigger(type="exact", phrase="протокол чистый лист", locale="ru-RU"),
            ProtocolTrigger(type="exact", phrase="protocol clean slate", locale="en-US"),
        ),
        steps=(
            ProtocolActionDefinition(action_type="close_app", inputs={"app_name": "Telegram"}),
            ProtocolActionDefinition(action_type="close_app", inputs={"app_name": "Notes"}),
            ProtocolActionDefinition(action_type="close_app", inputs={"app_name": "Safari"}),
            ProtocolActionDefinition(action_type="close_app", inputs={"app_name": "Music"}),
        ),
        confirmation_policy=ProtocolConfirmationPolicy(mode="always"),
        completion_message='Completed protocol "Clean Slate".',
        completion_message_ru='Завершил протокол "чистый лист".',
        tags=("builtin", "cleanup"),
    ),
    ProtocolDefinition(
        id="i_am_home",
        title="I Am Home",
        description="Open the home soundtrack link and name the most recent remembered project.",
        triggers=(
            ProtocolTrigger(type="exact", phrase="я дома", locale="ru-RU"),
            ProtocolTrigger(type="exact", phrase="i am home", locale="en-US"),
            ProtocolTrigger(type="exact", phrase="i'm home", locale="en-US"),
        ),
        steps=(
            ProtocolActionDefinition(
                action_type="open_website",
                inputs={
                    "browser_name": "Safari",
                    "url": "https://www.youtube.com/watch?v=IyR25B-IGyg",
                },
            ),
        ),
        completion_message="{home_greeting_en} {last_project_sentence_en}",
        completion_message_ru="{home_greeting_ru} {last_project_sentence_ru}",
        tags=("builtin", "home"),
    ),
)
