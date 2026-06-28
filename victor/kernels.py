"""
Computation kernels — v4.3 (DoD item #8: StatisticsKernel)

A ComputationKernel takes numeric inputs (usually pulled from EXPERIMENT or
MEASUREMENT nodes) and produces a ComputedResult: a deterministic, hashable
output that can be stored back into the graph as a COMPUTED node via
VictorKnowledgeGraph.add_computed_node().

Why the reproducibility_hash matters (PRD's uncertainty/reproducibility
section): it's a SHA-256 of (kernel name, kernel version, sorted input node
IDs, sorted input values). If any input is later retracted or edited, this
hash breaks on recomputation — the graph can flag stale COMPUTED nodes by
comparing the stored hash against a freshly recomputed one. That check isn't
wired into the graph yet; ComputedResult just carries what's needed for it.

StatisticsKernel is the first kernel — mean, sample variance, standard
deviation, a confidence interval on the mean (normal approximation), and
Cohen's d effect size between two groups. This unblocks Phase 2 sensor data
(PRD: "first computation kernel needed before Phase 2 sensors can produce
quantitative COMPUTED nodes").
"""
from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


KERNEL_VERSION = "1.0"


@dataclass
class ComputedResult:
    kernel:                str
    kernel_version:        str
    inputs:                List[str]            # input node IDs, if known (else raw value tags)
    outputs:               Dict[str, float]
    reproducibility_hash:  str
    uncertainty:           Optional[Dict[str, float]] = None
    notes:                 str = ""


class ComputationKernelBase(ABC):
    name: str = "base"

    @abstractmethod
    def compute(self, *args, **kwargs) -> ComputedResult:
        ...

    @staticmethod
    def _hash(kernel_name: str, kernel_version: str, input_ids: Sequence[str], values: Sequence[float]) -> str:
        payload = json.dumps({
            "kernel": kernel_name,
            "version": kernel_version,
            "inputs": sorted(input_ids),
            "values": sorted(round(v, 10) for v in values),
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


class StatisticsKernel(ComputationKernelBase):
    """
    mean, sample variance, standard deviation, confidence interval on the
    mean, and Cohen's d effect size between two groups.

    Inputs are plain floats — the caller (core.py / CLI) is responsible for
    pulling those floats out of EXPERIMENT.results or MEASUREMENT nodes and
    passing the corresponding node IDs through `input_node_ids` so the
    DERIVED_FROM edges in the graph are meaningful.
    """
    name = "statistics"

    def compute(
        self,
        values:          Sequence[float],
        input_node_ids:  Optional[Sequence[str]] = None,
        confidence_level: float = 0.95,
        metric_name:      str = "value",
    ) -> ComputedResult:
        if not values:
            raise ValueError("StatisticsKernel.compute() requires at least one value")

        values = [float(v) for v in values]
        n = len(values)
        mean = sum(values) / n

        if n > 1:
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        else:
            variance = 0.0
        std = math.sqrt(variance)

        # Normal approximation CI (good enough for n>=2; flagged as approximate for n<30).
        z = self._z_for_confidence(confidence_level)
        se = std / math.sqrt(n) if n > 0 else 0.0
        ci_low  = mean - z * se
        ci_high = mean + z * se

        ids = list(input_node_ids) if input_node_ids else [f"raw:{metric_name}:{i}" for i in range(n)]

        outputs = {
            "n":        float(n),
            "mean":     round(mean, 6),
            "variance": round(variance, 6),
            "std":      round(std, 6),
            "ci_low":   round(ci_low, 6),
            "ci_high":  round(ci_high, 6),
            "confidence_level": confidence_level,
        }

        return ComputedResult(
            kernel=self.name,
            kernel_version=KERNEL_VERSION,
            inputs=ids,
            outputs=outputs,
            uncertainty={"se": round(se, 6)},
            notes=(
                f"n={n} {'(CI approximate for small n — normal approximation, not t-distribution)' if n < 30 else ''}"
            ).strip(),
            reproducibility_hash=self._hash(self.name, KERNEL_VERSION, ids, values),
        )

    def effect_size(
        self,
        group_a:        Sequence[float],
        group_b:        Sequence[float],
        input_node_ids: Optional[Sequence[str]] = None,
    ) -> ComputedResult:
        """Cohen's d — standardized mean difference between two groups."""
        a, b = [float(v) for v in group_a], [float(v) for v in group_b]
        if len(a) < 2 or len(b) < 2:
            raise ValueError("effect_size requires at least 2 values per group")

        mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
        var_a = sum((v - mean_a) ** 2 for v in a) / (len(a) - 1)
        var_b = sum((v - mean_b) ** 2 for v in b) / (len(b) - 1)

        pooled_std = math.sqrt(
            ((len(a) - 1) * var_a + (len(b) - 1) * var_b) / (len(a) + len(b) - 2)
        )
        cohens_d = (mean_a - mean_b) / pooled_std if pooled_std > 0 else 0.0

        ids = list(input_node_ids) if input_node_ids else (
            [f"raw:a:{i}" for i in range(len(a))] + [f"raw:b:{i}" for i in range(len(b))]
        )
        all_values = a + b

        outputs = {
            "mean_a": round(mean_a, 6), "mean_b": round(mean_b, 6),
            "pooled_std": round(pooled_std, 6), "cohens_d": round(cohens_d, 6),
            "magnitude": self._interpret_cohens_d(cohens_d),
        }

        return ComputedResult(
            kernel="statistics.effect_size",
            kernel_version=KERNEL_VERSION,
            inputs=ids,
            outputs=outputs,
            reproducibility_hash=self._hash("statistics.effect_size", KERNEL_VERSION, ids, all_values),
        )

    @staticmethod
    def _interpret_cohens_d(d: float) -> str:
        d = abs(d)
        if d < 0.2:
            return "negligible"
        if d < 0.5:
            return "small"
        if d < 0.8:
            return "medium"
        return "large"

    @staticmethod
    def _z_for_confidence(level: float) -> float:
        # Common two-tailed z-scores; falls back to 1.96 (95%) for unlisted levels.
        table = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        return table.get(round(level, 2), 1.96)
