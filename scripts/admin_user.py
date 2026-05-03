"""Create or update local admin users.

Run from the server:
    uv run python scripts/admin_user.py create --username admin
"""
import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import SessionLocal, init_db
from services.auth_service import AuthService


def read_password() -> str:
    """Prompt for a password twice without echoing it."""
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage karaoke admin users")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create",
        help="Create an admin or update the password when the username exists",
    )
    create_parser.add_argument("--username", required=True)

    args = parser.parse_args()
    service = AuthService()

    try:
        password = read_password()
        init_db()
        with SessionLocal() as db:
            admin = service.create_or_update_admin(db, args.username, password)
            print(f"Admin user ready: {admin.username}")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
