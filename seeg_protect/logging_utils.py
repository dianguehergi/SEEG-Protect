import json
from pathlib import Path
from typing import Any

from .models import utc_now_iso


def append_event(path: str, event_type: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": utc_now_iso(),
        "event_type": event_type,
        "payload": payload,
    }
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")

