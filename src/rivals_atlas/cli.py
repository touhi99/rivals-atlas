"""Command line: import raw files, fetch from the data site, serve the dashboard, answer questions."""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from rivals_atlas import openssl_fix
from rivals_atlas.core import config, db
from rivals_atlas.graph import knowledge
from rivals_atlas.graph import network as graph
from rivals_atlas.ingest import meta as meta_mod
from rivals_atlas.ingest.importer import import_folder


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rivals-atlas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import", help="read data/raw/{matches,history} into the database")
    fe = sub.add_parser("fetch", help="download match history from rivalsmeta (opt-in) and import it")
    fe.add_argument("--profile", help="profile id (the number in the player page address); saved for next time")
    fe.add_argument("--mode", type=int, default=2, help="2 ranked, 1 quick play")
    fe.add_argument("--limit", type=int, default=None, help="at most this many new match documents")
    fe.add_argument("--pace", choices=["normal", "gentle"], default="gentle", help="gentle (default) = one request every 3 seconds, normal = one per second")
    fe.add_argument("--no-refresh", action="store_true", help="do not ask the site to refresh the profile from the game first")
    fe.add_argument("--yes", action="store_true", help="confirm you have read the notice")
    gr = sub.add_parser("graph", help="rebuild hero synergy and counter edges from stored matches")
    gr.add_argument("--ladybug", action="store_true", help="also (re)build the LadybugDB projection (data/graph.lbdb)")
    sub.add_parser("insights", help="let the Coach and Tilt guard find what stands out in the matches (needs a model, see llm.py)")
    ask = sub.add_parser("ask", help="ask the agents a question about the stored matches (needs a model, see llm.py)")
    ask.add_argument("question")
    ask.add_argument("--agent", choices=["coordinator", "coach", "tilt_guard", "cartographer"], default="coordinator")
    sv = sub.add_parser("serve", help="start the dashboard")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--open", action="store_true", help="open the dashboard in the browser once it is ready")
    sv.add_argument("--reload", action="store_true", help="development: restart on code changes")
    return ap


def cmd_import(a: argparse.Namespace, base: Path) -> int:
    con = db.connect(base / "rivals.db")
    rep = import_folder(con, base / "raw", os.environ.get("RIVALS_ATLAS_SELF") or None)
    print("\n".join(rep.lines()))
    print(f"{graph.build(con)} graph edges rebuilt")
    if m := meta_mod.load(base):
        print(f"{knowledge.load_meta(con, m)} team-up facts loaded")
    build_ladybug(con, base)
    return 0


def cmd_fetch(a: argparse.Namespace, base: Path) -> int:
    from rivals_atlas.ingest import fetch
    st = config.load_settings(base)
    profile = fetch.parse_profile(a.profile) or st.get("profile_id")
    if not profile:
        print("Give --profile with the address of the player's page, or the number at its end.")
        return 2
    if not (a.yes or st.get("consent_at")):
        print(fetch.NOTICE)
        print("\nRun again with --yes to confirm.")
        return 2
    config.save_settings({"profile_id": str(profile), "consent_at": st.get("consent_at") or time.time()}, base)
    try:
        res = fetch.run(str(profile), a.mode, base, a.limit, pace=a.pace, refresh=not a.no_refresh,
                        progress=lambda p: print(f"[{p['stage']}] {p['message']}"))
    except fetch.FetchError as e:
        print(f"Stopped: {e}")
        return 1
    print(res)
    return 0


def build_ladybug(con: sqlite3.Connection, base: Path) -> None:
    from rivals_atlas.graph import store as lbug_store
    counts = lbug_store.rebuild(con, base / lbug_store.GRAPH_FILE, meta_mod.load(base))
    print(f"LadybugDB graph rebuilt: {counts}")


def cmd_graph(a: argparse.Namespace, base: Path) -> int:
    con = db.connect(base / "rivals.db")
    print(f"{graph.build(con)} edges")
    if a.ladybug:
        build_ladybug(con, base)
    return 0


def cmd_ask(a: argparse.Namespace, base: Path) -> int:
    from rivals_atlas import agents
    from rivals_atlas.agents import llm
    db_path = base / "rivals.db"
    if a.agent == "coordinator":
        ans = agents.ask(a.question, llm.generators(), db_path, meta_mod.load(base))
    else:
        ans = agents.ask_specialist(a.agent, a.question, llm.make_generator(), db_path, meta_mod.load(base))
    print(f"[{llm.setting(base)}]\n{ans.report}")
    if ans.framing:
        print(f"\n(unchecked model text) {ans.framing}")
    if ans.unverified:
        print(f"(numbers in that text that no query returned: {', '.join(ans.unverified)})")
    return 0


def cmd_insights(a: argparse.Namespace, base: Path) -> int:
    from rivals_atlas.agents import insights
    data = insights.generate(config.db_path(), base, meta_mod.load(base))
    print(f"[{data['model']}] {data['scope']}, {data['matches']} matches")
    for o in data["observations"]:
        print(f"\n- [{o['badge']}] {o['text']}")
        for e in o["evidence"]:
            print(f"    {e['label']}: " + (f"{e['rate']:.0%} ({e['wins']} wins in {e['n']}, range {e['lo']:.0%} to {e['hi']:.0%})" if e["rate"] is not None else f"n={e['n']}"))
    if not data["observations"]:
        print("\nNo observation survived the check.")
    if data["dropped"]:
        print(f"\n{len(data['dropped'])} dropped: " + "; ".join(dict.fromkeys(data["dropped"])))
    return 0


def _port_open(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_ours(port: int) -> bool:
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.5) as reply:
            return json.load(reply).get("app") == "rivals-atlas"
    except Exception:  # noqa: BLE001  (any failure means "not this app")
        return False


def _free_port(start: int) -> int | None:
    for port in range(start, start + 20):
        if not _port_open(port):
            return port
    return None


def _open_when_ready(port: int) -> None:
    for _ in range(300):
        if _is_ours(port):
            webbrowser.open(f"http://127.0.0.1:{port}/")
            return
        time.sleep(0.1)


def cmd_serve(a: argparse.Namespace, base: Path) -> int:
    port = a.port
    if _port_open(port):
        if _is_ours(port):
            print(f"Rivals Atlas is already running: http://127.0.0.1:{port}/")
            if a.open:
                webbrowser.open(f"http://127.0.0.1:{port}/")
            return 0
        port = _free_port(port + 1)
        if port is None:
            print(f"Port {a.port} is in use by another program, and so are the next 20.")
            return 1
        print(f"Port {a.port} is in use by another program; using {port} instead.")
    if a.open:
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    import uvicorn
    uvicorn.run("rivals_atlas.web.api:app", host="127.0.0.1", port=port, reload=a.reload,
                reload_dirs=[str(Path(__file__).parent)] if a.reload else None)
    return 0


COMMANDS: dict[str, Callable[[argparse.Namespace, Path], int]] = {
    "import": cmd_import, "fetch": cmd_fetch, "graph": cmd_graph, "ask": cmd_ask, "insights": cmd_insights,
    "serve": cmd_serve,
}


def main(argv: list[str] | None = None) -> int:
    config.load_env()                      # .env in the working directory: model key and settings, never printed
    a = build_parser().parse_args(argv)
    try:
        openssl_fix.ensure()               # macOS: make LadybugDB loadable before anything imports it
    except openssl_fix.FixError as e:
        print(f"Rivals Atlas cannot start: {e}", file=sys.stderr)
        return 1
    return COMMANDS[a.cmd](a, config.data_dir())
