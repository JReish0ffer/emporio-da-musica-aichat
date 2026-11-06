"""Agent-loop behaviour with a stubbed LLM (no network)."""
from types import SimpleNamespace as NS

from emporio import config
from emporio.agent.loop import Agent


class FakeClient:
    """Returns scripted assistant messages and records what it was sent."""
    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw["messages"])
        msg = NS(content=self.contents.pop(0), tool_calls=None)
        return NS(choices=[NS(message=msg)])


def make_agent(tmp_path, monkeypatch, client):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    return Agent(session_id="s1", client=client)


def test_invented_ticket_number_is_blocked(tmp_path, monkeypatch):
    client = FakeClient("Abri o chamado EM-00042 pra você!", "Posso abrir um chamado com a equipe, quer?")
    agent = make_agent(tmp_path, monkeypatch, client)
    reply = agent.chat("quero devolver")
    assert "EM-00042" not in reply and len(client.calls) == 2
    assert "GUARD" in client.calls[1][-1]["content"]


def test_real_ticket_number_passes(tmp_path, monkeypatch):
    client = FakeClient("Seu chamado EM-00001 foi registrado.")
    agent = make_agent(tmp_path, monkeypatch, client)
    agent.conn.execute("INSERT INTO tickets (session_id, reason, summary, created_at) VALUES ('s1','x','y','now')")
    agent.conn.commit()
    assert "EM-00001" in agent.chat("e o chamado?")


def test_history_is_persisted_and_resumable(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, FakeClient("Oi!"))
    agent.chat("olá")
    again = Agent(session_id="s1", client=FakeClient("De novo!"))
    assert [m["content"] for m in again.memory.history("s1")] == ["olá", "Oi!"]
