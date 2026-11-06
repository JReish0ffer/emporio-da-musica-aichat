"""Terminal chat.  python -m emporio.interfaces.cli [--session ID] [--debug] [--rebuild-db] [--transcript FILE]"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from .. import config, db


def main() -> None:
    ap = argparse.ArgumentParser(description="Chat with Emi, the Empório da Música attendant.")
    ap.add_argument("--session", default=None, help="Session id; reuse it to resume a conversation.")
    ap.add_argument("--debug", action="store_true", help="Show tool calls.")
    ap.add_argument("--rebuild-db", action="store_true", help="Rebuild the SQLite DB from the CSVs (wipes history).")
    ap.add_argument("--transcript", help="Also append the conversation to this Markdown file.")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    console = Console()
    if args.rebuild_db or not config.DB_PATH.exists():
        db.build_db()
    from ..agent.loop import Agent  # imported late so --help works without an API key

    session = args.session or uuid.uuid4().hex[:8]
    agent = Agent(session_id=session)
    resumed = bool(agent.memory.history(session))
    console.print(f"[bold]Empório da Música[/bold] — session [cyan]{session}[/cyan]"
                  f"{' (resumed)' if resumed else ''}. Type 'sair' to quit.\n")

    def trace(name: str, a: dict, result: str) -> None:
        if args.debug:
            console.print(f"[dim]  ⚙ {name}({json.dumps(a, ensure_ascii=False)}) → {result[:160]}…[/dim]")

    log = Path(args.transcript) if args.transcript else None
    while True:
        try:
            text = console.input("[bold green]Você:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in {"sair", "exit", "quit"}:
            break
        reply = agent.chat(text, on_tool=trace)
        console.print("[bold blue]Emi:[/bold blue]", Markdown(reply))
        console.print()
        if log:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(f"**Cliente:** {text}\n\n**Emi:** {reply}\n\n")
    console.print("Até mais! 🎸")


if __name__ == "__main__":
    main()
