"""
ClaimExtractor — uses the LLM layer to pull structured claims + concepts from text.

v4 change: EpistemicStatus stamped on every extracted Claim.
  - LLM-extracted claims → EpistemicStatus.LITERATURE
  - Keyword-fallback claims → EpistemicStatus.HYPOTHESIS (low-confidence)

F-004 compliance: never silently discards an extraction attempt.
JSON failures fall back to keyword heuristic + low_confidence=True.
Every attempt is logged to extraction_log.jsonl.
"""
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import List, Tuple, Optional

from .models import Claim, EpistemicStatus
from .llm import OllamaClient


EXTRACTION_PROMPT = """\
You are extracting research claims from a scientific text.

Extract ALL specific claims from the text below. Focus on:
1. Quantitative: specific numbers, percentages, benchmark scores, accuracy metrics
2. Architectural: "method X improves baseline Y using technique Z"
3. Methodological: "approach A outperforms B on task C"

Return ONLY a JSON object — no preamble, no markdown, no explanation:
{{
  "claims": [
    {{
      "text": "full claim as stated in text",
      "type": "quantitative|architectural|methodological",
      "metric": "metric name or null",
      "value": "numeric value or null",
      "benchmark": "benchmark name or null"
    }}
  ],
  "concepts": ["concept1", "concept2"]
}}

Text:
{text}"""

_STOPWORDS = {
    "the", "and", "for", "are", "with", "this", "that", "from", "have",
    "has", "was", "were", "been", "being", "into", "over", "under", "than",
    "then", "such", "also", "not", "but", "can", "may", "our", "their",
    "its", "his", "her", "they", "them", "these", "those", "use", "used",
    "using", "based", "show", "shows", "showed", "result", "results",
}


class ClaimExtractor:
    def __init__(
        self,
        llm:      OllamaClient,
        log_file: Optional[str | Path] = None,
    ):
        self.llm      = llm
        self.log_file = Path(log_file) if log_file else None

    def extract(
        self,
        text:         str,
        source_id:    str,
        source_title: str,
        chunk_id:     Optional[str] = None,
        max_chars:    int = 4000,
    ) -> Tuple[List[Claim], List[str]]:
        """
        Extract claims + concepts from a single text block.
        Called once per chunk by the ingestors (F-004 fix).
        Returns (claims, concept_names).
        """
        snippet = text[:max_chars]
        prompt  = EXTRACTION_PROMPT.format(text=snippet)
        result  = self.llm.generate(prompt)
        raw     = result.text

        parsed = self._parse_json(raw)

        if parsed is not None:
            claims, concepts = self._claims_from_parsed(
                parsed, source_id, source_title, chunk_id,
                provider=result.provider, low_confidence=False,
            )
            self._log(chunk_id, source_id, result, raw,
                      n_claims=len(claims), low_confidence=False, parse_failed=False)
            return claims, concepts

        # JSON parse failed → keyword fallback (F-004: never silently discard)
        claims, concepts = self._keyword_fallback(
            snippet, source_id, source_title, chunk_id, provider=result.provider,
        )
        self._log(chunk_id, source_id, result, raw,
                  n_claims=len(claims), low_confidence=True, parse_failed=True)
        return claims, concepts

    # ── JSON path ─────────────────────────────────────────────────────────────

    @staticmethod
    def _claims_from_parsed(
        parsed:         dict,
        source_id:      str,
        source_title:   str,
        chunk_id:       Optional[str],
        provider:       str,
        low_confidence: bool,
    ) -> Tuple[List[Claim], List[str]]:
        claims: List[Claim] = []
        for c in parsed.get("claims", []):
            if not c.get("text"):
                continue
            claims.append(Claim(
                text             = c["text"],
                source_id        = source_id,
                source_title     = source_title,
                claim_type       = c.get("type", "methodological"),
                metric           = c.get("metric"),
                value            = c.get("value"),
                benchmark        = c.get("benchmark"),
                chunk_id         = chunk_id,
                extracted_by     = provider,
                low_confidence   = low_confidence,
                epistemic_status = EpistemicStatus.LITERATURE.value,
            ))
        concepts = [s for s in parsed.get("concepts", []) if isinstance(s, str)]
        return claims, concepts

    @staticmethod
    def _parse_json(raw: str) -> Optional[dict]:
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
        return None

    # ── Keyword fallback (F-004) ──────────────────────────────────────────────

    def _keyword_fallback(
        self,
        text:         str,
        source_id:    str,
        source_title: str,
        chunk_id:     Optional[str],
        provider:     str,
    ) -> Tuple[List[Claim], List[str]]:
        """
        Keyword-based fallback. Marks claims as low_confidence=True and
        EpistemicStatus.HYPOTHESIS so evidence weighting discounts them.
        """
        claims: List[Claim] = []
        number_pat = re.compile(r"\d+(\.\d+)?\s*%?")
        for sent in re.split(r"(?<=[.!?])\s+", text):
            sent = sent.strip()
            if len(sent) < 15 or len(sent) > 300:
                continue
            if number_pat.search(sent):
                claims.append(Claim(
                    text             = sent,
                    source_id        = source_id,
                    source_title     = source_title,
                    claim_type       = "quantitative",
                    chunk_id         = chunk_id,
                    extracted_by     = "keyword_fallback",
                    low_confidence   = True,
                    epistemic_status = EpistemicStatus.HYPOTHESIS.value,
                ))

        words    = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", text)
        freq     = Counter(w.lower() for w in words if w.lower() not in _STOPWORDS)
        concepts = [w for w, _ in freq.most_common(8)]

        return claims, concepts

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, chunk_id, source_id, result, raw, n_claims, low_confidence, parse_failed):
        if not self.log_file:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp":          time.strftime("%Y-%m-%dT%H:%M:%S"),
                "chunk_id":           chunk_id,
                "source_id":          source_id,
                "provider_used":      result.provider,
                "model":              result.model,
                "parse_failed":       parse_failed,
                "low_confidence":     low_confidence,
                "n_claims":           n_claims,
                "raw_response_chars": len(raw),
            }
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass
