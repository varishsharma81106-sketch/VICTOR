"""
test_unmask_audit_log.py

Verifies that every mask/unmask operation writes a correctly structured
JSONL entry to the unmask audit log, and that failed operations (node
doesn't exist) are also recorded.
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from victor.graph import VictorKnowledgeGraph
from victor.config import VictorConfig


# ── Minimal Victor stand-in ───────────────────────────────────────────────────

def _make_victor_core(tmp_path: Path):
    """
    Build a minimal Victor-like object with only config, graph, mask, unmask,
    and _write_mask_audit — no LLM, no embedder, no vector store.
    We import the real Victor class and substitute a mock embedder so the
    graph initialises without touching disk-heavy dependencies.
    """
    from victor.core import Victor

    cfg = VictorConfig(home_dir=tmp_path)
    cfg.ensure_dirs()

    # Mock embedder — graph needs one but we won't call embed()
    mock_embedder = MagicMock()
    mock_embedder.embed.return_value = [0.0] * 384

    graph = VictorKnowledgeGraph(cfg.graph_file, mock_embedder)

    # Build a Victor instance without calling __init__ (avoids ChromaDB / Ollama)
    v = object.__new__(Victor)
    v.config = cfg
    v.graph  = graph

    # Bind the real methods we need
    import types
    from victor.core import Victor as V
    v.mask               = types.MethodType(V.mask, v)
    v.unmask             = types.MethodType(V.unmask, v)
    v._write_mask_audit  = types.MethodType(V._write_mask_audit, v)

    return v


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestUnmaskAuditLog:

    def test_mask_writes_audit_entry(self, tmp_path):
        v = _make_victor_core(tmp_path)
        v.graph.add_node("n1", "claim", "some claim text", {})

        ok = v.mask("n1")
        assert ok

        log_path = v.config.unmask_audit_log_file
        assert log_path.exists(), "audit log file must be created on first mask"

        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 1
        e = entries[0]
        assert e["action"]  == "mask"
        assert e["node_id"] == "n1"
        assert e["success"] is True
        assert "ts" in e
        # Accept both ISO 8601 UTC forms: trailing Z or +00:00 offset
        assert "Z" in e["ts"] or "+00:00" in e["ts"], f"expected UTC timestamp, got: {e['ts']}"

    def test_unmask_writes_audit_entry(self, tmp_path):
        v = _make_victor_core(tmp_path)
        v.graph.add_node("n1", "claim", "some claim text", {})
        v.mask("n1")

        ok = v.unmask("n1")
        assert ok

        log_path = v.config.unmask_audit_log_file
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 2
        assert entries[0]["action"] == "mask"
        assert entries[1]["action"] == "unmask"
        assert entries[1]["node_id"] == "n1"
        assert entries[1]["success"] is True

    def test_failed_mask_still_logged(self, tmp_path):
        """Mask on a non-existent node returns False AND is still logged."""
        v = _make_victor_core(tmp_path)

        ok = v.mask("does_not_exist")
        assert not ok

        log_path = v.config.unmask_audit_log_file
        assert log_path.exists()
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["node_id"] == "does_not_exist"

    def test_failed_unmask_still_logged(self, tmp_path):
        """Unmask on a non-existent node returns False AND is still logged."""
        v = _make_victor_core(tmp_path)

        ok = v.unmask("ghost_node")
        assert not ok

        log_path = v.config.unmask_audit_log_file
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert entries[0]["success"] is False
        assert entries[0]["action"] == "unmask"

    def test_multiple_operations_append_not_overwrite(self, tmp_path):
        v = _make_victor_core(tmp_path)
        v.graph.add_node("a", "claim", "claim a", {})
        v.graph.add_node("b", "claim", "claim b", {})

        v.mask("a")
        v.mask("b")
        v.unmask("a")

        log_path = v.config.unmask_audit_log_file
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 3
        assert [e["action"] for e in entries] == ["mask", "mask", "unmask"]
        assert [e["node_id"] for e in entries] == ["a", "b", "a"]

    def test_audit_entries_have_caller_field(self, tmp_path):
        v = _make_victor_core(tmp_path)
        v.graph.add_node("n1", "claim", "text", {})
        v.mask("n1")

        log_path = v.config.unmask_audit_log_file
        entry = json.loads(log_path.read_text().strip().splitlines()[0])
        assert "caller" in entry
        assert entry["caller"] != ""

    def test_log_path_follows_config(self, tmp_path):
        """The audit log lands at config.unmask_audit_log_file, not hardcoded."""
        v = _make_victor_core(tmp_path)
        custom_log = tmp_path / "custom_logs" / "my_audit.jsonl"
        v.config.unmask_audit_log_file = custom_log
        v.graph.add_node("n1", "claim", "text", {})

        v.mask("n1")

        assert custom_log.exists(), "audit log must write to configured path"
        entry = json.loads(custom_log.read_text().strip())
        assert entry["node_id"] == "n1"

    def test_timestamps_are_chronological(self, tmp_path):
        """Log entries must be strictly non-decreasing in time."""
        import time
        v = _make_victor_core(tmp_path)
        v.graph.add_node("n1", "claim", "text", {})
        v.graph.add_node("n2", "claim", "text2", {})

        v.mask("n1")
        time.sleep(0.01)
        v.mask("n2")

        log_path = v.config.unmask_audit_log_file
        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert entries[0]["ts"] <= entries[1]["ts"]
