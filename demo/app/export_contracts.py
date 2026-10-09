import argparse
import json
from pathlib import Path

from .config import DemoSettings
from .main import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[2] / "docs" / "api" / "demo-openapi.json"
    content = json.dumps(create_app(DemoSettings(_env_file=None)).openapi(), indent=2) + "\n"
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf8") != content:
            parser.exit(1, "Demo API contract is stale. Run pnpm run demo:api.\n")
        print("Demo OpenAPI artifact matches the public contracts.")
    else:
        destination.write_text(content, encoding="utf8")
        print("Exported demo API contract without operator scenarios or credentials.")


if __name__ == "__main__":
    main()
