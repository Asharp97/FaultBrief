import json
import sys
from pathlib import Path

from .config import Settings
from .main import create_app

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "docs" / "api" / "openapi.json"


def contract_text() -> str:
    # Export with explicit empty configuration: no credentials or provider URLs in the artifact.
    application = create_app(
        Settings(_env_file=None, database_url=None, auth_url=None, jwks_url=None)
    )
    return json.dumps(application.openapi(), ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    expected = contract_text()
    if "--check" in sys.argv:
        if not DESTINATION.exists() or DESTINATION.read_text(encoding="utf-8") != expected:
            print("OpenAPI artifact is stale. Run pnpm run api:export.", file=sys.stderr)
            sys.exit(1)
        print("OpenAPI artifact matches the API contracts.")
    else:
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        DESTINATION.write_text(expected, encoding="utf-8")
        print("Exported docs/api/openapi.json without environment values.")


if __name__ == "__main__":
    main()
