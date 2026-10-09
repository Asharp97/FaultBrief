import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError


def main() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    action = sys.argv[1] if len(sys.argv) == 2 else "upgrade"
    try:
        if action == "upgrade":
            command.upgrade(config, "head")
        elif action == "check":
            command.check(config)
        elif action == "sql":
            command.upgrade(config, "head", sql=True)
        else:
            raise ValueError("Migration command must be upgrade, check, or sql.")
    except SQLAlchemyError:
        print("Migration failed. Check database access and the current schema.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
