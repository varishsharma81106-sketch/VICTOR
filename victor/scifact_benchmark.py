"""
SciFact Benchmark for ConflictDetector — DoD #4

Evaluates ConflictDetector accuracy against the allenai/scifact dataset.
This is the gating criterion for Phase 5 (LoRA fine-tuning).

Usage:
    # Install datasets library first:
    pip install datasets

    # Run benchmark:
    python -m victor.scifact_benchmark

    # Or with custom params:
    python -m victor.scifact_benchmark --n-samples 100 --confidence-threshold 0.5

    # Dry run (no LLM calls, just show label distribution):
    python -m victor.scifact_benchmark --dry-run

Target: >85% accuracy (PRD threshold)
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from datasets import load_dataset as _hf_load_dataset  # type: ignore[import-untyped]
    _HAS_DATASETS = True
except ImportError:
    _HAS_DATASETS = False
    _hf_load_dataset = None  # type: ignore[assignment]

from .models import ConflictResult
from .reasoning import ConflictDetector, NLICrossEncoder

_LABEL_MAP: Dict[str, str] = {
    "SUPPORT": "confirm",
    "CONTRADICT": "contradict",
    "SUPPORTS": "confirm",
    "REFUTES": "contradict",
    "NOT ENOUGH INFO": "inconclusive",
    "NOT_ENOUGH_INFO": "inconclusive",
    "NEI": "inconclusive",
}

VALID_DIRECTIONS = {"confirm", "contradict", "inconclusive"}


def map_scifact_label(scifact_label: str) -> str:
    return _LABEL_MAP.get(scifact_label, "inconclusive")


@dataclass
class EvalSample:
    claim_id: str
    claim_text: str
    doc_id: str
    abstract_text: str
    gold_direction: str


@dataclass
class ClassMetrics:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0


@dataclass
class BenchmarkResult:
    accuracy: float = 0.0
    n_evaluated: int = 0
    n_skipped_confidence: int = 0
    n_nli_overrides: int = 0
    n_total: int = 0
    confidence_threshold: float = 0.0
    per_class: Dict[str, ClassMetrics] = None  # type: ignore[assignment]
    confusion_matrix: Optional[Dict[str, Dict[str, int]]] = None

    def __post_init__(self):
        if self.per_class is None:
            self.per_class = {d: ClassMetrics() for d in VALID_DIRECTIONS}
        if self.confusion_matrix is None:
            self.confusion_matrix = {
                gold: {pred: 0 for pred in VALID_DIRECTIONS}
                for gold in VALID_DIRECTIONS
            }


def _load_local_jsonl(path: str) -> list:
    import json as _json
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(_json.loads(line))
    return rows


def load_scifact_data(
    n_samples: Optional[int] = None,
    seed: int = 42,
    corpus_path: Optional[str] = None,
    claims_path: Optional[str] = None,
) -> List[EvalSample]:
    if corpus_path is not None and claims_path is not None:
        print(f"Loading corpus from {corpus_path}...")
        raw_corpus = _load_local_jsonl(corpus_path)
        print(f"  Loaded {len(raw_corpus)} corpus documents")
        print(f"Loading claims from {claims_path}...")
        raw_claims = _load_local_jsonl(claims_path)
        print(f"  Loaded {len(raw_claims)} claims")
        claims_ds = raw_claims
        corpus_ds = raw_corpus
    else:
        if not _HAS_DATASETS:
            raise ImportError(
                "The 'datasets' library is required for the SciFact benchmark.\n"
                "Install it with:  pip install datasets\n"
                "Or pass corpus_path= and claims_path= to load local JSONL files."
            )
        print("Loading allenai/scifact dataset (claims split)...")
        claims_ds = _hf_load_dataset("allenai/scifact", "claims", split="test")
        print(f"  Loaded {len(claims_ds)} claims")
        print("Loading allenai/scifact dataset (corpus split)...")
        corpus_ds = _hf_load_dataset("allenai/scifact", "corpus", split="corpus")
        print(f"  Loaded {len(corpus_ds)} corpus documents")

    abstract_lookup: Dict[str, str] = {}
    for doc in corpus_ds:
        doc_id = str(doc.get("doc_id", ""))
        abstract_sentences = doc.get("abstract", [])
        if isinstance(abstract_sentences, list):
            abstract_text = " ".join(
                s if isinstance(s, str) else str(s) for s in abstract_sentences
            )
        else:
            abstract_text = str(abstract_sentences)
        abstract_lookup[doc_id] = abstract_text

    samples: List[EvalSample] = []
    for claim_row in claims_ds:
        claim_id = str(claim_row.get("id", ""))
        claim_text = claim_row.get("claim", "")
        evidence = claim_row.get("evidence", {})

        if not evidence:
            continue

        if isinstance(evidence, dict):
            for doc_id, ann in evidence.items():
                doc_id = str(doc_id)
                if isinstance(ann, dict):
                    label = ann.get("label", "")
                elif isinstance(ann, list):
                    label = ""
                    for entry in ann:
                        if isinstance(entry, dict):
                            label = entry.get("label", "")
                            if label:
                                break
                        elif isinstance(entry, str):
                            label = entry
                            break
                elif isinstance(ann, str):
                    label = ann
                else:
                    label = ""

                if not label:
                    continue

                gold_dir = map_scifact_label(label)
                abstract_text = abstract_lookup.get(doc_id, "")
                if not abstract_text.strip():
                    continue

                samples.append(
                    EvalSample(
                        claim_id=claim_id,
                        claim_text=claim_text,
                        doc_id=doc_id,
                        abstract_text=abstract_text,
                        gold_direction=gold_dir,
                    )
                )

    if n_samples is not None and n_samples < len(samples):
        rng = random.Random(seed)
        samples = rng.sample(samples, n_samples)
    print(f"  Prepared {len(samples)} (claim, abstract, label) triples")
    return samples


def get_label_distribution(samples: List[EvalSample]) -> Dict[str, int]:
    return Counter(s.gold_direction for s in samples)


def evaluate(
    samples: List[EvalSample],
    detector: ConflictDetector,
    confidence_threshold: float = 0.0,
) -> BenchmarkResult:
    result = BenchmarkResult(
        n_total=len(samples),
        confidence_threshold=confidence_threshold,
    )

    correct = 0
    evaluated = 0
    skipped = 0
    nli_overrides = 0

    print(f"\nEvaluating {len(samples)} samples (threshold={confidence_threshold})...")
    print("-" * 60)

    for i, sample in enumerate(samples):
        if len(samples) < 20 or (i + 1) % 10 == 0 or i == 0:
            print(
                f"  [{i+1}/{len(samples)}] "
                f"claim={sample.claim_id[:12]}... "
                f"gold={sample.gold_direction}",
                end="", flush=True,
            )

        t0 = time.time()
        prediction = detector.judge(
            claim_text=sample.claim_text,
            result_text=sample.abstract_text,
        )
        elapsed = time.time() - t0

        pred_dir = prediction.direction
        if pred_dir not in VALID_DIRECTIONS:
            pred_dir = "inconclusive"

        if getattr(prediction, "nli_override", False):
            nli_overrides += 1

        if prediction.confidence <= confidence_threshold:
            skipped += 1
            if len(samples) < 20 or (i + 1) % 10 == 0 or i == 0:
                print(
                    f" -> pred={pred_dir} "
                    f"(conf={prediction.confidence:.2f}, SKIPPED) "
                    f"[{elapsed:.1f}s]"
                )
            result.n_skipped_confidence = skipped
            continue

        evaluated += 1
        result.confusion_matrix[sample.gold_direction][pred_dir] += 1

        is_correct = pred_dir == sample.gold_direction
        if is_correct:
            correct += 1

        status = "[OK]" if is_correct else "[FAIL]"
        if len(samples) < 20 or (i + 1) % 10 == 0 or i == 0:
            print(
                f" -> pred={pred_dir} (conf={prediction.confidence:.2f}) "
                f"{status} [{elapsed:.1f}s]"
            )

    result.n_evaluated = evaluated
    result.n_skipped_confidence = skipped
    result.n_nli_overrides = nli_overrides

    if evaluated > 0:
        result.accuracy = correct / evaluated
    else:
        result.accuracy = 0.0

    _compute_per_class(result)
    return result


def _compute_per_class(result: BenchmarkResult) -> None:
    cm = result.confusion_matrix
    for direction in VALID_DIRECTIONS:
        tp = cm[direction][direction]
        fp = sum(cm[g][direction] for g in VALID_DIRECTIONS if g != direction)
        fn = sum(cm[direction][p] for p in VALID_DIRECTIONS if p != direction)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        result.per_class[direction] = ClassMetrics(
            precision=precision, recall=recall, f1=f1, support=tp + fn,
        )


_PRD_THRESHOLD = 0.85


def print_report(result: BenchmarkResult) -> None:
    print("\n" + "=" * 60)
    print("  SCIFACT BENCHMARK RESULTS")
    print("=" * 60)
    print(f"\n  Samples total:           {result.n_total}")
    print(f"  Samples evaluated:       {result.n_evaluated}")
    print(f"  Skipped (low conf):      {result.n_skipped_confidence}")
    print(f"  NLI overrides fired:     {result.n_nli_overrides}")
    print(f"  Confidence threshold:    {result.confidence_threshold}")
    print(f"\n  Overall accuracy:        {result.accuracy:.1%}")
    threshold_met = result.accuracy >= _PRD_THRESHOLD
    status = "PASS" if threshold_met else "FAIL"
    print(f"  PRD threshold (>85%):    {status}  ({'meets' if threshold_met else 'below'} target)")
    print("\n  Per-class metrics:")
    print(f"  {'Direction':<18} {'Prec':>6} {'Recall':>6} {'F1':>6} {'Support':>8}")
    print("  " + "-" * 48)
    for direction in ["confirm", "contradict", "inconclusive"]:
        m = result.per_class[direction]
        print(
            f"  {direction:<18} {m.precision:>5.1%} {m.recall:>5.1%} "
            f"{m.f1:>5.1%} {m.support:>8d}"
        )
    print("\n  Confusion matrix (rows=gold, cols=predicted):")
    directions = ["confirm", "contradict", "inconclusive"]
    header = f"  {'Gold \\ Pred':<18}"
    for d in directions:
        header += f" {d:>12}"
    print(header)
    print("  " + "-" * (18 + 13 * len(directions)))
    for gold in directions:
        row = f"  {gold:<18}"
        for pred in directions:
            row += f" {result.confusion_matrix[gold][pred]:>12}"
        print(row)
    print("\n" + "=" * 60)


def dry_run_report(samples: list) -> None:
    dist = get_label_distribution(samples)
    print("\n" + "=" * 60)
    print("  SCIFACT DRY RUN (no LLM calls)")
    print("=" * 60)
    print(f"\n  Total triples loaded:  {len(samples)}")
    print(f"\n  Label distribution:")
    for direction in ["confirm", "contradict", "inconclusive"]:
        count = dist.get(direction, 0)
        pct = count / len(samples) * 100 if samples else 0
        print(f"    {direction:<18} {count:>5d}  ({pct:5.1f}%)")
    print(f"\n  Example claims (first 5):")
    for sample in samples[:5]:
        print(f"\n    Claim: {sample.claim_text[:100]}...")
        print(f"    Gold:  {sample.gold_direction}")
        print(f"    Abstract: {sample.abstract_text[:100]}...")
    print("\n" + "=" * 60)
    print("  Dry run complete. Run without --dry-run to evaluate ConflictDetector.")
    print("=" * 60)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SciFact Benchmark for ConflictDetector — DoD #4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--n-samples", type=int, default=None)
    parser.add_argument("--confidence-threshold", type=float, default=0.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--use-mock-llm", action="store_true")
    parser.add_argument("--corpus-path", type=str, default=None, metavar="PATH")
    parser.add_argument("--claims-path", type=str, default=None, metavar="PATH")
    parser.add_argument(
        "--nli-model",
        type=str,
        default=None,
        metavar="MODEL_NAME",
        help=(
            "sentence-transformers CrossEncoder model name for NLI cross-check. "
            "If set, loads an NLICrossEncoder and wires it into ConflictDetector. "
            "Example: cross-encoder/nli-deberta-v3-base"
        ),
    )
    parser.add_argument(
        "--nli-threshold",
        type=float,
        default=0.5,
        help=(
            "Min NLI confidence required to override an LLM confirm/inconclusive "
            "judgment to contradict (default: 0.5). Only used in standard mode."
        ),
    )
    parser.add_argument(
        "--nli-primary",
        action="store_true",
        help=(
            "Step-1a architecture: NLI cross-encoder decides direction; LLM "
            "generates reasoning text only (no JSON schema, no direction token). "
            "Eliminates structured-output agreement-bias amplification. "
            "Requires --nli-model."
        ),
    )
    parser.add_argument(
        "--nli-label-order",
        type=str,
        default=None,
        metavar="ORDER",
        help=(
            "Explicit label order for the NLI model, as a comma-separated list "
            "of three values from {contradiction,entailment,neutral}. "
            "Bypasses auto-detection entirely — use this for models whose "
            "id2label attribute path differs from deberta-v3 (e.g. ModernCE). "
            "Example: --nli-label-order entailment,neutral,contradiction"
        ),
    )
    parser.add_argument(
        "--skip-nli-smoke-test",
        action="store_true",
        help=(
            "Skip the label-order smoke test that runs two known pairs before "
            "the benchmark loop. Use only if you have already validated the "
            "label mapping externally. The smoke test catches order mismatches "
            "before they corrupt 100+ samples."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    using_local = args.corpus_path is not None and args.claims_path is not None

    if not using_local and not _HAS_DATASETS:
        print(
            "ERROR: The 'datasets' library is required for HuggingFace download.\n"
            "  Install with:  pip install datasets\n"
            "  Or use local files:  --corpus-path corpus.jsonl --claims-path claims_dev.jsonl\n"
        )
        sys.exit(1)

    if args.dry_run:
        samples = load_scifact_data(
            n_samples=args.n_samples,
            seed=args.seed,
            corpus_path=args.corpus_path,
            claims_path=args.claims_path,
        )
        dry_run_report(samples)
        return

    from .config import VictorConfig
    from .llm import create_inference_client

    config = VictorConfig()
    if args.use_mock_llm:
        config.use_mock_llm = True

    # Build NLI cross-encoder if requested
    nli = None
    if args.nli_model:
        # Parse --nli-label-order if provided
        label_order = None
        if args.nli_label_order:
            label_order = [s.strip() for s in args.nli_label_order.split(",")]
            print(f"  Using explicit label order: {label_order}")

        print(f"Loading NLI cross-encoder: {args.nli_model} ...")
        nli = NLICrossEncoder(model_name=args.nli_model, label_order=label_order)
        mode = "primary (NLI decides direction)" if args.nli_primary else f"cross-check (threshold={args.nli_threshold})"
        print(f"  NLI mode: {mode}")

        # Smoke-test the label mapping before the benchmark loop (unless skipped)
        if not args.skip_nli_smoke_test:
            try:
                nli.validate_label_order()
            except RuntimeError as exc:
                print(f"\nLabel order smoke test FAILED -- aborting benchmark.\n{exc}")
                sys.exit(1)
        else:
            print("  Skipping label-order smoke test (--skip-nli-smoke-test).")
    elif args.nli_primary:
        print("WARNING: --nli-primary has no effect without --nli-model. Ignored.")

    print("Creating inference client...")
    client = create_inference_client(config)
    detector = ConflictDetector(
        llm=client,
        nli=nli,
        nli_override_threshold=args.nli_threshold,
        nli_primary=args.nli_primary and nli is not None,
    )

    if hasattr(client, "is_available") and not client.is_available() and not args.use_mock_llm:
        print(
            "\nWARNING: No LLM backend is available.\n"
            "  Falling back to mock mode (all predictions will be 'inconclusive').\n"
            "  To use a real model:\n"
            "    - Start Ollama:  ollama serve\n"
            "    - Or set OPENAI_API_KEY env var\n"
            "    - Or use --use-mock-llm to suppress this warning\n"
        )
        config.use_mock_llm = True
        client = create_inference_client(config)
        detector = ConflictDetector(
            llm=client,
            nli=nli,
            nli_override_threshold=args.nli_threshold,
            nli_primary=args.nli_primary and nli is not None,
        )

    samples = load_scifact_data(
        n_samples=args.n_samples,
        seed=args.seed,
        corpus_path=args.corpus_path,
        claims_path=args.claims_path,
    )
    if not samples:
        print("ERROR: No samples loaded from the dataset. Cannot evaluate.")
        sys.exit(1)

    result = evaluate(
        samples=samples,
        detector=detector,
        confidence_threshold=args.confidence_threshold,
    )
    print_report(result)

    if result.accuracy < _PRD_THRESHOLD:
        sys.exit(1)


if __name__ == "__main__":
    main()
