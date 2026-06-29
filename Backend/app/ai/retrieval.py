"""Lexical retrieval over a run's per-invoice free text — the "R" in the
hybrid RAG assistant.

Anthropic exposes no embeddings API, the project ships only numpy as a math
dependency, and a run's corpus is small and bounded (tens–hundreds of
invoices), so a classic BM25 ranker is the right tool here: genuine
information retrieval (TF-IDF with length normalisation), deterministic,
offline, and zero extra dependencies. The LLM does the *semantic
understanding* of the question (see app/api/assistant_hybrid.py); this module
finds the invoices whose notes are most relevant to the query terms so the
model can answer grounded in real rows instead of guessing.

One ``InvoiceDoc`` is built per invoice from its human-readable text — vendor,
exception type/description, AI root cause + rationale, resolution path, and any
drafted email — i.e. exactly the free-text fields a deterministic numeric query
can't address.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# Common English words carry no retrieval signal — dropping them keeps BM25
# from ranking on "the"/"is" overlap. Small, hand-picked; not a full stoplist.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or that
    the to was were will with what which who whom why how when where this these those
    i we you they me my our your their do does did can could should would about""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens, stopwords removed. Deterministic."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if t not in _STOPWORDS]


@dataclass
class InvoiceDoc:
    invoice_id: str
    text: str
    tokens: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = tokenize(self.text)


def build_corpus(state: dict) -> list[InvoiceDoc]:
    """One document per invoice, assembled from its free-text fields.

    Pulls the searchable prose for each invoice — vendor, exception
    type/description, AI root cause + rationale, resolution path, drafted email
    subject/body. Numbers (amount, SLA hours) are intentionally NOT the search
    target; those are answered deterministically elsewhere."""
    cls = {c.invoice_id: c for c in state.get("classifications", [])}
    res = {r.invoice_id: r for r in state.get("resolutions", [])}
    drafts = {d.invoice_id: d for d in state.get("drafts", [])}

    docs: list[InvoiceDoc] = []
    for row in state.get("rows", []):
        inv = row.invoice_id
        parts: list[str] = [inv, getattr(row, "vendor_name", "") or ""]
        et = getattr(row, "exception_type", None)
        if et:
            parts.append(getattr(et, "value", str(et)))
        parts.append(getattr(row, "exception_description", "") or "")

        c = cls.get(inv)
        if c is not None:
            pet = c.primary_exception_type
            parts.append(getattr(pet, "value", str(pet)))
            parts.append(getattr(c, "root_cause", "") or "")
            parts.append(getattr(c, "rationale", "") or "")
            sev = c.severity
            parts.append(getattr(sev, "value", str(sev)))

        r = res.get(inv)
        if r is not None:
            rp = r.resolution_path
            parts.append(getattr(rp, "value", str(rp)).replace("_", " "))

        d = drafts.get(inv)
        if d is not None:
            parts.append(getattr(d, "subject", "") or "")
            parts.append(getattr(d, "body", "") or "")

        docs.append(InvoiceDoc(invoice_id=inv, text=" ".join(p for p in parts if p)))
    return docs


class BM25:
    """Okapi BM25 over a small in-memory corpus.

    BM25 ranks a document by how many query terms it contains, weighted by how
    rare each term is across the corpus (IDF) and damped by document length so a
    long note doesn't outrank a short, on-point one. ``k1``/``b`` are the
    standard Okapi parameters. Built per query call — corpora here are tiny, so
    there's nothing to cache."""

    def __init__(self, docs: list[InvoiceDoc], *, k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b
        self.N = len(docs)
        self.doc_len = [len(d.tokens) for d in docs]
        self.avgdl = (sum(self.doc_len) / self.N) if self.N else 0.0

        # Document frequency per term, then smoothed IDF.
        df: dict[str, int] = {}
        self._tf: list[dict[str, int]] = []
        for d in docs:
            seen: dict[str, int] = {}
            for tok in d.tokens:
                seen[tok] = seen.get(tok, 0) + 1
            self._tf.append(seen)
            for tok in seen:
                df[tok] = df.get(tok, 0) + 1
        self.idf: dict[str, float] = {
            t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()
        }

    def _score(self, q_terms: list[str], i: int) -> float:
        if not self.avgdl:
            return 0.0
        tf = self._tf[i]
        dl = self.doc_len[i]
        score = 0.0
        for term in q_terms:
            f = tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += idf * (f * (self.k1 + 1)) / denom
        return score

    def search(self, query: str, *, top_k: int = 5) -> list[tuple[str, float]]:
        """Return up to ``top_k`` (invoice_id, score) pairs, score-descending.

        Only positive-scoring docs are returned — a doc that shares no query
        term scores 0 and is dropped, so an off-topic query yields nothing
        rather than an arbitrary "best" row."""
        q_terms = tokenize(query)
        if not q_terms or not self.docs:
            return []
        scored = [
            (self.docs[i].invoice_id, self._score(q_terms, i)) for i in range(self.N)
        ]
        scored = [(inv, s) for inv, s in scored if s > 0.0]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:top_k]


def retrieve(state: dict, query: str, *, top_k: int = 5) -> list[str]:
    """Top-k invoice ids most relevant to ``query`` (BM25 over run notes)."""
    docs = build_corpus(state)
    return [inv for inv, _ in BM25(docs).search(query, top_k=top_k)]
