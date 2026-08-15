"""
Victor Tool Registry — Step 1 of agent loop implementation.

Exposes reasoning modules (ConflictDetector, GapDetector, EvidenceWeighter,
graph traversal) as structured tools the LLM can invoke mid-answer.

Design:
  - Each tool has a JSON-schema-like signature the LLM sees in its prompt
  - ToolExecutor routes parsed LLM tool calls to the actual Python methods
  - All tool output is JSON-serializable so the LLM can consume it
  - New tools are registered by adding them to TOOL_REGISTRY — no changes
    to the agent loop required
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .graph import VictorKnowledgeGraph
    from .reasoning import ConflictDetector, EvidenceWeighter, GapDetector
    from .embedder import LocalEmbedder


# ──────────────────────────────────────────────────────────────────────────────
# Tool schema definitions  (what the LLM sees)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolParam:
    name:        str
    ptype:       str   # "string" | "number" | "boolean"
    description: str
    required:    bool  = True


@dataclass
class Tool:
    name:        str
    description: str
    params:      List[ToolParam] = field(default_factory=list)
    _fn:         Optional[Callable] = field(default=None, repr=False)

    def to_prompt_block(self) -> str:
        """Render tool signature for inclusion in the LLM system prompt."""
        lines = [
            f'  {{"name": "{self.name}",',
            f'   "description": "{self.description}",',
            '   "parameters": {',
        ]
        for p in self.params:
            req_flag = " (required)" if p.required else " (optional)"
            lines.append(
                f'     "{p.name}": {{"type": "{p.ptype}", '
                f'"description": "{p.description}{req_flag}"}}'
            )
        lines.append("   }}")
        lines.append("  }")
        return "\n".join(lines)

    def execute(self, **kwargs) -> Dict[str, Any]:
        if self._fn is None:
            return {"error": f"Tool '{self.name}' has no implementation"}
        try:
            result = self._fn(**kwargs)
            return {"tool": self.name, "result": result}
        except Exception as exc:
            return {"tool": self.name, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# Tool implementations  (what actually runs)
# ──────────────────────────────────────────────────────────────────────────────

class _ToolImplementations:
    """Holds references to Victor's reasoning modules and graph.
    Passed to ToolRegistry at init time.
    """

    def __init__(
        self,
        graph: VictorKnowledgeGraph,
        conflict_detector: ConflictDetector,
        weighter: EvidenceWeighter,
        gap_detector: GapDetector,
        embedder: LocalEmbedder,
    ):
        self.graph = graph
        self.conflict_detector = conflict_detector
        self.weighter = weighter
        self.gap_detector = gap_detector
        self.embedder = embedder

    # ── Conflict tools ────────────────────────────────────────────────────

    def judge_conflict(self, claim_text: str, result_text: str) -> Dict[str, Any]:
        """Use the LLM to judge whether an experiment result confirms,
        contradicts, or is inconclusive with respect to a claim."""
        result = self.conflict_detector.judge(claim_text, result_text)
        return {
            "direction":  result.direction,
            "confidence": result.confidence,
            "reason":     result.reason,
        }

    # ── Evidence tools ────────────────────────────────────────────────────

    def summarize_claim_evidence(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Return the weighted evidence summary for a claim node.

        Masking enforcement: if the claim node is masked, return an anchor
        instead of the real claim_text.  Evidence counts (n_confirms, etc.)
        are withheld too — they could indirectly disclose what the node says.
        The LLM only sees the anchor; the researcher can use
        `victor unmask <node_id>` to restore full access.
        """
        if self.graph.node_is_masked(claim_id):
            node_data = self.graph.get_node(claim_id) or {}
            anchor = self._anchor_for(claim_id, node_data)
            anchor["claim_id"] = claim_id   # shape-consistent key for callers
            return anchor
        summary = self.weighter.summarize_claim(claim_id)
        if summary is None:
            return None
        return {
            "claim_id":         summary.claim_id,
            "claim_text":       summary.claim_text,
            "epistemic_status": summary.epistemic_status,
            "confidence":       summary.confidence,
            "n_confirms":       summary.n_confirms,
            "n_contradicts":    summary.n_contradicts,
            "n_inconclusive":   summary.n_inconclusive,
            "supporting_experiments":  summary.supporting_experiments,
            "conflicting_experiments": summary.conflicting_experiments,
            "is_gap":           summary.gap,
        }

    def check_claims_in_context(self, claim_ids: List[str]) -> List[Dict[str, Any]]:
        """Summarize evidence for multiple claims at once."""
        results = []
        for cid in claim_ids:
            s = self.summarize_claim_evidence(cid)
            if s:
                results.append(s)
        return results

    # ── Gap tools ─────────────────────────────────────────────────────────

    def find_research_gaps(self, min_importance: float = 0.0) -> List[Dict[str, Any]]:
        """Find claims with no experimental confirmation.

        Masking enforcement: masked claim nodes are returned as anchors so
        the LLM cannot infer what the node says from its gap-list position.
        """
        gaps = self.gap_detector.find_gaps(min_importance=min_importance)
        out = []
        for g in gaps[:10]:
            if self.graph.node_is_masked(g.claim_id):
                node_data = self.graph.get_node(g.claim_id) or {}
                anchor = self._anchor_for(g.claim_id, node_data)
                anchor["claim_id"] = g.claim_id   # shape-consistent key
                out.append(anchor)
                continue
            out.append({
                "claim_id":         g.claim_id,
                "claim_text":       g.claim_text,
                "epistemic_status": g.epistemic_status,
                "n_contradicts":    g.n_contradicts,
                "confidence":       g.confidence,
            })
        return out

    # ── Graph traversal tools ─────────────────────────────────────────────
    #
    # Masking enforcement: these tools are LLM-facing (the agent loop calls
    # them mid-answer), so they sit on the same trust boundary as
    # retrieve.py — masked nodes must never surface real content here
    # either. Without this check, the agent loop is a complete bypass of
    # masked memory: an anchor chunk from retrieve() hands the LLM a
    # node_id ("...Use 'victor unmask {node_id}' to reveal"), and the LLM
    # could then call get_node_details(node_id) and read the full content
    # without the user ever running `victor unmask`. Same anchor shape as
    # retrieve.py's _make_anchor, so a masked node looks identical whether
    # it was hit via vector/graph retrieval or via a tool call.

    def _anchor_for(self, node_id: str, node_data: Dict[str, Any]) -> Dict[str, Any]:
        ntype = node_data.get("ntype", "node")
        return {
            "node_id":   node_id,
            "type":      ntype,
            "is_masked": True,
            "message": (
                f"[MASKED — {ntype} — content withheld. "
                f"Use 'victor unmask {node_id[:16]}' to reveal.]"
            ),
        }

    def get_node_details(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return full details of a graph node including edges."""
        if self.graph.node_is_masked(node_id):
            node_data = self.graph.get_node(node_id) or {}
            return self._anchor_for(node_id, node_data)
        return self.graph.inspect_node(node_id)

    def find_related_nodes(self, node_id: str, hops: int = 2) -> List[Dict[str, Any]]:
        """Find nodes reachable within N hops from a starting node."""
        neighbors = self.graph.get_neighbors(node_id, hops=hops)
        out = []
        for nbr_id, nbr_data, etype in neighbors:
            if self.graph.node_is_masked(nbr_id):
                anchor = self._anchor_for(nbr_id, nbr_data)
                anchor["relation"] = etype
                out.append(anchor)
                continue
            out.append({
                "node_id":  nbr_id,
                "label":    nbr_data.get("label", ""),
                "type":     nbr_data.get("ntype", ""),
                "relation": etype,
            })
        return out

    def search_nodes_by_text(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic search over graph nodes (not vector chunks)."""
        results = self.graph.semantic_query(query, top_k=top_k)
        out = []
        for nid, score, node_data in results:
            if self.graph.node_is_masked(nid):
                anchor = self._anchor_for(nid, node_data)
                anchor["score"] = round(float(score), 4)
                out.append(anchor)
                continue
            out.append({
                "node_id":  nid,
                "label":    node_data.get("label", ""),
                "type":     node_data.get("ntype", ""),
                "score":    round(float(score), 4),
            })
        return out

    def get_claims_for_source(self, source_id: str) -> List[Dict[str, Any]]:
        """Get all claims made by a given paper/note source."""
        from .models import EdgeType
        claims = []
        for src, dst, data in self.graph._g.edges(data=True):
            if src == source_id and data.get("etype") == EdgeType.MAKES_CLAIM:
                node = self.graph.get_node(dst)
                if node:
                    if self.graph.node_is_masked(dst):
                        anchor = self._anchor_for(dst, node)
                        anchor["claim_id"] = dst
                        claims.append(anchor)
                        continue
                    claims.append({
                        "claim_id": dst,
                        "text": node.get("label", ""),
                        "epistemic_status": node.get("metadata", {}).get(
                            "epistemic_status", "literature"
                        ),
                    })
        return claims


# ──────────────────────────────────────────────────────────────────────────────
# Tool Registry  (singleton per Victor instance)
# ──────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Holds all tools and can execute them by name.
    Constructed once in Victor.__init__ and passed to the agent loop.
    """

    def __init__(self, impl: _ToolImplementations):
        self.impl = impl
        self._tools: Dict[str, Tool] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register the standard set of reasoning tools."""
        self.register(Tool(
            name="judge_conflict",
            description=(
                "Determine whether an experiment result CONFIRMS, CONTRADICTS, "
                "or is INCONCLUSIVE with respect to a scientific claim. "
                "Use this when you have a claim and an experiment result and need "
                "to know their relationship."
            ),
            params=[
                ToolParam("claim_text",  "string", "The claim text to evaluate"),
                ToolParam("result_text", "string", "The experiment result text"),
            ],
            _fn=self.impl.judge_conflict,
        ))

        self.register(Tool(
            name="summarize_claim_evidence",
            description=(
                "Get the full evidence summary for a specific claim node: "
                "how many experiments confirm/contradict it, weighted confidence, "
                "and whether it is a gap. Use when citing a claim to know its evidentiary status."
            ),
            params=[
                ToolParam("claim_id", "string", "The graph node ID of the claim"),
            ],
            _fn=self.impl.summarize_claim_evidence,
        ))

        self.register(Tool(
            name="check_claims_in_context",
            description=(
                "Batch version of summarize_claim_evidence. "
                "Check the evidentiary status of multiple claims at once. "
                "Use after retrieving several claims to quickly assess which are well-supported."
            ),
            params=[
                ToolParam("claim_ids", "string", (
                    "JSON array of claim node IDs, e.g. [\"claim_abc\", \"claim_def\"]"
                )),
            ],
            _fn=self.impl.check_claims_in_context,
        ))

        self.register(Tool(
            name="find_research_gaps",
            description=(
                "Find claims in the knowledge graph that have NO experimental confirmation. "
                "Returns up to 10 highest-priority gaps sorted by importance. "
                "Use when the user asks what is missing or what experiments to run next."
            ),
            params=[
                ToolParam("min_importance", "number", (
                    "Only return gaps at or above this importance score (0.0–1.0). "
                    "Default 0.0 returns all gaps."
                ), required=False),
            ],
            _fn=self.impl.find_research_gaps,
        ))

        self.register(Tool(
            name="get_node_details",
            description=(
                "Get full structured details of any graph node by its ID, "
                "including all incoming/outgoing edges and metadata. "
                "Use when you need to inspect a specific node the user mentions."
            ),
            params=[
                ToolParam("node_id", "string", "The graph node ID to inspect"),
            ],
            _fn=self.impl.get_node_details,
        ))

        self.register(Tool(
            name="find_related_nodes",
            description=(
                "Find nodes connected to a given node within N hops in the knowledge graph. "
                "Use to expand context around a claim, paper, or experiment."
            ),
            params=[
                ToolParam("node_id", "string", "The starting node ID"),
                ToolParam("hops", "number", "Number of hops (1 or 2 recommended). Default 2.", required=False),
            ],
            _fn=self.impl.find_related_nodes,
        ))

        self.register(Tool(
            name="search_nodes_by_text",
            description=(
                "Semantic search over graph nodes (papers, claims, experiments, concepts) "
                "using their embeddings. Returns the top-k most similar nodes. "
                "Use when you need to find relevant nodes beyond what vector retrieval returned."
            ),
            params=[
                ToolParam("query", "string", "The search query text"),
                ToolParam("top_k", "number", "Number of results. Default 5.", required=False),
            ],
            _fn=self.impl.search_nodes_by_text,
        ))

        self.register(Tool(
            name="get_claims_for_source",
            description=(
                "Get all claims extracted from a specific paper or note source. "
                "Use when the user asks about a specific document's claims."
            ),
            params=[
                ToolParam("source_id", "string", "The source document node ID"),
            ],
            _fn=self.impl.get_claims_for_source,
        ))

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def tool_descriptions_for_prompt(self) -> str:
        """Render all tool signatures for inclusion in the LLM system prompt."""
        blocks = [t.to_prompt_block() for t in self._tools.values()]
        return "\n\n".join(blocks)

    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name with the given arguments.
        Returns a dict the LLM can consume.
        """
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool: '{name}'. "
                            f"Available: {list(self._tools.keys())}"}

        # Parse JSON-encoded list parameters
        for key, val in list(arguments.items()):
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, (list, dict)):
                        arguments[key] = parsed
                except (json.JSONDecodeError, TypeError):
                    pass

        # Convert numeric strings
        for key, val in list(arguments.items()):
            if isinstance(val, str):
                try:
                    if "." in val:
                        arguments[key] = float(val)
                    else:
                        arguments[key] = int(val)
                except ValueError:
                    pass

        return tool.execute(**arguments)

    def execute_from_llm_json(self, raw_json: str) -> Dict[str, Any]:
        """
        Parse a tool call from LLM output and execute it.
        Expects: {"tool": "name", "arguments": {...}}
        """
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            import re
            match = re.search(r"\{.*\}", raw_json, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    return {"error": "Invalid JSON in tool call", "raw": raw_json}
            else:
                return {"error": "Invalid JSON in tool call", "raw": raw_json}

        name = parsed.get("tool") or parsed.get("name")
        arguments = parsed.get("arguments") or parsed.get("args") or parsed.get("params", {})
        if name is None:
            return {"error": "No tool name found in JSON", "parsed": parsed}
        return self.execute(name, arguments)
