"""
Scale harness — where does Victor stop being usable?

Every number Victor has ever reported about itself came from a graph of a few
dozen nodes. "421 tests pass" says nothing about behaviour at 20,000 artifacts,
and the compounding thesis in VICTOR_THEORY_v1 only pays off if a graph is
allowed to grow for months. This measures the four operations that sit on the
critical path of every user action, at sizes a real user would reach.

    python tools/bench_scale.py                 # 1k, 5k, 20k
    python tools/bench_scale.py 1000 50000      # explicit sizes

Uses a deterministic hash-seeded embedder rather than sentence-transformers:
the goal is to time Victor's own code, not a model download. Vectors are
unit-normalised, exactly as LocalEmbedder produces them.
"""
from __future__ import annotations

import gc
import json
import random
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from victor.graph import VictorKnowledgeGraph  # noqa: E402
from victor.models import NodeType, EdgeType  # noqa: E402

DIM = 384
NTYPES = [
    NodeType.CLAIM, NodeType.CONCEPT, NodeType.PAPER,
    NodeType.EXPERIMENT, NodeType.OBSERVATION, NodeType.NOTE,
]


class FakeEmbedder:
    """Deterministic unit vectors, no model load. Same contract as LocalEmbedder."""

    model_name = "fake-hash-384"

    def embed(self, text: str) -> list[float]:
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(DIM)
        return (v / np.linalg.norm(v)).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    @staticmethod
    def cosine(a, b) -> float:
        from victor.embedder import LocalEmbedder

        return LocalEmbedder.cosine(a, b)


def timed(fn):
    gc.collect()
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def build(graph: VictorKnowledgeGraph, n: int, seed: int = 7) -> None:
    """A graph shaped like a real one: ~1.4 edges/node, mixed types, 8% masked."""
    rng = random.Random(seed)
    ids = []
    for i in range(n):
        nid = f"n{i:06d}"
        ntype = NTYPES[i % len(NTYPES)]
        graph.add_node(
            nid,
            ntype,
            f"Artifact {i}: measured effect of condition {i % 97} on outcome {i % 31}",
        )
        ids.append(nid)

    for i, nid in enumerate(ids):
        for _ in range(1 if i % 3 else 2):
            other = ids[rng.randrange(n)]
            if other != nid:
                graph.add_edge(nid, other, EdgeType.RELATED_TO)

    for nid in rng.sample(ids, k=max(1, n // 12)):
        graph.mask_node(nid)


def bench(n: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"victor_bench_{n}_"))
    try:
        gf = tmp / "graph.json"
        emb = FakeEmbedder()

        g = VictorKnowledgeGraph(gf, emb)
        t_build, _ = timed(lambda: build(g, n))
        t_save, _ = timed(g.save)
        size_mb = gf.stat().st_size / 1e6

        del g
        t_load, g2 = timed(lambda: VictorKnowledgeGraph(gf, emb))

        qs = [f"effect of condition {i} on outcome" for i in range(5)]
        # Warm once: the first query pays for whatever lazy state exists, and
        # including it would report setup cost as query cost.
        g2.semantic_query(qs[0], top_k=10)
        lat = [timed(lambda q=q: g2.semantic_query(q, top_k=10))[0] for q in qs]

        t_neigh, _ = timed(lambda: g2.get_neighbors(f"n{n // 2:06d}", hops=2))

        from victor.web import VictorAPI

        class _V:
            """Minimum surface VictorAPI touches — no LLM, no vector store."""

            graph = g2
            vector_store = None
            config = None

            def stats(self):
                return {
                    "graph": self.graph.stats(),
                    "vector_store": {"count": 0},
                    "llm_online": False,
                    "llm_model": "none",
                    "openai_ready": False,
                    "retriever_type": "none",
                    "tool_count": 0,
                }

        api = VictorAPI(_V())
        t_over, _ = timed(api.overview)
        t_graph, _ = timed(lambda: api.graph(limit=600))

        return {
            "nodes": n,
            "edges": g2._g.number_of_edges(),
            "build_s": t_build,
            "save_s": t_save,
            "load_s": t_load,
            "json_mb": size_mb,
            "query_ms": statistics.median(lat) * 1000,
            "neighbors_ms": t_neigh * 1000,
            "api_overview_ms": t_over * 1000,
            "api_graph_ms": t_graph * 1000,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


HEADERS = [
    ("nodes", "nodes", "{:>7,}"),
    ("edges", "edges", "{:>7,}"),
    ("build_s", "build s", "{:>8.2f}"),
    ("save_s", "save s", "{:>8.2f}"),
    ("load_s", "load s", "{:>8.2f}"),
    ("json_mb", "json MB", "{:>8.1f}"),
    ("query_ms", "query ms", "{:>9.1f}"),
    ("neighbors_ms", "2hop ms", "{:>8.1f}"),
    ("api_overview_ms", "overview ms", "{:>12.1f}"),
    ("api_graph_ms", "api graph ms", "{:>13.1f}"),
]


def main(argv: list[str]) -> int:
    sizes = [int(a) for a in argv] or [1000, 5000, 20000]
    rows = []
    for n in sizes:
        print(f"  running n={n:,} ...", file=sys.stderr, flush=True)
        rows.append(bench(n))

    print()
    print("".join(h.rjust(len(f.format(0))) for _, h, f in HEADERS))
    for r in rows:
        print("".join(f.format(r[k]) for k, _, f in HEADERS))
    print()
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
