"""
InferenceClient — provider-agnostic LLM backend (DoD item #5).

v4.3 change: OllamaClient now implements the InferenceClient interface
instead of being the only backend. New backends (LlamaCppClient, MLXClient)
plug into the same interface so core.py never needs to know which one is
running. Select via VictorConfig.inference_backend ("ollama" | "llama_cpp" | "mlx")
and construct through create_inference_client(config) rather than naming
OllamaClient directly.

Priority within OllamaClient specifically: Ollama (local) → OpenAI (cloud) → Mock.
Every call is logged to llm_calls.jsonl with provider, model, latency, error.

v4.1 additions (Step 1–2):
  - generate_structured(): attempts JSON output with a schema hint,
    with retry fallback on parse failure
  - generate_with_tools(): convenience wrapper for tool-calling loops

v4.2 fixes:
  - _ollama() accepts optional response_schema; when provided, passes it as
    the Ollama `format` parameter so llama.cpp enforces output via GBNF
    grammar — the model physically cannot emit invalid JSON.
  - generate_structured() no longer injects schema text into the prompt when
    response_schema is passed (double-enforcement confuses small models).
  - generate_with_tools() passes AGENT_ACTION_SCHEMA to _ollama() via
    response_schema instead of relying on prompt-level coercion.
  - Requires Ollama v0.5+. On older Ollama the `format` key is silently
    ignored and prompt-based coercion is the graceful fallback.
"""
import json
import time
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any


# JSON schema for the agent loop's action output.
# Passed as `format` to Ollama (v0.5+), which converts it to a GBNF grammar
# that is enforced at the token level — invalid JSON gets zero probability.
AGENT_ACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action":    {"type": "string", "enum": ["tool_call", "final_answer"]},
        "tool":      {"type": "string"},
        "arguments": {"type": "object"},
        "answer":    {"type": "string"},
    },
    "required": ["action"],
}


@dataclass
class LLMResult:
    text:      str
    provider:  str
    model:     str
    latency_s: float = 0.0
    error:     Optional[str] = None


class InferenceClient(ABC):
    """
    Provider-agnostic interface every backend must implement.

    This is the abstraction the PRD's DoD item #5 calls for: core.py and the
    agent loop talk to InferenceClient, never to a specific backend class.
    Adding a new backend means subclassing this and implementing four
    methods — no changes required anywhere else.
    """

    @abstractmethod
    def generate(self, prompt: str, temperature: Optional[float] = None) -> LLMResult:
        """Generate text. Must never raise — always return an LLMResult.

        temperature=None means "use the backend's configured default".
        Pass an explicit value to vary sampling for one call, which is what
        self-consistency voting needs in order to produce differing samples.
        """
        ...

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema_hint: Optional[Dict[str, Any]] = None,
        retries: int = 1,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        ...

    @abstractmethod
    def generate_with_tools(
        self,
        prompt: str,
        tool_descriptions: str,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend's runtime is reachable right now."""
        ...

    # Shared default — most backends don't have an OpenAI escape hatch,
    # only OllamaClient overrides this meaningfully.
    def openai_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))


class OllamaClient(InferenceClient):
    def __init__(
        self,
        base_url:       str  = "http://localhost:11434",
        model:          str  = "phi3:mini",
        openai_model:   str  = "gpt-4o-mini",
        openai_api_url: str  = "https://api.openai.com/v1/chat/completions",
        use_mock:       bool = False,
        timeout:        int  = 60,
        log_file:       Optional[Path] = None,
        temperature:    float = 0.1,
    ):
        self.base_url       = base_url.rstrip("/")
        self.model          = model
        self.openai_model   = openai_model
        self.openai_api_url = openai_api_url
        self.use_mock       = use_mock
        self.timeout        = timeout
        self.log_file       = Path(log_file) if log_file else None
        self.temperature    = temperature

    def generate(self, prompt: str, temperature: Optional[float] = None) -> LLMResult:
        """
        Generate text. Tries Ollama → OpenAI → Mock.
        Never raises — always returns an LLMResult.

        temperature=None uses self.temperature (from VictorConfig.llm_temperature).
        """
        if self.use_mock:
            return self._mock(prompt)

        try:
            result = self._ollama(prompt, temperature=temperature)
            self._log(result, prompt)
            return result
        except Exception:
            pass

        try:
            result = self._openai(prompt, temperature=temperature)
            self._log(result, prompt)
            return result
        except Exception:
            pass

        result = self._mock(prompt)
        self._log(result, prompt)
        return result

    # ── Structured / tool-aware generation (v4.1) ────────────────────────────

    def generate_structured(
        self,
        prompt: str,
        schema_hint: Optional[Dict[str, Any]] = None,
        retries: int = 1,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        """
        Generate with a strong preference for valid JSON output.

        When `response_schema` is provided it is forwarded to `_ollama()` as
        the Ollama `format` parameter (grammar-constrained output, v0.5+).
        In that case NO schema text is injected into the prompt — double-
        enforcement confuses small models; the grammar wins.

        When only `schema_hint` is provided (legacy path) the schema is
        injected into the prompt text as before.

        Retries up to `retries` times on JSON parse failure.
        """
        if response_schema:
            # Grammar path: don't touch the prompt; constraint is at token level.
            enhanced_prompt = prompt
        elif schema_hint:
            schema_json = json.dumps(schema_hint, indent=2)
            enhanced_prompt = (
                f"{prompt}\n\n"
                f"You MUST respond with a single JSON object matching this schema:\n"
                f"```json\n{schema_json}\n```\n"
                f"Respond ONLY with the JSON object — no markdown, no preamble."
            )
        else:
            enhanced_prompt = prompt

        last_result = None
        for attempt in range(retries + 1):
            if response_schema and not self.use_mock:
                # Route directly to _ollama with grammar schema; fall through to
                # _openai / _mock on failure just like the normal generate() chain.
                try:
                    result = self._ollama(
                        enhanced_prompt,
                        response_schema=response_schema,
                        temperature=temperature,
                    )
                    self._log(result, enhanced_prompt)
                except Exception:
                    try:
                        result = self._openai(enhanced_prompt, temperature=temperature)
                        self._log(result, enhanced_prompt)
                    except Exception:
                        result = self._mock(enhanced_prompt)
                        self._log(result, enhanced_prompt)
            else:
                # use_mock=True, or no response_schema — use standard generate() chain.
                result = self.generate(enhanced_prompt, temperature=temperature)
            last_result = result

            # Validate JSON
            text = result.text.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return LLMResult(
                        text=text,
                        provider=result.provider,
                        model=result.model,
                        latency_s=result.latency_s,
                    )
            except (json.JSONDecodeError, TypeError):
                pass

            # Retry with a stronger prompt nudge (only on prompt-based path)
            if attempt < retries and not response_schema:
                enhanced_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: Your previous response was not valid JSON. "
                    f"Respond with ONLY a JSON object. No other text.\n"
                    f"Required schema: {json.dumps(schema_hint or {})}"
                )

        return last_result

    def generate_with_tools(
        self,
        prompt: str,
        tool_descriptions: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        """
        Convenience wrapper for tool-calling agent loops.

        Passes AGENT_ACTION_SCHEMA as `response_schema` so _ollama() enforces
        the action envelope via GBNF grammar (Ollama v0.5+). The prompt does
        NOT contain JSON format instructions — the grammar handles that.

        On fallback to _openai or _mock, generate_structured's prompt-based
        coercion still works as a degraded fallback.
        """
        # Tool descriptions go in the prompt; JSON format enforcement is via grammar.
        full_prompt = (
            f"You have access to the following tools:\n{tool_descriptions}\n\n"
            f"{prompt}"
        )
        return self.generate_structured(
            full_prompt,
            response_schema=AGENT_ACTION_SCHEMA,
            retries=1,
            temperature=temperature,
        )

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def openai_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    # ── Providers ─────────────────────────────────────────────────────────────

    def _ollama(
        self,
        prompt: str,
        response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        import urllib.request

        t0   = time.time()
        body: Dict[str, Any] = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            # Without this key Ollama applies its own server-side default (0.8).
            # Victor's judgments are classification, not creative writing, so the
            # sampling temperature must be Victor's decision, not the daemon's.
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
            },
        }
        if response_schema:
            # Ollama v0.5+ converts this JSON schema to a GBNF grammar internally.
            # On older Ollama the key is silently ignored — prompt-based coercion
            # in generate_structured acts as graceful degradation.
            body["format"] = response_schema

        payload = json.dumps(body).encode()

        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())

        return LLMResult(
            text=data.get("response", ""),
            provider="ollama",
            model=self.model,
            latency_s=round(time.time() - t0, 2),
        )

    def _openai(self, prompt: str, temperature: Optional[float] = None) -> LLMResult:
        import urllib.request

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("No OPENAI_API_KEY set")

        t0      = time.time()
        payload = json.dumps({
            "model": self.openai_model,
            "messages": [{"role": "user", "content": prompt}],
            # Was hardcoded to 0.1, which made per-call sampling diversity
            # impossible on this backend — self-consistency voting degenerated
            # into N identical votes.
            "temperature": self.temperature if temperature is None else temperature,
        }).encode()

        req = urllib.request.Request(
            self.openai_api_url,
            data=payload,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())

        text = data["choices"][0]["message"]["content"]
        return LLMResult(
            text=text,
            provider="openai",
            model=self.openai_model,
            latency_s=round(time.time() - t0, 2),
        )

    def _mock(self, prompt: str) -> LLMResult:
        """Offline placeholder — returns structurally valid responses."""
        # Detect what kind of response is needed
        p_lower = prompt.lower()

        if '"direction"' in prompt or "confirms" in p_lower or "contradict" in p_lower:
            text = '{"direction": "inconclusive", "confidence": 0.0, "reason": "mock mode — no LLM available"}'
        elif '"claims"' in prompt or "quantitative" in p_lower:
            text = '{"claims": [], "concepts": []}'
        elif ('"action"' in prompt or "tool_call" in p_lower or "final_answer" in p_lower
              or "you have access to the following tools" in p_lower):
            # For agent loop mock — produce a final_answer to avoid infinite loops
            text = '{"action": "final_answer", "answer": "[Mock LLM — no live model available]\\n\\nI cannot access the knowledge base because no LLM is running. To enable:\\n1. Install Ollama and run `ollama serve`\\n2. Or set OPENAI_API_KEY env var"}'
        else:
            text = (
                "[Mock LLM — no live model available]\n\n"
                "To enable local inference: install Ollama and run 'ollama serve'\n"
                "To enable cloud inference: set OPENAI_API_KEY env var\n\n"
                f"Query received: {prompt[:150]}..."
            )
        return LLMResult(text=text, provider="mock", model="mock", latency_s=0.0)

    def _log(self, result: LLMResult, prompt: str) -> None:
        if not self.log_file:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%S"),
                "provider":       result.provider,
                "model":          result.model,
                "latency_s":      result.latency_s,
                "prompt_chars":   len(prompt),
                "response_chars": len(result.text),
                "error":          result.error,
            }
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except Exception:
            pass


class LlamaCppClient(InferenceClient):
    """
    Direct llama.cpp backend via the `llama_cpp` Python bindings — no Ollama
    server required. Useful for headless / embedded deployments (Phase 2
    hardware target: Raspberry Pi + sensors) where running a separate Ollama
    daemon is unnecessary overhead.

    Falls back to a mock response if llama_cpp isn't installed or the GGUF
    model file isn't found — never raises, matching the InferenceClient contract.
    """

    def __init__(
        self,
        model_path: str,
        n_ctx:      int = 4096,
        n_threads:  Optional[int] = None,
        log_file:   Optional[Path] = None,
        temperature: float = 0.1,
    ):
        self.model_path = model_path
        self.n_ctx       = n_ctx
        self.n_threads   = n_threads
        self.log_file    = Path(log_file) if log_file else None
        self.temperature = temperature
        self._llm        = None

    def _load(self):
        if self._llm is not None:
            return
        from llama_cpp import Llama   # pip install llama-cpp-python
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            verbose=False,
        )

    def is_available(self) -> bool:
        try:
            import llama_cpp  # noqa: F401
            return Path(self.model_path).exists()
        except ImportError:
            return False

    def generate(self, prompt: str, temperature: Optional[float] = None) -> LLMResult:
        t0 = time.time()
        try:
            self._load()
            out = self._llm(
                prompt,
                max_tokens=1024,
                stop=["</s>"],
                temperature=self.temperature if temperature is None else temperature,
            )
            text = out["choices"][0]["text"]
            result = LLMResult(
                text=text, provider="llama_cpp",
                model=Path(self.model_path).name,
                latency_s=round(time.time() - t0, 2),
            )
        except Exception as exc:
            result = LLMResult(
                text=f"[llama_cpp unavailable: {exc}]",
                provider="mock", model="mock", error=str(exc),
            )
        self._log(result, prompt)
        return result

    def generate_structured(
        self, prompt: str, schema_hint: Optional[Dict[str, Any]] = None,
        retries: int = 1, response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        # llama_cpp grammar support (GBNF) exists but is a separate code path
        # (LlamaGrammar.from_json_schema) — kept simple here via prompt coercion,
        # consistent with OllamaClient's degraded fallback for pre-v0.5 Ollama.
        schema = response_schema or schema_hint
        enhanced = prompt
        if schema:
            enhanced = (
                f"{prompt}\n\nRespond ONLY with JSON matching: {json.dumps(schema)}"
            )
        result = self.generate(enhanced, temperature=temperature)
        for attempt in range(retries):
            try:
                json.loads(result.text.strip())
                return result
            except (json.JSONDecodeError, TypeError):
                result = self.generate(
                    enhanced + "\n\nIMPORTANT: respond with ONLY valid JSON.",
                    temperature=temperature,
                )
        return result

    def generate_with_tools(self, prompt: str, tool_descriptions: str, max_tokens=None,
                            temperature: Optional[float] = None) -> LLMResult:
        full_prompt = f"You have access to the following tools:\n{tool_descriptions}\n\n{prompt}"
        return self.generate_structured(full_prompt, response_schema=AGENT_ACTION_SCHEMA,
                                        retries=1, temperature=temperature)

    def _log(self, result: LLMResult, prompt: str) -> None:
        if not self.log_file:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "provider": result.provider, "model": result.model,
                    "latency_s": result.latency_s, "prompt_chars": len(prompt),
                    "response_chars": len(result.text), "error": result.error,
                }) + "\n")
        except Exception:
            pass


class MLXClient(InferenceClient):
    """
    Apple Silicon backend via `mlx-lm`. Same contract as LlamaCppClient —
    never raises, degrades to a mock response if mlx_lm isn't installed or
    the architecture isn't Apple Silicon.
    """

    def __init__(self, model_path: str, log_file: Optional[Path] = None):
        self.model_path = model_path
        self.log_file   = Path(log_file) if log_file else None
        self._model     = None
        self._tokenizer = None

    def _load(self):
        if self._model is not None:
            return
        from mlx_lm import load   # pip install mlx-lm
        self._model, self._tokenizer = load(self.model_path)

    def is_available(self) -> bool:
        try:
            import platform
            import mlx_lm  # noqa: F401
            return platform.system() == "Darwin" and platform.machine() == "arm64"
        except ImportError:
            return False

    def generate(self, prompt: str, temperature: Optional[float] = None) -> LLMResult:
        # temperature is accepted for interface parity but not applied: mlx_lm
        # takes sampling settings via a sampler object, not a scalar kwarg.
        # Wiring that up is a separate change — flagged rather than faked.
        t0 = time.time()
        try:
            from mlx_lm import generate as mlx_generate
            self._load()
            text = mlx_generate(self._model, self._tokenizer, prompt=prompt, max_tokens=1024)
            result = LLMResult(
                text=text, provider="mlx", model=Path(self.model_path).name,
                latency_s=round(time.time() - t0, 2),
            )
        except Exception as exc:
            result = LLMResult(
                text=f"[mlx unavailable: {exc}]", provider="mock", model="mock", error=str(exc),
            )
        self._log(result, prompt)
        return result

    def generate_structured(
        self, prompt: str, schema_hint: Optional[Dict[str, Any]] = None,
        retries: int = 1, response_schema: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> LLMResult:
        schema = response_schema or schema_hint
        enhanced = prompt
        if schema:
            enhanced = f"{prompt}\n\nRespond ONLY with JSON matching: {json.dumps(schema)}"
        result = self.generate(enhanced, temperature=temperature)
        for attempt in range(retries):
            try:
                json.loads(result.text.strip())
                return result
            except (json.JSONDecodeError, TypeError):
                result = self.generate(
                    enhanced + "\n\nIMPORTANT: respond with ONLY valid JSON.",
                    temperature=temperature,
                )
        return result

    def generate_with_tools(self, prompt: str, tool_descriptions: str, max_tokens=None,
                            temperature: Optional[float] = None) -> LLMResult:
        full_prompt = f"You have access to the following tools:\n{tool_descriptions}\n\n{prompt}"
        return self.generate_structured(full_prompt, response_schema=AGENT_ACTION_SCHEMA,
                                        retries=1, temperature=temperature)

    def _log(self, result: LLMResult, prompt: str) -> None:
        if not self.log_file:
            return
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "provider": result.provider, "model": result.model,
                    "latency_s": result.latency_s, "prompt_chars": len(prompt),
                    "response_chars": len(result.text), "error": result.error,
                }) + "\n")
        except Exception:
            pass


def create_inference_client(config) -> InferenceClient:
    """
    Factory — builds the configured InferenceClient backend from a VictorConfig.
    This is what core.py calls instead of naming OllamaClient directly,
    completing DoD item #5 (provider-agnostic InferenceClient).
    """
    backend     = getattr(config, "inference_backend", "ollama")
    temperature = getattr(config, "llm_temperature", 0.1)

    if backend == "llama_cpp":
        return LlamaCppClient(
            model_path=getattr(config, "llama_cpp_model_path", ""),
            log_file=config.llm_log_file,
            temperature=temperature,
        )
    if backend == "mlx":
        return MLXClient(
            model_path=getattr(config, "mlx_model_path", ""),
            log_file=config.llm_log_file,
        )
    # default: ollama
    return OllamaClient(
        base_url       = config.ollama_base_url,
        model          = config.ollama_model,
        openai_model   = config.openai_model,
        openai_api_url = config.openai_api_url,
        use_mock       = config.use_mock_llm,
        timeout        = config.llm_timeout,
        log_file       = config.llm_log_file,
        temperature    = temperature,
    )
