"""
HybridRetriever — v4  +  AgenticRetriever — Step 2

Changes from v3:
  - Weighted scoring: score = 0.7 × cosine_similarity + 0.3 × importance_score
  - EpistemicStatus surfaced on every RetrievedChunk from graph node metadata
  - graph.record_retrieval() called for every contributing node
  - Temporal decay applied at the start of each retrieve() call (F-014)
  - Conversation memory: every answered query stored as CONVERSATION node

AgenticRetriever (new — Step 2 of PRD Section 7):
  - Retrieve → Reason → Review → Respond loop (replaces single-shot)
  - LLM can call tools mid-answer: judge_conflict, summarize_claim_evidence,
    find_research_gaps, search_nodes_by_text, find_related_nodes, etc.
  - Bounded: max 5 tool calls, explicit token ceiling, explicit stop condition
  - Automatic Review: ConflictDetector runs on conflicting claims
"""
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime, timezone
import hashlib
import json
import logging
import re

logger = logging.getLogger(__name__)

from .models import (
    RetrievedChunk, VictorAnswer, NodeType,
    EpistemicStatus, ConversationTurn,
)
from .vector_store import VictorVectorStore
from .graph import VictorKnowledgeGraph
from .llm import OllamaClient


_COSINE_WEIGHT     = 0.7
_IMPORTANCE_WEIGHT = 0.3


def _estimate_tokens(text: str) -> int:
    """Rough token estimate — actual tokenizers vary but this is closer than word count."""
    return int(len(text.split()) * 1.3)


def _ep_badge(chunk: RetrievedChunk) -> str:
    """
    Render the epistemic-status badge for one context line.

    Tolerates a missing status rather than raising. The badge is cosmetic;
    a chunk without a tier must never be able to break answer assembly.
    """
    return f"[{(chunk.epistemic_status or 'unknown').upper()}]"


ANSWER_PROMPT = """\
You are a research assistant with access to a curated knowledge base.
Answer the question using ONLY the context provided below.
Be precise. Cite which source each key fact comes from.
Include the epistemic status of evidence when relevant \
(MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS).
If the context doesn't contain enough information, say so clearly.

Context:
{context}

Question: {question}

Answer:"""


# ═══════════════════════════════════════════════════════════════════════════════
#  HybridRetriever — original v4 single-shot pipeline (preserved)
# ═══════════════════════════════════════════════════════════════════════════════

class HybridRetriever:
    def __init__(
        self,
        vector_store:       VictorVectorStore,
        graph:              VictorKnowledgeGraph,
        llm:                OllamaClient,
        top_k:              int  = 8,
        graph_hop:          int  = 2,
        decay_on_retrieve:  bool = True,
    ):
        self.vs               = vector_store
        self.graph            = graph
        self.llm              = llm
        self.top_k            = top_k
        self.graph_hop        = graph_hop
        self.decay_on_retrieve = decay_on_retrieve

    # ── Main retrieval ────────────────────────────────────────────────────────

    def retrieve(self, query: str) -> List[RetrievedChunk]:
        """Hybrid retrieval: vector + graph expansion with weighted scoring.

        Masked memory enforcement (scope-before-routing):
        - Masked nodes still participate in graph routing and edge traversal.
          ConflictDetector and GapDetector see the full graph — masking never
          breaks the structural layer.
        - At content assembly time, masked nodes are replaced by anchor chunks.
          An anchor preserves referential presence ("something exists here, score
          deprioritised") while withholding content from the LLM context.
        - This is decoupled enforcement (SD-RAG principle): controls are applied
          here in retrieve(), not in the prompt or at generation time.
        """
        if self.decay_on_retrieve:
            self.graph.apply_temporal_decay()

        seen: Dict[str, RetrievedChunk] = {}

        # Step 1: vector search
        for c in self.vs.query(query, top_k=self.top_k):
            importance = self._node_importance(c.source_id, c.source_type)
            blended    = _COSINE_WEIGHT * c.score + _IMPORTANCE_WEIGHT * importance
            # Masked source nodes: swap content for an anchor at the vector-hit stage.
            if self._node_is_masked(c.source_id):
                node_data = self.graph.get_node(c.source_id) or {}
                k = f"anchor_{c.source_id}"
                if k not in seen:
                    seen[k] = self._make_anchor(c.source_id, node_data, blended)
            else:
                c.score            = blended
                c.epistemic_status = self._node_epistemic(c.source_id)
                self.graph.record_retrieval(c.source_id)
                seen[self._key(c)] = c

        # Step 2: semantic graph query → expand
        # Masked graph nodes: route through them structurally, emit anchor only.
        for node_id, raw_score, node_data in self.graph.semantic_query(query, top_k=5):
            if raw_score < 0.4:
                continue
            source_id  = node_data.get("metadata", {}).get("source_id") or node_id
            importance = node_data.get("metadata", {}).get("importance_score", 0.5)
            blended    = _COSINE_WEIGHT * raw_score + _IMPORTANCE_WEIGHT * importance

            if self._node_is_masked(node_id):
                # Masked: emit one anchor for this node, skip vector chunk expansion
                k = f"anchor_{node_id}"
                if k not in seen:
                    seen[k] = self._make_anchor(node_id, node_data, blended)
                continue

            epistemic = node_data.get("metadata", {}).get(
                "epistemic_status", EpistemicStatus.LITERATURE.value
            )
            self.graph.record_retrieval(node_id)

            for c in self.vs.get_by_source(source_id)[:3]:
                k = self._key(c)
                if k not in seen:
                    c.score            = blended * 0.7
                    c.epistemic_status = epistemic
                    c.provenance       = [
                        f"graph expansion — {node_data.get('ntype', '')} "
                        f"'{node_data.get('label', '')[:60]}'"
                    ]
                    seen[k] = c

        # Step 3: 2-hop neighbor expansion
        # Masked neighbors: anchor only — never expand their vector chunks.
        top_src_ids = list({c.source_id for c in list(seen.values())[:3]})
        for src_id in top_src_ids:
            for nbr_id, nbr_data, etype in self.graph.get_neighbors(src_id, hops=self.graph_hop):
                ntype      = nbr_data.get("ntype")
                nbr_meta   = nbr_data.get("metadata", {})
                importance = nbr_meta.get("importance_score", 0.5)
                epistemic  = nbr_meta.get("epistemic_status", EpistemicStatus.LITERATURE.value)

                if self._node_is_masked(nbr_id):
                    k = f"anchor_{nbr_id}"
                    if k not in seen:
                        blended = _COSINE_WEIGHT * 0.6 + _IMPORTANCE_WEIGHT * importance
                        seen[k] = self._make_anchor(nbr_id, nbr_data, blended)
                    continue

                self.graph.record_retrieval(nbr_id)

                if ntype == NodeType.CLAIM:
                    k = f"claim_{nbr_id}"
                    if k not in seen:
                        label   = nbr_data.get("label", "")
                        blended = _COSINE_WEIGHT * 0.6 + _IMPORTANCE_WEIGHT * importance
                        seen[k] = RetrievedChunk(
                            text             = label,
                            source_id        = nbr_meta.get("source_id", nbr_id),
                            source_type      = NodeType.CLAIM,
                            source_title     = f"Claim from {nbr_meta.get('source_id','?')[:30]}",
                            chunk_index      = 0,
                            score            = blended,
                            provenance       = [f"graph edge '{etype}' from {src_id[:20]}"],
                            epistemic_status = epistemic,
                        )

                elif ntype == NodeType.EXPERIMENT:
                    for c in self.vs.get_by_source(nbr_id)[:2]:
                        k = self._key(c)
                        if k not in seen:
                            blended            = _COSINE_WEIGHT * 0.65 + _IMPORTANCE_WEIGHT * importance
                            c.score            = blended
                            c.epistemic_status = epistemic
                            c.provenance       = [f"linked experiment ('{etype}' from '{src_id[:20]}')"]
                            seen[k] = c

        return sorted(seen.values(), key=lambda x: x.score, reverse=True)[:self.top_k]

    # ── Answer generation ─────────────────────────────────────────────────────

    def answer(self, query: str) -> Tuple[str, List[RetrievedChunk]]:
        ans = self.answer_full(query)
        return ans.answer, ans.retrieved_chunks

    def answer_full(self, query: str) -> VictorAnswer:
        """Full answer with conversation memory storage."""
        chunks = self.retrieve(query)

        if not chunks:
            return VictorAnswer(
                answer             = "No relevant information found in Victor's knowledge base.",
                retrieved_chunks   = [],
                provenance_summary = "no context",
                provider_used      = "none",
                no_context         = True,
            )

        context_parts = []
        for i, c in enumerate(chunks, 1):
            ep_badge = _ep_badge(c)
            context_parts.append(
                f"[{i}] {ep_badge} ({c.source_type}) {c.source_title} (score={c.score:.2f})\n{c.text}"
            )
        context = "\n\n---\n\n".join(context_parts)
        prompt  = ANSWER_PROMPT.format(context=context, question=query)

        llm_result = self.llm.generate(prompt)

        sources      = sorted({(c.source_type, c.source_title) for c in chunks}, key=lambda x: x[0])
        prov_summary = " · ".join(f"[{st}] {ti[:25]}" for st, ti in sources)

        answer_obj = VictorAnswer(
            answer             = llm_result.text,
            retrieved_chunks   = chunks,
            provenance_summary = prov_summary,
            provider_used      = llm_result.provider,
            no_context         = False,
            cited_sources      = [c.source_id for c in chunks],
        )

        self._store_conversation(query, answer_obj)
        return answer_obj

    def _store_conversation(self, query: str, answer_obj: VictorAnswer):
        """Store Q&A as CONVERSATION node. Silently skips on failure."""
        try:
            q_embedding = self.vs.embedder.embed(query)
            turn = ConversationTurn(
                query           = query,
                answer          = answer_obj.answer,
                provider_used   = answer_obj.provider_used,
                source_ids      = list(set(answer_obj.cited_sources)),
                query_embedding = q_embedding,
            )
            self.graph.add_conversation_node(turn)
            self.graph.save()
        except Exception as e:
            logger.warning("Failed to store conversation node: %s", e)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _node_importance(self, source_id: str, source_type: str) -> float:
        node = self.graph.get_node(source_id)
        if node:
            return node.get("metadata", {}).get("importance_score", 0.5)
        defaults = {
            NodeType.EXPERIMENT: 0.80,
            NodeType.CLAIM:      0.70,
            NodeType.PAPER:      0.65,
            NodeType.NOTE:       0.60,
        }
        return defaults.get(source_type, 0.5)

    def _node_epistemic(self, source_id: str) -> str:
        node = self.graph.get_node(source_id)
        if node:
            return node.get("metadata", {}).get(
                "epistemic_status", EpistemicStatus.LITERATURE.value
            )
        return EpistemicStatus.LITERATURE.value

    @staticmethod
    def _key(c: RetrievedChunk) -> str:
        return f"{c.source_id}_{c.chunk_index}"


    # ── Masked memory helpers ──────────────────────────────────────────────────

    def _node_is_masked(self, node_id: str) -> bool:
        """Check mask state directly from the graph node metadata."""
        return self.graph.node_is_masked(node_id)

    def _make_anchor(
        self, node_id: str, node_data: dict, blended_score: float
    ) -> "RetrievedChunk":
        """
        Return a masked anchor chunk.

        The LLM sees that something relevant exists here but the content is
        withheld. This preserves the 'referential basis and logistic basis'
        from the original Victor framing — the system knows about the node,
        the LLM knows something is masked, but the content is not surfaced.

        Score is set to 0.05× the blended score so anchors sort below real
        content but still appear in the result list.
        """
        ntype = node_data.get("ntype", "node")
        return RetrievedChunk(
            text=(
                f"[MASKED — {ntype} — content withheld. "
                f"Use 'victor unmask {node_id[:16]}' to reveal.]"
            ),
            source_id=node_id,
            source_type=node_data.get("ntype", NodeType.NOTE),
            source_title="[Masked Node — anchor only]",
            chunk_index=0,
            score=max(blended_score * 0.05, 0.001),
            provenance=[f"masked anchor · node {node_id[:20]}"],
            # "masked", not None. RetrievedChunk.epistemic_status is typed str with a
            # safe default; passing None explicitly overrode it and crashed both
            # answer_full() and _build_context() (they call .upper()) the moment a
            # masked node entered a result set. The anchor text already discloses
            # ntype, so a "masked" tier reveals nothing further.
            epistemic_status="masked",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  AgenticRetriever — Step 2: bounded agent loop (Retrieve→Reason→Review→Respond)
# ═══════════════════════════════════════════════════════════════════════════════

# System prompt fragment injected before the tool descriptions
_AGENT_SYSTEM_PREFIX = """\
You are Victor, a research intelligence assistant. You answer questions by reasoning
over a curated knowledge graph of papers, experiments, claims, and notes.

Every answer must cite sources. Every claim must include its epistemic status
(MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS).

You work in a loop: you can call tools to gather more information before answering.
After each tool call you will see the result and can call another tool or give your
final answer. You have a budget of up to {max_tool_calls} tool calls.

AVAILABLE TOOLS:
{tool_descriptions}

HOW TO CALL A TOOL:
Respond with ONLY a JSON object:
{{"action": "tool_call", "tool": "TOOL_NAME", "arguments": {{"param": "value"}}}}

HOW TO GIVE YOUR FINAL ANSWER:
Respond with ONLY a JSON object:
{{"action": "final_answer", "answer": "Your detailed answer here."}}

RULES:
- Always prefer final_answer unless you genuinely need more information.
- Call judge_conflict when retrieved claims and experiments might conflict.
- Call summarize_claim_evidence before citing a claim to know its strength.
- Call find_research_gaps when the user asks what is missing or what to test next.
- Cite source nodes by their IDs when possible.
- If the context is insufficient, say so clearly in your final answer.
- Track your budget: you have used {tool_calls_used} of {max_tool_calls} tool calls.
"""


class AgenticRetriever(HybridRetriever):
    """
    Extends HybridRetriever with a bounded agent loop.

    Instead of retrieve-then-generate once, the LLM can:
      1. Receive retrieved chunks
      2. Decide to call a tool (Reason step)
      3. See tool results and decide again
      4. Eventually produce final_answer (Respond step)

    Automatic Review: ConflictDetector runs on any CONFIRMS/CONTRADICTS edges
    found among retrieved claims before the first LLM call.

    Bounded by:
      - max_tool_calls (default 5) — hard stop
      - max_context_tokens (default 8000) — rough token ceiling
    """

    def __init__(
        self,
        vector_store:        VictorVectorStore,
        graph:               VictorKnowledgeGraph,
        llm:                 OllamaClient,
        top_k:               int  = 8,
        graph_hop:           int  = 2,
        decay_on_retrieve:   bool = True,
        max_tool_calls:      int  = 5,
        max_context_tokens:  int  = 8000,
        auto_review:         bool = True,
        tool_registry:       Optional[Any] = None,
    ):
        super().__init__(vector_store, graph, llm, top_k, graph_hop, decay_on_retrieve)
        self.max_tool_calls     = max_tool_calls
        self.max_context_tokens = max_context_tokens
        self.auto_review        = auto_review
        self.tool_registry      = tool_registry
        self._tool_calls_used   = 0
        self._context_tokens    = 0
        self._tool_history: List[Dict[str, Any]] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def answer_full(self, query: str) -> VictorAnswer:
        """
        Agent loop: Retrieve → Review → [Reason → Tool → ...] → Respond.
        """
        self._tool_calls_used = 0
        self._context_tokens  = 0
        self._tool_history    = []

        # ── RETRIEVE ──────────────────────────────────────────────────────────
        chunks = self.retrieve(query)
        if not chunks:
            return VictorAnswer(
                answer             = "No relevant information found in Victor's knowledge base.",
                retrieved_chunks   = [],
                provenance_summary = "no context",
                provider_used      = "none",
                no_context         = True,
            )

        # ── REVIEW (automatic) ────────────────────────────────────────────────
        review_notes = ""
        if self.auto_review:
            review_notes = self._auto_review(chunks)

        # ── REASON / RESPOND loop ─────────────────────────────────────────────
        accumulated_context = self._build_context(chunks, review_notes)
        final_answer_text = self._agent_loop(query, accumulated_context, chunks)

        # ── Package answer ────────────────────────────────────────────────────
        sources      = sorted({(c.source_type, c.source_title) for c in chunks}, key=lambda x: x[0])
        prov_summary = " · ".join(f"[{st}] {ti[:25]}" for st, ti in sources)

        # Append tool history note if tools were used
        answer_text = final_answer_text
        if self._tool_history:
            trace_lines = [f"\n\n_[Agent loop: {len(self._tool_history)} tool call(s)]_"]
            for i, th in enumerate(self._tool_history, 1):
                status = "OK" if "error" not in th["result"] else "ERR"
                trace_lines.append(
                    f"  {i}. `{th['tool']}` → {status}"
                )
            answer_text += "\n".join(trace_lines)

        answer_obj = VictorAnswer(
            answer             = answer_text,
            retrieved_chunks   = chunks,
            provenance_summary = prov_summary,
            provider_used      = self.llm.model,
            no_context         = False,
            cited_sources      = [c.source_id for c in chunks],
        )

        self._store_conversation(query, answer_obj)
        return answer_obj

    # ── Agent loop internals ──────────────────────────────────────────────────

    def _agent_loop(
        self,
        query: str,
        initial_context: str,
        chunks: List[RetrievedChunk],
    ) -> str:
        """
        Run the bounded agent loop.
        Returns the final answer text.
        """
        context   = initial_context
        turns     = 0
        max_turns = self.max_tool_calls

        while turns < max_turns:
            # Build the prompt for this turn
            prompt = self._build_agent_prompt(query, context, turns, max_turns)

            # Get tool descriptions for the schema-constrained call
            if self.tool_registry is not None:
                tool_desc = self.tool_registry.tool_descriptions_for_prompt()
            else:
                tool_desc = _FALLBACK_TOOL_DESCRIPTIONS

            # Call LLM via generate_with_tools so _ollama() enforces the
            # AGENT_ACTION_SCHEMA via GBNF grammar (Ollama v0.5+).
            # The prompt already contains tool descriptions from _build_agent_prompt;
            # generate_with_tools prepends them again — so we pass just the
            # query+context section here and let generate_with_tools wrap it.
            llm_result = self.llm.generate_with_tools(
                prompt=prompt,
                tool_descriptions=tool_desc,
            )
            # Assign (not +=): prompt already embeds the full accumulated context,
            # so += would re-count prior turns' context on every iteration → quadratic blowup.
            # Set to current turn's total so the budget check reflects actual context size.
            self._context_tokens = _estimate_tokens(prompt) + _estimate_tokens(llm_result.text)

            if self._context_tokens >= self.max_context_tokens:
                # Token budget exhausted — force final answer
                forced_prompt = (
                    context
                    + f"\n\nQuestion: {query}\n\n"
                    + "You have exhausted your context-token budget. "
                    + "Provide your final answer now using the information you have.\n\nAnswer:"
                )
                forced_result = self.llm.generate(forced_prompt)
                return forced_result.text

            # Parse LLM response
            action = self._parse_llm_action(llm_result.text)

            if action is None:
                # Could not parse — treat as final answer
                return llm_result.text

            if action.get("action") == "final_answer":
                return action.get("answer", llm_result.text)

            if action.get("action") == "tool_call":
                if self._tool_calls_used >= max_turns:
                    # Budget exhausted — force final answer
                    forced_prompt = (
                        context
                        + f"\n\nQuestion: {query}\n\n"
                        + "You have exhausted your tool-call budget. "
                        + "Provide your final answer now using the information you have.\n\nAnswer:"
                    )
                    forced_result = self.llm.generate(forced_prompt)
                    return forced_result.text

                tool_name = action.get("tool", "")
                arguments = action.get("arguments", {})

                # Execute tool (with deduplication)
                call_hash = self._tool_call_hash(tool_name, arguments)
                cached = self._get_cached_tool_result(call_hash)
                if cached is not None:
                    result = cached
                else:
                    result = self._execute_tool(tool_name, arguments)
                self._tool_calls_used += 1
                self._tool_history.append({
                    "tool": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "call_hash": call_hash,
                })

                # Append result to context
                result_json = json.dumps(result, indent=2, default=str)
                context += f"\n\n[Tool result: {tool_name}]\n{result_json}\n"
                turns += 1
                continue

            # Unrecognized action — treat response as final answer
            return llm_result.text

        # Budget exhausted — one final forced answer
        forced_prompt = (
            context
            + f"\n\nQuestion: {query}\n\n"
            + "You have exhausted your tool-call budget. "
            + "Provide your final answer now using the information you have.\n\nAnswer:"
        )
        forced_result = self.llm.generate(forced_prompt)
        return forced_result.text

    def _build_context(self, chunks: List[RetrievedChunk], review_notes: str) -> str:
        """Format retrieved chunks + review notes into context string."""
        parts = []
        if review_notes:
            parts.append("=== AUTOMATIC REVIEW ===\n" + review_notes)

        parts.append("=== RETRIEVED CONTEXT ===")
        for i, c in enumerate(chunks, 1):
            ep_badge = _ep_badge(c)
            parts.append(
                f"[{i}] {ep_badge} ({c.source_type}) {c.source_title} "
                f"(score={c.score:.2f})\n{c.text}"
            )

        return "\n\n---\n\n".join(parts)

    def _auto_review(self, chunks: List[RetrievedChunk]) -> str:
        """
        REVIEW step: Run ConflictDetector on any claims that have
        both confirming and contradicting experiment edges.
        Returns a note string for the context, or empty string.
        """
        from .models import EdgeType

        claim_chunks = [c for c in chunks if c.source_type == NodeType.CLAIM]
        if not claim_chunks:
            return ""

        review_lines = []
        for cc in claim_chunks:
            node = self.graph.get_node(cc.source_id)
            if node is None:
                continue

            # Count edge types
            n_confirms    = 0
            n_contradicts = 0
            for _, _, ed in self.graph._g.in_edges(cc.source_id, data=True):
                et = ed.get("etype", "")
                if et == EdgeType.CONFIRMS:
                    n_confirms    += 1
                elif et == EdgeType.CONTRADICTS:
                    n_contradicts += 1

            if n_confirms > 0 and n_contradicts > 0:
                review_lines.append(
                    f"⚠ Claim '{cc.text[:80]}...' has BOTH confirming ({n_confirms}) "
                    f"and contradicting ({n_contradicts}) experiments. "
                    f"Call judge_conflict or summarize_claim_evidence to assess."
                )
            elif n_contradicts > 0 and n_confirms == 0:
                review_lines.append(
                    f"⚠ Claim '{cc.text[:80]}...' has {n_contradicts} contradicting "
                    f"experiment(s) and no confirmations."
                )

        return "\n".join(review_lines) if review_lines else ""

    def _build_agent_prompt(self, query: str, context: str, turns_used: int, max_turns: int) -> str:
        """Build the full prompt for one agent loop turn."""
        # Get tool descriptions from registry if available
        if self.tool_registry is not None:
            tool_desc = self.tool_registry.tool_descriptions_for_prompt()
        else:
            tool_desc = _FALLBACK_TOOL_DESCRIPTIONS

        system = _AGENT_SYSTEM_PREFIX.format(
            tool_descriptions=tool_desc,
            max_tool_calls=max_turns,
            tool_calls_used=turns_used,
        )

        prompt = (
            system
            + "\n\n=== CURRENT CONTEXT ===\n"
            + context
            + f"\n\n=== USER QUESTION ===\n{query}\n\n"
            + "Respond with a JSON object (tool_call or final_answer):\n"
        )
        return prompt

    def _parse_llm_action(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse LLM response into an action dict.
        Handles JSON extraction from markdown code blocks.
        Returns None if parsing fails entirely.
        """
        # Try direct JSON parse
        text = raw_text.strip()

        # Extract from markdown code block if present
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            text = code_block.group(1)

        # Try to find a JSON object
        try:
            parsed = json.loads(text)
            if "action" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Try regex extraction of outermost braces
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if "action" in parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass

        return None

    def _tool_call_hash(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Return a deterministic hash for a tool call (name + arguments)."""
        payload = json.dumps({"tool": tool_name, "args": arguments}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()

    def _get_cached_tool_result(self, call_hash: str) -> Optional[Dict[str, Any]]:
        """Return cached result if this exact tool call was already executed."""
        for th in self._tool_history:
            if th.get("call_hash") == call_hash:
                return th["result"]
        return None

    def _execute_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool via the registry if available, else return error."""
        if self.tool_registry is None:
            return {"error": "No tool registry configured"}
        return self.tool_registry.execute(name, arguments)


# Fallback tool descriptions used when no ToolRegistry is configured
_FALLBACK_TOOL_DESCRIPTIONS = """\
  {"name": "judge_conflict",
   "description": "Determine if an experiment confirms, contradicts, or is inconclusive vs a claim",
   "parameters": {
     "claim_text": {"type": "string", "description": "The claim text (required)"},
     "result_text": {"type": "string", "description": "The experiment result text (required)"}
   }}

  {"name": "summarize_claim_evidence",
   "description": "Get evidence summary for a claim (confirms, contradicts, confidence)",
   "parameters": {
     "claim_id": {"type": "string", "description": "The claim node ID (required)"}
   }}

  {"name": "find_research_gaps",
   "description": "Find claims with no experimental confirmation",
   "parameters": {
     "min_importance": {"type": "number", "description": "Minimum importance score filter (optional)"}
   }}

  {"name": "search_nodes_by_text",
   "description": "Semantic search over graph nodes",
   "parameters": {
     "query": {"type": "string", "description": "Search text (required)"},
     "top_k": {"type": "number", "description": "Number of results (optional)"}
   }}

  {"name": "find_related_nodes",
   "description": "Find nodes connected within N hops",
   "parameters": {
     "node_id": {"type": "string", "description": "Starting node ID (required)"},
     "hops": {"type": "number", "description": "Hop count 1-2 (optional)"}
   }}

  {"name": "get_node_details",
   "description": "Get full details of a graph node by ID",
   "parameters": {
     "node_id": {"type": "string", "description": "The node ID (required)"}
   }}

  {"name": "get_claims_for_source",
   "description": "Get all claims from a specific paper/note",
   "parameters": {
     "source_id": {"type": "string", "description": "The source document ID (required)"}
   }}"""
