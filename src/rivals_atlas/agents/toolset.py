"""The data tools as one Haystack `Toolset`.

The toolset holds only a descriptor (database path and tool names), so `to_dict` / `from_dict` rebuild it anywhere, as the
Haystack docs recommend for a toolset whose tools come from elsewhere. The tools it makes open their own read-only SQLite
connection on every call, because Haystack runs tools in worker threads and a connection belongs to the thread that made it.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from haystack.core.serialization import generate_qualified_class_name
from haystack.tools import Tool, Toolset, create_tool_from_function

from rivals_atlas.agents import tools
from rivals_atlas.core import db
from rivals_atlas.ingest import meta as meta_mod

if TYPE_CHECKING:
    from rivals_atlas.agents import Ledger


def _wrap(fn: Any, drop: set[str], run: Any) -> Any:
    """A copy of `fn` without the arguments the model must not see (the connection, the meta document)."""
    sig = inspect.signature(fn)
    params = [p for n, p in sig.parameters.items() if n not in drop]

    def w(**kw: Any) -> str:
        return run(kw)
    w.__signature__ = sig.replace(parameters=params)         # type: ignore[attr-defined]
    w.__annotations__ = {p.name: p.annotation for p in params}
    w.__doc__, w.__name__ = fn.__doc__, fn.__name__
    return w


class RivalsToolset(Toolset):
    def __init__(self, db_path: Path | str, names: tuple[str, ...] = tuple(tools.TOOLS),
                 meta: dict[str, Any] | None = None, ledger: Ledger | None = None) -> None:
        unknown = [n for n in names if n not in tools.TOOLS]
        if unknown:
            raise ValueError(f"unknown tool(s): {', '.join(unknown)}")
        self.db_path = Path(db_path)
        self.names = tuple(names)
        self.meta = meta
        self.ledger = ledger
        super().__init__(tools=[self._make(n) for n in self.names])

    def _make(self, name: str) -> Tool:
        def run(kw: dict[str, Any]) -> str:
            try:
                f = tools.run(db.connect_readonly(self.db_path), name, kw, self.meta)
            except (KeyError, TypeError, ValueError) as e:       # a bad argument is the model's to read and retry
                return json.dumps({"error": str(e)})
            if self.ledger is not None:
                self.ledger.add_finding(f)
            return json.dumps(f.to_dict())
        return create_tool_from_function(_wrap(tools.TOOLS[name], {"con", "meta"}, run))

    def to_dict(self) -> dict[str, Any]:
        return {"type": generate_qualified_class_name(type(self)),
                "data": {"db_path": str(self.db_path), "names": list(self.names)}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RivalsToolset:
        d = data["data"]
        path = Path(d["db_path"])
        return cls(path, tuple(d["names"]), meta_mod.load(path.parent))     # the meta file sits beside the database
