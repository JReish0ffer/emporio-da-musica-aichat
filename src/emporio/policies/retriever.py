"""Policy RAG: PDF -> section chunks -> BM25 retrieval.

Why section chunks + BM25 (no vector DB): the manual is ~8 pages written with precise keywords (PIX, PAC, 7 dias,
garantia...). Each numbered section is a self-contained rule, so splitting on headings keeps rules intact and gives
us a citable section number. A small synonym map bridges customer slang to the manual's vocabulary.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from rank_bm25 import BM25Okapi

from .. import config
from ..tools.common import norm

_NOISE = re.compile(r"^(Empório da Música\s+Manual de Políticas e Procedimentos|Página \d+)\s*$")
_SUB = re.compile(r"^(\d{1,2}\.\d)\s+(\S.*)$")
_TOP = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
_STOP = set(norm("a o as os de da do das dos e em um uma para por com que se na no nas nos ao à ou eu voce posso "
                 "queria gostaria quero como qual quais tem ter e é").split())

# customer words -> manual vocabulary (applied to the query only)
_SYNONYMS = {
    "devolver": "devolucao arrependimento troca reembolso", "devolucao": "arrependimento reembolso troca",
    "arrependi": "arrependimento devolucao", "arrependimento": "devolucao",
    "trocar": "troca preferencia defeito", "quebrou": "defeito garantia", "defeito": "garantia troca",
    "estragou": "defeito garantia", "parcelar": "parcelamento credito parcelas", "parcelas": "parcelamento credito",
    "cartao": "credito debito", "desconto": "promocoes pix", "promocao": "promocoes descontos",
    "entrega": "frete entregas prazo", "entregar": "frete entregas", "frete": "entregas",
    "rastrear": "rastreamento codigo", "rastreio": "rastreamento codigo", "horario": "funcionamento horario",
    "aberto": "funcionamento horario", "abre": "funcionamento horario", "fecha": "funcionamento horario",
    "dados": "privacidade lgpd", "privacidade": "lgpd dados", "pagar": "pagamento formas pix", "paga": "pagamento pix",
}


@dataclass
class Chunk:
    section: str
    title: str
    text: str


def _clean_lines(pdf: Path) -> list[str]:
    lines: list[str] = []
    for page in PdfReader(str(pdf)).pages[1:]:  # page 1 is the cover
        for raw in (page.extract_text(extraction_mode="layout") or "").splitlines():
            line = re.sub(r"\s+", " ", raw).strip()
            if line and not _NOISE.match(line):
                lines.append(line)
    return lines


def build_chunks(pdf: Path = config.POLICY_PDF) -> list[Chunk]:
    chunks: list[Chunk] = []
    top_num, top_title = 0, ""
    cur: Chunk | None = None
    for line in _clean_lines(pdf):
        m_top = _TOP.match(line)
        m_sub = _SUB.match(line)
        # Top-level headings must be sequential (1,2,3…), which rejects numbered list items like §7.2's "1. Saudação".
        if m_top and int(m_top.group(1)) == top_num + 1:
            top_num, top_title = int(m_top.group(1)), m_top.group(2)
            cur = Chunk(str(top_num), top_title, "")
            chunks.append(cur)
        elif m_sub and m_sub.group(1).startswith(f"{top_num}."):
            cur = Chunk(m_sub.group(1), f"{top_title} > {m_sub.group(2)}", "")
            chunks.append(cur)
        elif cur:
            cur.text += line + "\n"
    return [c for c in chunks if c.text.strip()]


class PolicyIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.bm25 = BM25Okapi([self._tok(f"{c.title} {c.title} {c.text}") for c in chunks])

    @staticmethod
    def _tok(text: str) -> list[str]:
        return [t for t in norm(text).split() if t not in _STOP]

    def search(self, query: str, k: int = 3) -> list[tuple[float, Chunk]]:
        toks = self._tok(query)
        expanded = toks + [w for t in toks for w in _SYNONYMS.get(t, "").split()]
        scores = self.bm25.get_scores(expanded)
        ranked = sorted(zip(scores, self.chunks), key=lambda t: -t[0])
        return [(s, c) for s, c in ranked[:k] if s > 0]


@lru_cache(maxsize=1)
def get_index() -> PolicyIndex:
    return PolicyIndex(build_chunks())


def search_policies(ctx, question: str, top_k: int = 3) -> dict:
    hits = get_index().search(question, k=top_k)
    if not hits:
        return {"found": False, "message": "No policy section matches. Do not invent a rule; offer a human attendant."}
    return {"found": True, "sections": [
        {"section": f"§{c.section}", "title": c.title, "text": c.text.strip()} for _, c in hits],
        "instruction": "Answer ONLY from these sections; cite the section number when helpful."}
