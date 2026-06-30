import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seeg_protect.config import settings
from seeg_protect.security import build_signature


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/sign_payload.py '<json-payload>'")
    payload = " ".join(sys.argv[1:])
    print(build_signature(settings.webhook_secret, payload.encode("utf-8")))


if __name__ == "__main__":
    main()
