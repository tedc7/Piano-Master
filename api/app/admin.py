"""Server-side maintenance, run inside the API container:

    python -m app.admin reset-pin          # forget the parent PIN; the app then asks for a new one
    python -m app.admin skill-token NAME   # a token for a Claude skill on the dev box (Skill API, arch §10.9)
"""
from __future__ import annotations

import sys

from . import db, library


def main(argv: list[str]) -> int:
    if argv[:1] == ["skill-token"] and len(argv) == 2:
        db.migrate()
        con = db.connect()
        try:
            print(library.new_token(con, argv[1]))
        finally:
            con.close()
        return 0
    if argv[:1] != ["reset-pin"]:
        print(__doc__.strip())
        return 2
    db.migrate()
    con = db.connect()
    try:
        con.execute("UPDATE parent SET pin_hash = NULL, failed_attempts = 0, lockouts = 0, locked_until = NULL WHERE id = 1")
        con.execute("DELETE FROM parent_sessions")
    finally:
        con.close()
    print("Parent PIN cleared: open Parent in the app to choose a new one.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
