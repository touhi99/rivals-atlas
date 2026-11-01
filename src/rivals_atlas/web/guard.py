"""One check for every POST route: the app's own pages send this header, a form on another site cannot."""
from fastapi import HTTPException, Request

HEADER = "x-requested-with"
VALUE = "rivals-atlas"


def require_app_header(request: Request) -> None:
    if request.headers.get(HEADER) != VALUE:
        raise HTTPException(403, "Missing header")
