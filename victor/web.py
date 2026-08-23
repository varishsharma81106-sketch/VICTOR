"""
Victor web console — a local, offline, read-mostly window into the knowledge base.

Why this exists
---------------
Until now the only way to see what Victor knows was to read the code or squint at
CLI tables. That made the two things Victor is actually *for* invisible:

  1. Compounding — you could not see the graph getting denser over time.
  2. Masked memory — the differentiating mechanism was a boolean in a JSON file.

This module serves a single-page console that makes both legible: the graph is
drawn, and masked nodes are drawn *as masked* — structure visible, content
withheld — so the mechanism is something you can look at and operate.

Design constraints, in priority order
-------------------------------------
* **Zero new dependencies.** Standard library only (``http.server``, ``json``).
  Victor's premise is being 90% capable offline; an interface that needs pip or
  a CDN would break the premise it is meant to display.
* **Localhost only.** Binds 127.0.0.1 by default. Victor holds unpublished
  research; the server must not be reachable from the network by accident.
* **Redaction is server-side.** The API never sends masked content to the
  browser — not even hidden behind a CSS class. If enforcement lived in the
  page, "view source" would be the bypass. See ``_redact()``.
"""
from __future__ import annotations

import heapq
import json
import logging
import mimetypes
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

logger = logging.getLogger(__name__)

WEBUI_DIR = Path(__file__).parent / "webui"

# Text substituted for any masked node's label before it leaves the process.
# A fixed string, not a truncation: length alone leaks information, and a
# truncated label is exactly the bug that shipped in v5.3 and was fixed on the
# anchor path in August 2026 while `list_masked` kept leaking 60 characters.
REDACTED = "████████"

# Metadata keys safe to expose for a masked node.
#
# An allowlist, not a denylist, and deliberately so. Claim nodes carry whatever
# fields the LLM extractor produced — `metric`, `value`, `direction`, `subject`
# — and for a scientific claim those fields *are* the content: withholding the
# sentence "improving accuracy by 8.70%" while publishing
# {"value": "8.70%, -19.0%, -17.6%"} withholds nothing. A denylist would have to
# be updated every time the extractor learns a new field, and would fail open
# when someone forgot. This list fails closed.
#
# Everything here is structural — position, weight, and state in the graph —
# which is precisely what masked memory is supposed to keep live.
STRUCTURAL_META_KEYS = frozenset({
    "epistemic_status",
    "importance_score",
    "retrieval_count",
    "last_retrieved_at",
    "created_at",
    "frozen",
    "is_masked",
    "decay_applied_at",
})


# ── Session reveals ───────────────────────────────────────────────────────────

class RevealSession:
    """
    Temporary, in-memory reveals — the console's answer to the original framing.

    VICTOR_ORIGINAL.md describes masked memory as "one recording only getting
    through when the user decides to call it". That is a *momentary* surfacing,
    not a state change. `victor unmask` permanently flips `is_masked` to False,
    which is a different act: it declassifies the node forever.

    A reveal surfaces one node's content for this console session only. Nothing
    is written to the graph, and the node is masked again on restart. This makes
    "call it up, look at it, let it go back under" possible, which the permanent
    flag alone cannot express.
    """

    def __init__(self) -> None:
        self._revealed: set[str] = set()
        self._lock = threading.Lock()

    def reveal(self, node_id: str) -> None:
        with self._lock:
            self._revealed.add(node_id)

    def conceal(self, node_id: str) -> None:
        with self._lock:
            self._revealed.discard(node_id)

    def is_revealed(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._revealed

    def all(self) -> List[str]:
        with self._lock:
            return sorted(self._revealed)

    def clear(self) -> int:
        with self._lock:
            n = len(self._revealed)
            self._revealed.clear()
            return n


# ── The API ───────────────────────────────────────────────────────────────────

class VictorAPI:
    """
    Everything the console can ask for, as plain dicts.

    Kept separate from the HTTP plumbing so it is directly unit-testable without
    binding a socket — the tests drive this class, not the server.
    """

    def __init__(self, victor, session: Optional[RevealSession] = None) -> None:
        self.v = victor
        self.session = session or RevealSession()

    # ── redaction ─────────────────────────────────────────────────────────────

    def _visible(self, node_id: str, meta: Dict[str, Any]) -> bool:
        """A node's content is visible if it isn't masked, or was revealed this session."""
        if not meta.get("is_masked", False):
            return True
        return self.session.is_revealed(node_id)

    def _redact(self, node_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a node dict safe to serialise to the browser.

        Structure always survives — id, type, degree, importance, edges. Only the
        label is withheld, and only while the node is masked and unrevealed. That
        split *is* the masked memory graph: relational anchors live, content dark.
        """
        meta = data.get("metadata", {}) or {}
        masked = bool(meta.get("is_masked", False))
        revealed = self.session.is_revealed(node_id)
        out = {
            "id": node_id,
            "ntype": data.get("ntype", "unknown"),
            "masked": masked,
            "revealed": revealed and masked,
            "frozen": bool(meta.get("frozen", False)),
            "epistemic_status": meta.get("epistemic_status"),
            "importance": round(float(meta.get("importance_score", 0.5)), 3),
            "retrieval_count": int(meta.get("retrieval_count", 0)),
            "last_retrieved_at": meta.get("last_retrieved_at"),
        }
        out["label"] = data.get("label", "") if self._visible(node_id, meta) else REDACTED
        return out

    def _redact_meta(self, node_id: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Strip content-bearing metadata from a masked node.

        Extractor output lives in the same dict as structural bookkeeping, so
        publishing raw metadata publishes the claim's substance even when the
        label is withheld. Only STRUCTURAL_META_KEYS survive; the count of
        dropped keys is reported so the console can say *that* something was
        withheld without saying what.
        """
        if self._visible(node_id, meta):
            return dict(meta)
        kept = {k: v for k, v in meta.items() if k in STRUCTURAL_META_KEYS}
        withheld = len(meta) - len(kept)
        if withheld:
            kept["_withheld_fields"] = withheld
        return kept

    # ── endpoints ─────────────────────────────────────────────────────────────

    def overview(self) -> Dict[str, Any]:
        """Headline numbers — what Victor currently holds and whether it can think."""
        g = self.v.graph
        stats = self.v.stats()

        status_counts: Dict[str, int] = {}
        masked = frozen = 0
        total_importance = 0.0
        retrievals = 0
        for _, data in g._g.nodes(data=True):
            meta = data.get("metadata", {}) or {}
            st = meta.get("epistemic_status")
            if st:
                status_counts[st] = status_counts.get(st, 0) + 1
            masked += bool(meta.get("is_masked", False))
            frozen += bool(meta.get("frozen", False))
            total_importance += float(meta.get("importance_score", 0.0))
            retrievals += int(meta.get("retrieval_count", 0))

        n = g._g.number_of_nodes()
        edges = g._g.number_of_edges()
        return {
            "nodes": n,
            "edges": edges,
            # Connection density is the compounding metric from VICTOR_THEORY_v1:
            # "value scales with the density of connections between them", not
            # with the raw artifact count. Edges per node makes that visible.
            "density": round(edges / n, 3) if n else 0.0,
            "by_type": stats["graph"]["by_type"],
            "by_epistemic_status": status_counts,
            "masked": masked,
            "frozen": frozen,
            "total_retrievals": retrievals,
            "mean_importance": round(total_importance / n, 3) if n else 0.0,
            "vectors": stats["vector_store"],
            "llm": {
                "online": stats["llm_online"],
                "model": stats["llm_model"],
                "openai_ready": stats["openai_ready"],
                "retriever": stats["retriever_type"],
                "tools": stats["tool_count"],
            },
        }

    def graph(
        self,
        limit: int = 600,
        ntype: Optional[str] = None,
        min_importance: float = 0.0,
        focus: Optional[str] = None,
        hops: int = 2,
    ) -> Dict[str, Any]:
        """
        A drawable slice of the graph, redacted.

        Edges are always returned in full even when both endpoints are masked —
        withholding them would destroy the one thing masked memory promises to
        keep: the relational anchors.

        At 100,000 nodes "the whole graph" is neither drawable nor meaningful,
        so the slice is chosen rather than truncated: `focus` restricts to one
        node's neighbourhood, `ntype`/`min_importance` filter, and whatever
        survives is ranked by importance before the cut.
        """
        g = self.v.graph._g
        total = g.number_of_nodes()

        if focus is not None and g.has_node(focus):
            scope = {focus} | {
                nid for nid, _, _ in self.v.graph.get_neighbors(focus, hops=hops)
            }
        else:
            focus = None
            scope = None

        # Rank on raw metadata before building a single redacted dict. The old
        # code built one per node and discarded 99.4% of them, which is why a
        # 100k-node graph cost 344 ms to draw.
        candidates: List[Tuple[float, str]] = []
        source = scope if scope is not None else g.nodes
        for nid in source:
            data = g.nodes[nid]
            if ntype and data.get("ntype") != ntype:
                continue
            meta = data.get("metadata") or {}
            imp = float(meta.get("importance_score", 0.5))
            if imp < min_importance:
                continue
            candidates.append((imp, nid))

        matched = len(candidates)
        truncated = matched > limit
        if truncated:
            candidates = heapq.nlargest(limit, candidates, key=lambda c: c[0])

        keep = {nid for _, nid in candidates}
        nodes = [self._redact(nid, g.nodes[nid]) for nid in keep]

        # Only an edge leaving a kept node can have both endpoints kept, so the
        # nbunch form visits O(kept x degree) edges rather than all of E.
        links = [
            {
                "source": s,
                "target": t,
                "etype": d.get("etype", "related"),
                "weight": round(float(d.get("weight", 1.0)), 3),
            }
            for s, t, d in g.out_edges(keep, data=True)
            if t in keep
        ]
        return {
            "nodes": nodes,
            "links": links,
            "truncated": truncated,
            "matched": matched,
            "total_nodes": total,
            "focus": focus,
        }

    # Sort keys the browse endpoint accepts. An allowlist because the value
    # arrives from a query string and is used to pick a metadata field.
    SORTS = {
        "importance": lambda m: float(m.get("importance_score", 0.0)),
        "retrievals": lambda m: int(m.get("retrieval_count", 0)),
        "recent": lambda m: str(m.get("last_retrieved_at") or ""),
        "created": lambda m: str(m.get("created_at") or ""),
    }

    def search(
        self,
        q: str = "",
        ntype: Optional[str] = None,
        status: Optional[str] = None,
        masked: Optional[bool] = None,
        mode: str = "text",
        sort: str = "importance",
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        Find nodes in a graph too large to look at. Paged, sorted, filtered.

        Masked nodes are matched on structure only — type, status, degree, id —
        never on their text. Substring-matching a query against withheld content
        would turn this endpoint into an oracle: ask for "palladium", see
        whether the masked node appears, and the mask has told you its contents
        one guess at a time. Structural facts are already published by the vault
        view, so exposing those costs nothing new.
        """
        g = self.v.graph._g
        needle = q.strip().lower()

        if mode == "semantic" and needle:
            # semantic_query already excludes masked nodes at the graph layer.
            ranked = self.v.graph.semantic_query(q, top_k=limit + offset)
            page = ranked[offset : offset + limit]
            return {
                "results": [
                    dict(self._redact(nid, data), score=round(score, 4))
                    for nid, score, data in page
                ],
                "total": len(ranked),
                "offset": offset,
                "limit": limit,
                "mode": "semantic",
                "note": "Semantic search never reaches masked nodes.",
            }

        keyfn = self.SORTS.get(sort, self.SORTS["importance"])
        hits: List[Tuple[Any, str]] = []
        for nid, data in g.nodes(data=True):
            meta = data.get("metadata") or {}
            is_masked = bool(meta.get("is_masked", False))
            if masked is not None and is_masked != masked:
                continue
            if ntype and data.get("ntype") != ntype:
                continue
            if status and meta.get("epistemic_status") != status:
                continue
            if needle:
                if is_masked and not self.session.is_revealed(nid):
                    continue
                if needle not in str(data.get("label", "")).lower():
                    continue
            hits.append((keyfn(meta), nid))

        hits.sort(key=lambda h: h[0], reverse=True)
        page = hits[offset : offset + limit]
        return {
            "results": [
                dict(
                    self._redact(nid, g.nodes[nid]),
                    degree=g.in_degree(nid) + g.out_degree(nid),
                )
                for _, nid in page
            ],
            "total": len(hits),
            "offset": offset,
            "limit": limit,
            "mode": "text",
            "note": (
                "Masked nodes are excluded from text matching — searching their "
                "content would leak it one query at a time."
                if needle
                else ""
            ),
        }

    def node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """One node in full: metadata, both edge directions, and neighbour labels."""
        detail = self.v.inspect(node_id)
        if detail is None:
            return None
        raw = self.v.graph.get_node(node_id) or {}
        out = self._redact(node_id, raw)
        out["metadata"] = self._redact_meta(node_id, detail.get("metadata", {}))
        out["degree_in"] = detail.get("degree_in", 0)
        out["degree_out"] = detail.get("degree_out", 0)

        def _edge(e: Dict[str, Any], key: str) -> Dict[str, Any]:
            other = e[key]
            odata = self.v.graph.get_node(other) or {}
            red = self._redact(other, odata)
            return {
                "id": other,
                "label": red["label"],
                "ntype": red["ntype"],
                "masked": red["masked"],
                "etype": e.get("etype"),
                "weight": e.get("weight", 1.0),
                "confidence": e.get("confidence"),
            }

        out["in_edges"] = [_edge(e, "from") for e in detail.get("in_edges", [])]
        out["out_edges"] = [_edge(e, "to") for e in detail.get("out_edges", [])]
        return out

    def masked(self) -> Dict[str, Any]:
        """
        The vault: every masked node as an anchor.

        Deliberately returns no labels for unrevealed nodes. `victor list-masked`
        prints 60 characters of each one; browsing the vault should not be a way
        to read the vault.
        """
        items = []
        for entry in self.v.list_masked():
            nid = entry["id"]
            red = self._redact(nid, entry)
            red["degree"] = (
                self.v.graph._g.in_degree(nid) + self.v.graph._g.out_degree(nid)
            )
            items.append(red)
        items.sort(key=lambda i: i["degree"], reverse=True)
        return {"masked": items, "count": len(items), "session_reveals": self.session.all()}

    def reveal(self, node_id: str) -> Dict[str, Any]:
        """Surface one masked node for this session only. Audited like an unmask."""
        node = self.v.graph.get_node(node_id)
        if node is None:
            return {"ok": False, "error": "no such node"}
        if not self.v.graph.node_is_masked(node_id):
            return {"ok": False, "error": "node is not masked"}
        self.session.reveal(node_id)
        # Reveals are logged on the same trail as permanent unmasks. A temporary
        # look at withheld content is still an access event.
        self.v._write_mask_audit("session-reveal", node_id, True)
        return {"ok": True, "node": self.node(node_id)}

    def conceal(self, node_id: str) -> Dict[str, Any]:
        """Drop a session reveal — the node goes back under without touching the graph."""
        self.session.conceal(node_id)
        self.v._write_mask_audit("session-conceal", node_id, True)
        return {"ok": True}

    def set_mask(self, node_id: str, masked: bool) -> Dict[str, Any]:
        """Permanently mask or unmask. This writes to the graph; reveal does not."""
        ok = self.v.mask(node_id) if masked else self.v.unmask(node_id)
        if ok and not masked:
            self.session.conceal(node_id)
        return {"ok": bool(ok), "masked": masked}

    def audit(self, limit: int = 200) -> Dict[str, Any]:
        """The mask/unmask/reveal trail, newest first."""
        path = Path(self.v.config.unmask_audit_log_file)
        if not path.exists():
            return {"entries": [], "count": 0}
        entries: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        entries.reverse()
        return {"entries": entries[:limit], "count": len(entries)}

    def gaps(self, min_importance: float = 0.0) -> Dict[str, Any]:
        """Claims with no experimental confirmation — Victor's research agenda."""
        out = []
        for g in self.v.gaps(min_importance=min_importance):
            node = self.v.graph.get_node(g.claim_id) or {}
            meta = node.get("metadata", {}) or {}
            visible = self._visible(g.claim_id, meta)
            out.append({
                "claim_id": g.claim_id,
                "claim_text": g.claim_text if visible else REDACTED,
                "masked": bool(meta.get("is_masked", False)),
                "epistemic_status": g.epistemic_status,
                "confidence": round(g.confidence, 3),
                "n_confirms": g.n_confirms,
                "n_contradicts": g.n_contradicts,
                "n_inconclusive": g.n_inconclusive,
                "importance": round(float(meta.get("importance_score", 0.0)), 3),
            })
        return {"gaps": out, "count": len(out)}

    def ask(self, query: str) -> Dict[str, Any]:
        """Run a full query and return the answer with its provenance intact."""
        answer = self.v.ask_full(query)
        chunks = []
        for c in answer.retrieved_chunks:
            chunks.append({
                "text": c.text,
                "source_id": c.source_id,
                "source_type": getattr(c.source_type, "value", str(c.source_type)),
                "source_title": c.source_title,
                "score": round(float(c.score), 4),
                "epistemic_status": c.epistemic_status,
                "provenance": list(getattr(c, "provenance", []) or []),
                # A chunk is a masked anchor if the retriever produced it for a
                # node whose content is withheld. Surfacing this lets the console
                # show "3 of 8 sources are masked" — the honest state of an answer
                # built on partially dark memory.
                "masked_anchor": c.epistemic_status == "masked",
            })
        return {
            "answer": answer.answer,
            "provenance_summary": answer.provenance_summary,
            "provider": answer.provider_used,
            "no_context": answer.no_context,
            "cited_sources": list(answer.cited_sources or []),
            "chunks": chunks,
            "asked_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── the machine ───────────────────────────────────────────────────────────

    def deliberate(
        self,
        query: str,
        budget: int = 3,
        sensors: int = 0,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Run one referral pass and return the whole trace.

        This is the `ask` endpoint's opposite. `ask` retrieves five chunks by
        cosine distance and hands them to a model that then explains whatever
        arrived; masked memory shows up in the context as an inert anchor the
        model can read about but not act on. Here the machine is handed a table
        of *handles* — what each piece of memory is, never what it says — and it
        spends a budget: one handle at a time, each with a stated reason, each
        request answered with a grant or a refusal, all of it recorded.

        The point of surfacing this in the console is that the deliberation is
        the machine's, not the operator's. Nobody clicks "reveal". The machine
        reaches the masked node, asks for it, is told no, and says so in its
        conclusion. What the operator sees is what Victor would do at 3am on a
        rig with nobody watching.

        `sensors` runs that many ticks of the robot scenario on a throwaway
        graph first and offers the freshest readings into the same table, so a
        live observation and a six-month-old paper compete on equal terms.
        """
        from .referral import DeliberateReasoner, PolicyChooser, ReferralDesk, summarise

        query = (query or "").strip()
        budget = max(1, min(8, int(budget or 3)))

        sensor_block: Optional[Dict[str, Any]] = None
        fragments: List[Any] = []
        if sensors > 0:
            sensor_block, fragments = self._sensor_fragments(int(sensors))

        desk = ReferralDesk(
            self.v.graph,
            vector_store=getattr(self.v, "vector_store", None),
            # Session reveals are the only authority. The default is refuse-all;
            # a reasoning pass that could silently unmask would not be a trust
            # boundary, it would be a delay.
            authority=self.session.is_revealed,
            budget=budget,
            ledger_path=Path(self.v.graph.graph_file).parent / "referral_ledger.jsonl",
        )

        llm = getattr(self.v, "llm", None) if use_llm else None
        if llm is not None and not getattr(llm, "is_available", lambda: False)():
            llm = None
        # No model available is the normal field case, not a degraded one: the
        # policy chooser decides from the handles alone.
        reasoner = DeliberateReasoner(
            desk, llm=llm, chooser=None if llm else PolicyChooser()
        )
        result = reasoner.run(query, fragments=fragments)

        return {
            "deliberation": result.as_dict(),
            "rendered": result.table.render(),
            "summary": summarise(result),
            "chose_by": "language model" if llm else "policy (no model available)",
            "sensors": sensor_block,
            "revealed_this_session": self.session.all(),
            "at": datetime.now(timezone.utc).isoformat(),
        }

    def _sensor_fragments(self, ticks: int) -> Tuple[Dict[str, Any], List[Any]]:
        """
        Run the robot scenario on a scratch graph and return its live readings.

        A scratch graph, emphatically: the console must be able to demonstrate
        the machine without writing simulated observations into the user's real
        knowledge base. The embedder is shared because loading a second copy of
        the model would cost more than the whole simulation.
        """
        import tempfile

        from .graph import VictorKnowledgeGraph
        from .simulation import STRANDED_SITE, Simulation

        ticks = max(1, min(40, ticks))
        with tempfile.TemporaryDirectory(prefix="victor-machine-") as tmp:
            scratch = VictorKnowledgeGraph(Path(tmp) / "sim.json", self.v.embedder)
            sim = Simulation(scratch, STRANDED_SITE, seed=7, save_dir=Path(tmp) / "frames")
            sim.run(ticks=ticks)
            fragments = sim.fragments()
            block = {
                "scenario": STRANDED_SITE.name,
                "ticks": ticks,
                "report": sim.report(),
                "readings": [
                    {
                        "id": f.fragment_id,
                        "source": f.source,
                        "confidence": round(f.confidence, 3),
                        "masked": f.masked,
                        # The reading itself only when it is not sensitive. A
                        # panel that prints what the referral table withholds
                        # would undo the table two divs away.
                        "text": REDACTED if f.masked else f.text,
                    }
                    for f in fragments
                ],
            }
        return block, fragments

    def patterns(self) -> Dict[str, Any]:
        """What Victor has noticed about how it's being used."""
        base = self.v.patterns()
        digest = self.v.get_pattern_digest()
        return {"patterns": base, "digest": digest}

    def activity(self, limit: int = 40) -> Dict[str, Any]:
        """
        A reverse-chronological feed of what has actually been done with Victor.

        Built from `last_retrieved_at`, which every node gets on creation and on
        each retrieval — the closest thing the graph has to a timeline.
        """
        rows = []
        for nid, data in self.v.graph._g.nodes(data=True):
            meta = data.get("metadata", {}) or {}
            ts = meta.get("last_retrieved_at")
            if not ts:
                continue
            red = self._redact(nid, data)
            rows.append({
                "id": nid,
                "label": red["label"],
                "ntype": red["ntype"],
                "masked": red["masked"],
                "at": ts,
                "retrieval_count": red["retrieval_count"],
            })
        rows.sort(key=lambda r: r["at"], reverse=True)
        return {"activity": rows[:limit], "count": len(rows)}


# ── HTTP plumbing ─────────────────────────────────────────────────────────────

def _make_handler(api: VictorAPI):
    routes: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    def _json_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
        length = int(handler.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(handler.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Victor"
        sys_version = ""

        # ── helpers ───────────────────────────────────────────────────────────

        def _send(self, code: int, payload: Any, ctype: str = "application/json") -> None:
            if ctype == "application/json":
                body = json.dumps(payload, default=str).encode("utf-8")
            else:
                body = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            # The console is single-user and localhost-only; caching a stale
            # graph would make the compounding view silently wrong.
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _static(self, rel: str) -> None:
            rel = rel.lstrip("/") or "index.html"
            target = (WEBUI_DIR / rel).resolve()
            # Path traversal guard: the resolved path must stay inside WEBUI_DIR.
            if not str(target).startswith(str(WEBUI_DIR.resolve())) or not target.is_file():
                self._send(404, {"error": "not found"})
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, target.read_bytes(), ctype)

        # ── verbs ─────────────────────────────────────────────────────────────

        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's contract
            parsed = urlparse(self.path)
            path = parsed.path
            params = _parse_query(parsed.query)
            try:
                if not path.startswith("/api/"):
                    self._static(path)
                    return
                self._send(*_dispatch_get(api, path, params))
            except Exception as exc:  # keep the console alive on any single bad call
                logger.error("GET %s failed: %s\n%s", path, exc, traceback.format_exc())
                self._send(500, {"error": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = _json_body(self)
                self._send(*_dispatch_post(api, path, body))
            except Exception as exc:
                logger.error("POST %s failed: %s\n%s", path, exc, traceback.format_exc())
                self._send(500, {"error": str(exc)})

        def log_message(self, fmt: str, *args: Any) -> None:
            # BaseHTTPRequestHandler logs every request to stderr by default,
            # which drowns the "serving on ..." line users actually need.
            logger.debug("%s - %s", self.address_string(), fmt % args)

    return Handler


def _parse_query(qs: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in qs.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        out[unquote(k)] = unquote(v.replace("+", " "))
    return out


def _clamp_int(params: Dict[str, str], key: str, default: int, lo: int, hi: int) -> int:
    """
    Query-string integers are attacker-controlled even on localhost — a stray
    `?limit=100000000` should not ask the server to build a hundred million
    dicts. Unparseable values fall back to the default rather than 500.
    """
    try:
        return max(lo, min(hi, int(params.get(key, default))))
    except (TypeError, ValueError):
        return default


def _body_int(body: Dict[str, Any], key: str, default: int, lo: int, hi: int) -> int:
    """`_clamp_int` for JSON bodies, where the value arrives as int, str or junk."""
    try:
        return max(lo, min(hi, int(body.get(key, default))))
    except (TypeError, ValueError):
        return default


def _opt_bool(params: Dict[str, str], key: str) -> Optional[bool]:
    raw = params.get(key)
    if raw is None or raw == "":
        return None
    return raw.lower() in ("1", "true", "yes")


def _dispatch_get(api: VictorAPI, path: str, params: Dict[str, str]) -> Tuple[int, Any]:
    if path == "/api/overview":
        return 200, api.overview()
    if path == "/api/graph":
        return 200, api.graph(
            limit=_clamp_int(params, "limit", 600, 1, 5000),
            ntype=params.get("ntype") or None,
            min_importance=float(params.get("min_importance", 0.0) or 0.0),
            focus=params.get("focus") or None,
            hops=_clamp_int(params, "hops", 2, 1, 4),
        )
    if path == "/api/search":
        return 200, api.search(
            q=params.get("q", ""),
            ntype=params.get("ntype") or None,
            status=params.get("status") or None,
            masked=_opt_bool(params, "masked"),
            mode=params.get("mode", "text"),
            sort=params.get("sort", "importance"),
            limit=_clamp_int(params, "limit", 50, 1, 500),
            offset=_clamp_int(params, "offset", 0, 0, 10_000_000),
        )
    if path == "/api/masked":
        return 200, api.masked()
    if path == "/api/audit":
        return 200, api.audit(limit=int(params.get("limit", 200)))
    if path == "/api/gaps":
        return 200, api.gaps(min_importance=float(params.get("min_importance", 0.0)))
    if path == "/api/patterns":
        return 200, api.patterns()
    if path == "/api/activity":
        return 200, api.activity(limit=int(params.get("limit", 40)))
    if path.startswith("/api/node/"):
        node = api.node(unquote(path[len("/api/node/"):]))
        return (200, node) if node else (404, {"error": "no such node"})
    return 404, {"error": "unknown endpoint"}


def _dispatch_post(api: VictorAPI, path: str, body: Dict[str, Any]) -> Tuple[int, Any]:
    if path == "/api/ask":
        query = (body.get("query") or "").strip()
        if not query:
            return 400, {"error": "query is required"}
        return 200, api.ask(query)
    if path == "/api/deliberate":
        query = (body.get("query") or "").strip()
        if not query:
            return 400, {"error": "query is required"}
        return 200, api.deliberate(
            query,
            budget=_body_int(body, "budget", 3, 1, 8),
            sensors=_body_int(body, "sensors", 0, 0, 40),
            use_llm=bool(body.get("llm")),
        )
    if path == "/api/reveal":
        return 200, api.reveal(body.get("node_id", ""))
    if path == "/api/conceal":
        return 200, api.conceal(body.get("node_id", ""))
    if path == "/api/mask":
        return 200, api.set_mask(body.get("node_id", ""), True)
    if path == "/api/unmask":
        return 200, api.set_mask(body.get("node_id", ""), False)
    return 404, {"error": "unknown endpoint"}


def serve(victor, host: str = "127.0.0.1", port: int = 8420) -> None:
    """Run the console until interrupted. Blocks."""
    api = VictorAPI(victor)
    httpd = ThreadingHTTPServer((host, port), _make_handler(api))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
