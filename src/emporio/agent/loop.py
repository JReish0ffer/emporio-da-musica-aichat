"""The agent: a tool-calling loop on top of Groq (OpenAI-compatible chat API)."""
from __future__ import annotations

import json
import time
from typing import Callable

from groq import APIStatusError, BadRequestError, Groq, RateLimitError

from .. import config, db
from ..memory.store import Memory
from ..tools.common import Ctx
from ..tools.store import is_open_now
from .prompt import build_system_prompt
from .registry import SCHEMAS, dispatch

FALLBACK = ("Desculpa, tive um probleminha técnico aqui agora. 😅 Pode repetir sua mensagem? "
            "Se preferir, a equipe atende pelo (67) 3321-4500.")


class Agent:
    def __init__(self, session_id: str = "default", client: Groq | None = None, model: str | None = None):
        self.conn = db.get_conn()
        self.memory = Memory(self.conn)
        self.client = client or Groq()
        self.model = model or config.MODEL
        self.ctx = Ctx(conn=self.conn, now=config.now(), session_id=session_id)
        self.ctx.verified_customers = self.memory.open_session(session_id, self.ctx.now)

    # -- LLM call with small retry policy for Groq's occasional malformed tool calls / rate limits
    def _complete(self, messages: list[dict]):
        last: Exception | None = None
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(
                    model=self.model, messages=messages, tools=SCHEMAS, tool_choice="auto",
                    temperature=0.3, max_completion_tokens=1200, reasoning_effort="low")
            except RateLimitError as e:
                last = e
                time.sleep(2 * (attempt + 1))
            except BadRequestError as e:  # e.g. tool_use_failed: just try again
                last = e
            except APIStatusError as e:
                last = e
                time.sleep(1)
        raise RuntimeError(f"LLM unavailable: {last}")

    def chat(self, user_text: str, on_tool: Callable[[str, dict, str], None] | None = None) -> str:
        """Send one customer message, return the attendant's reply. `on_tool(name, args, result)` for tracing."""
        self.ctx.now = config.now()
        sid = self.ctx.session_id
        system = build_system_prompt(self.ctx.now, is_open_now(self.ctx)["is_open"])
        messages = [{"role": "system", "content": system}, *self.memory.history(sid), {"role": "user", "content": user_text}]
        self.memory.add(sid, "user", user_text, self.ctx.now)

        reply = FALLBACK
        try:
            for _ in range(config.MAX_TOOL_ROUNDS):
                msg = self._complete(messages).choices[0].message
                if not msg.tool_calls:
                    reply = (msg.content or "").strip() or FALLBACK
                    break
                messages.append({
                    "role": "assistant", "content": msg.content or "",
                    "tool_calls": [{"id": tc.id, "type": "function",
                                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                   for tc in msg.tool_calls]})
                for tc in msg.tool_calls:
                    result = dispatch(self.ctx, tc.function.name, tc.function.arguments)
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    args = json.loads(tc.function.arguments or "{}") if tc.function.arguments else {}
                    self.memory.add(sid, "tool", result, self.ctx.now, {"name": tc.function.name, "args": args})
                    if on_tool:
                        on_tool(tc.function.name, args, result)
                self.memory.save_verified(sid, self.ctx.verified_customers)
            else:
                reply = ("Esse assunto ficou um pouco complexo pra eu resolver por aqui. "
                         "Posso abrir um atendimento com a equipe para te ajudar melhor?")
        except RuntimeError:
            reply = FALLBACK
        self.memory.add(sid, "assistant", reply, self.ctx.now)
        return reply
