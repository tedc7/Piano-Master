"""This install's piano server, for the dev box's Python tools (tools/server.env.example).

The settings come from ~/.config/piano-master/server.env (or $PIANO_CONFIG), never from the repo:
the repo is public. A variable already set in the environment wins. The skill token is beside it,
in ~/.config/piano-master/skill-token (or $PIANO_SKILL_TOKEN).
"""
from __future__ import annotations

import os
import ssl
from pathlib import Path

CONFIG = Path(os.environ.get("PIANO_CONFIG", Path.home() / ".config" / "piano-master" / "server.env"))
TOKEN_FILE = Path.home() / ".config" / "piano-master" / "skill-token"


def setting(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            k, sep, v = line.strip().partition("=")
            if sep and k.strip() == name and not k.lstrip().startswith("#"):
                v = v.split(" #")[0].strip().strip("'\"")
                if v:
                    return v
    raise SystemExit(f"{name} isn't set: copy tools/server.env.example to {CONFIG} and fill it in")


def server() -> str:
    """The piano site's address, like https://piano.example.lan (no trailing slash)."""
    return setting("PIANO_SERVER").rstrip("/")


def ssl_context() -> ssl.SSLContext:
    """Verifies the server with its own certificate authority: never skipped."""
    ca = Path(os.path.expanduser(setting("CADDY_ROOT_CA")))
    if not ca.exists():
        raise SystemExit(f"no root certificate at {ca} (CADDY_ROOT_CA): copy the server certificate authority's root there")
    return ssl.create_default_context(cafile=str(ca))


def skill_token() -> str:
    t = os.environ.get("PIANO_SKILL_TOKEN") or (TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else "")
    if not t:
        raise SystemExit(f"no skill token: make one in the app (Config > Dev box connection) and save it in {TOKEN_FILE}")
    return t


def cert_failure(e: BaseException) -> str | None:
    """A clear message when a request failed because the server's certificate didn't verify."""
    reason = getattr(e, "reason", e)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (f"{server()}'s certificate doesn't verify with CADDY_ROOT_CA: a rebuilt server has a new certificate "
                "authority unless its Caddy data was restored; copy its new root to the dev box and every device")
    return None
