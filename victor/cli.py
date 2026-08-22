"""
Victor CLI — v4.1

Command-line entry point. Every subcommand is a thin wrapper around the
public Victor API in victor/core.py — the CLI does no business logic of
its own, it only formats output with rich.

Usage:
    python -m victor.cli --help
    victor --help                     (if installed as a console script)

Global options (e.g. --home, --mock-llm) go BEFORE the subcommand:
    victor --mock-llm ask "what did the baseline experiment show?"
"""
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from .core import Victor
from .config import VictorConfig


console = Console()


# ── Root group ────────────────────────────────────────────────────────────────

@click.group()
@click.option(
    "--home", "home_dir", type=click.Path(), default=None,
    help="Override Victor's data directory (default: ~/.victor, or $VICTOR_HOME).",
)
@click.option(
    "--mock-llm", is_flag=True, default=False,
    help="Force mock LLM mode — no Ollama/OpenAI calls. Useful for testing offline.",
)
@click.pass_context
def cli(ctx: click.Context, home_dir: Optional[str], mock_llm: bool):
    """Victor — local-first research, memory, and intelligence platform."""
    kwargs = {}
    if home_dir:
        kwargs["home_dir"] = home_dir
    config = VictorConfig(**kwargs)
    if mock_llm:
        config.use_mock_llm = True
    ctx.obj = Victor(config=config)


def _v(ctx: click.Context) -> Victor:
    return ctx.obj


def _print_node_table(nodes, title: str):
    if not nodes:
        console.print(f"[dim]No {title.lower()} found.[/dim]")
        return
    table = Table(title=title)
    table.add_column("ID")
    table.add_column("Label")
    table.add_column("Importance")
    table.add_column("Status")
    for n in nodes:
        meta = n.get("metadata", {})
        table.add_row(
            n["id"][:12],
            (n.get("label") or "")[:60],
            f"{meta.get('importance_score', 0):.2f}",
            meta.get("epistemic_status", ""),
        )
    console.print(table)


# ── Ingestion ─────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--title", default=None, help="Override the source title (default: filename).")
@click.option(
    "--extract-claims/--no-extract-claims", "extract_claims", default=None,
    help="Force claim extraction on/off for this file (default: config setting).",
)
@click.option(
    "--type", "source_type", default=None,
    type=click.Choice(["paper", "note"], case_sensitive=False),
    help="Override source type: paper (LITERATURE tier) or note (NOTE tier).",
)
@click.pass_context
def ingest(ctx, filepath, title, extract_claims, source_type):
    """Ingest a PDF, Markdown/text note, or experiment JSON file."""
    v = _v(ctx)
    try:
        result = v.ingest_file(filepath, title=title, extract_claims=extract_claims, source_type=source_type)
    except Exception as e:
        console.print(f"[red]Ingestion failed:[/red] {e}")
        raise SystemExit(1)

    console.print(
        f"[green]Ingested[/green] {result['type']} '{result['title']}' "
        f"({result.get('n_chunks', 0)} chunks) — source_id={result['source_id']}"
    )

    if "n_claims" in result:
        console.print(
            f"  Claims extracted: {result['n_claims']}   Concepts: {result.get('n_concepts', 0)}"
        )
        for c in result.get("claims", [])[:10]:
            flag = " [yellow](low-confidence)[/yellow]" if c["low_confidence"] else ""
            console.print(f"    • [{c['epistemic_status']}] {c['text'][:100]}{flag}")

    if "linked_claims" in result:
        if not result["linked_claims"]:
            console.print("  [dim]No claims matched closely enough to link.[/dim]")
        for link in result["linked_claims"]:
            console.print(
                f"    • {link['edge'].upper()} -> {link['claim'][:80]} "
                f"(confidence={link['confidence']:.2f})"
            )


# ── Observe (Reality → Artifact pipeline) ─────────────────────────────────────

@cli.command()
@click.option(
    "--image", "image_path", default=None, type=click.Path(exists=True),
    help="Path to an existing image file to classify (skips webcam capture).",
)
@click.option(
    "--camera", "use_camera", is_flag=True, default=False,
    help="Capture one frame from the webcam.",
)
@click.option(
    "--audio", "audio_path", default=None, type=click.Path(exists=True),
    help="Path to an existing audio file to classify (skips mic recording).",
)
@click.option(
    "--mic", "use_mic", is_flag=True, default=False,
    help="Record audio from the microphone for --duration seconds.",
)
@click.option(
    "--duration", "-d", default=5, type=int,
    help="Audio recording duration in seconds (default: 5).",
)
@click.option(
    "--labels", "-l", default=None,
    help="Comma-separated candidate labels, e.g. 'steel,aluminum,copper'.",
)
@click.option(
    "--confidence", "-c", default=None, type=float,
    help="Confidence override 0.0–1.0 (skips model; use with --labels for manual entry).",
)
@click.option(
    "--sensor", "-s", default="camera",
    type=click.Choice(["camera", "audio"], case_sensitive=False),
    help="Sensor type (camera or audio).",
)
@click.option(
    "--gaps", default=None,
    help="Extra verification gaps, comma-separated.",
)
@click.option(
    "--session", default=None,
    help="Session ID to group related observations.",
)
@click.option(
    "--mock", is_flag=True, default=False,
    help="Use mock classifier (for testing without GPU/model download).",
)
@click.pass_context
def observe(ctx, image_path, use_camera, audio_path, use_mic, duration, labels, confidence, sensor, gaps, session, mock):
    """
    Capture one sensor observation and store it as a MEASUREMENT node.

    This is the Reality → Artifact pipeline. A sensor reading becomes a
    graph node with all 6 Epistemic Artifact properties.

    \b
    Camera examples:
      victor observe --image photo.jpg --labels "steel,aluminum,copper"
      victor observe --camera --labels "quartz,feldspar,mica"
      victor observe --image sample.jpg --labels "unknown" --confidence 0.6 \\
                     --gaps "needs spectroscopy"

    \b
    Audio examples:
      victor observe --sensor audio --audio recording.wav --labels "speech,music,noise"
      victor observe --sensor audio --mic --labels "bird,insect,wind"
      victor observe --sensor audio --mic --duration 10 --labels "engine,humming,silence"
    """
    # ── Validate source ───────────────────────────────────────────────────────
    if sensor == "camera":
        if not image_path and not use_camera:
            console.print(
                "[red]Error:[/red] provide --image <path> or --camera flag.\n"
                "Example: victor observe --image photo.jpg --labels 'steel,aluminum'"
            )
            raise SystemExit(1)
    elif sensor == "audio":
        if not audio_path and not use_mic:
            console.print(
                "[red]Error:[/red] provide --audio <path> or --mic flag.\n"
                "Example: victor observe --sensor audio --audio recording.wav \\\n                       --labels 'speech,music,noise'"
            )
            raise SystemExit(1)

    if not labels:
        console.print(
            "[red]Error:[/red] --labels is required.\n"
            "Example: --labels 'label1,label2,label3'"
        )
        raise SystemExit(1)

    candidate_labels = [l.strip() for l in labels.split(",") if l.strip()]
    extra_gaps       = [g.strip() for g in gaps.split(",")] if gaps else None

    # ── Build classifier ──────────────────────────────────────────────────────
    clf = None
    if mock:
        if sensor == "audio":
            from victor.sensors import MockAudioClassifier
            clf = MockAudioClassifier(
                fixed_label      = candidate_labels[0],
                fixed_confidence = confidence if confidence is not None else 0.87,
            )
        else:
            from victor.sensors import MockClassifier
            clf = MockClassifier(
                fixed_label      = candidate_labels[0],
                fixed_confidence = confidence if confidence is not None else 0.87,
            )
    elif confidence is not None:
        # User-supplied confidence → manual classification, skip model
        if sensor == "audio":
            from victor.sensors import MockAudioClassifier
            clf = MockAudioClassifier(
                fixed_label      = candidate_labels[0],
                fixed_confidence = confidence,
            )
        else:
            from victor.sensors import MockClassifier
            clf = MockClassifier(
                fixed_label      = candidate_labels[0],
                fixed_confidence = confidence,
            )

    v = _v(ctx)
    source_desc = (
        "camera" if use_camera else
        image_path if image_path else
        "microphone" if use_mic else
        audio_path if audio_path else "unknown"
    )
    console.print(
        f"[dim]Observing with sensor=[{sensor}] source={source_desc} ...[/dim]"
    )

    # ── Execute observation ───────────────────────────────────────────────────
    try:
        if sensor == "audio":
            result = v.observe(
                sensor           = "audio",
                audio_path       = audio_path,
                audio_duration   = duration,
                candidate_labels = candidate_labels,
                classifier       = clf,
                extra_gaps       = extra_gaps,
                session_id       = session,
            )
        else:
            result = v.observe(
                sensor           = "camera",
                image_path       = image_path,
                camera_index     = 0,
                candidate_labels = candidate_labels,
                classifier       = clf,
                extra_gaps       = extra_gaps,
                session_id       = session,
            )
    except Exception as e:
        console.print(f"[red]Observation failed:[/red] {e}")
        raise SystemExit(1)

    # ── Display the Epistemic Artifact ────────────────────────────────────────
    ep = result["epistemic_status"].upper()
    console.print(f"\n[green]✓ Observation stored[/green]  [{ep}]  node_id={result['node_id']}")
    console.print(f"\n  [bold]Label:[/bold]       {result['label']}")
    console.print(f"  [bold]Confidence:[/bold]  {result['confidence']:.1%}")
    console.print(f"  [bold]Sensor:[/bold]      {result['sensor_id']}")
    console.print(f"  [bold]Model:[/bold]       {result['model_used']}")
    console.print(f"  [bold]Timestamp:[/bold]   {result['timestamp'][:19]}")
    if result.get("media_path"):
        console.print(f"  [bold]Media saved:[/bold] {result['media_path']}")
    if result.get("image_path"):
        console.print(f"  [bold]Image saved:[/bold] {result['image_path']}")
    console.print("\n  [bold]Gaps[/bold] (what needs verification):")
    for g in result["gaps"]:
        console.print(f"    • {g}")
    console.print(
        "\n  [dim]Use 'victor ask \"what did I observe today?\"' to query observations.[/dim]"
    )


# ── Query ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("query")
@click.option("--full", is_flag=True, help="Also show retrieved chunks + provenance.")
@click.option(
    "--show-patterns/--no-show-patterns", "show_patterns", default=True,
    help="Inject PatternDetector insights if the query matches a known weak topic (default: on).",
)
@click.option(
    "--digest", is_flag=True, default=False,
    help="Show a pattern digest after the answer (conversation stats, recurring topics, suggestions).",
)
@click.pass_context
def ask(ctx, query, full, show_patterns, digest):
    """Ask Victor a question grounded in your knowledge base."""
    v = _v(ctx)

    # Show retriever type indicator
    stats = v.stats()
    retriever_type = stats.get("retriever_type", "unknown")
    tool_count = stats.get("tool_count", 0)
    if retriever_type == "AgenticRetriever":
        console.print(f"[dim]-> Agentic loop active ({tool_count} tools available)[/dim]")
    else:
        console.print(f"[dim]-> Single-shot mode[/dim]")

    # Use pattern-aware ask if requested
    if show_patterns:
        answer = v.ask_with_patterns(query)
    else:
        answer = v.ask_full(query)

    console.print()

    # Format the answer — detect agent loop trace and highlight it
    ans_text = answer.answer
    if "_[Agent loop:" in ans_text:
        # Split the answer from the trace
        parts = ans_text.split("_[Agent loop:", 1)
        console.print(parts[0])
        console.print()
        # Show the trace in a panel
        trace_text = "_[Agent loop:" + parts[1]
        trace_text = trace_text.replace("_[", "").replace("]_", "")
        console.print(Panel(
            trace_text,
            title="[bold blue]Agent Loop Trace[/bold blue]",
            border_style="blue",
        ))
    else:
        console.print(ans_text)

    console.print()
    console.print(f"[dim]provider: {answer.provider_used} | sources: {answer.provenance_summary}[/dim]")

    if full and answer.retrieved_chunks:
        table = Table(title="Retrieved chunks")
        table.add_column("#")
        table.add_column("Status")
        table.add_column("Source")
        table.add_column("Score")
        table.add_column("Text")
        for i, c in enumerate(answer.retrieved_chunks, 1):
            table.add_row(
                str(i), c.epistemic_status, c.source_title[:30],
                f"{c.score:.2f}", c.text[:80].replace("\n", " "),
            )
        console.print(table)

    # Pattern digest (Step 3 surface)
    if digest:
        _show_pattern_digest(v)


def _show_pattern_digest(v: Victor):
    """Display a PatternDetector digest panel."""
    digest = v.get_pattern_digest()

    console.print()
    lines = []
    lines.append(f"Conversations: {digest['total_conversations']}")
    lines.append(f"Priority gaps: {digest['n_priority_gaps']}")

    if digest["recurring_weak_topics"]:
        lines.append("\n[bold yellow]Recurring weak topics:[/bold yellow]")
        for topic in digest["recurring_weak_topics"]:
            lines.append(f"  • '{topic['topic'][:50]}' — queried {topic['query_count']}x")

    if digest["suggestions"]:
        lines.append("\n[bold green]Suggested experiments:[/bold green]")
        for s in digest["suggestions"][:3]:
            lines.append(f"  • {s[:100]}")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Pattern Digest[/bold]",
        border_style="yellow",
    ))


# ── Evaluation ────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("eval_file", type=click.Path(exists=True))
@click.option("--k", default=5, help="Cutoff for precision@k / hit@k.")
@click.pass_context
def evaluate(ctx, eval_file, k):
    """Run retrieval evaluation (precision@k, hit@k, MRR) against a labeled query set."""
    v = _v(ctx)
    metrics = v.evaluate(eval_file, k=k)
    if not metrics:
        console.print("[yellow]No queries found in eval file.[/yellow]")
        return

    per_query = metrics.pop("per_query", [])
    for key, val in metrics.items():
        console.print(f"{key}: {val}")

    table = Table(title="Per-query results")
    table.add_column("Query")
    table.add_column("Hit")
    table.add_column("Precision")
    table.add_column("RR")
    for q in per_query:
        table.add_row(q["query"][:50], "✓" if q["hit"] else "✗", str(q["precision"]), str(q["rr"]))
    console.print(table)


# ── Reasoning layer ───────────────────────────────────────────────────────────

@cli.command()
@click.option("--min-importance", default=0.0, type=float, help="Only show gaps at/above this importance.")
@click.pass_context
def gaps(ctx, min_importance):
    """List claims with no experimental confirmation (actionable research gaps)."""
    v = _v(ctx)
    results = v.gaps(min_importance=min_importance)
    if not results:
        console.print("[green]No gaps found.[/green]")
        return

    table = Table(title="Unconfirmed claims")
    table.add_column("Claim ID")
    table.add_column("Status")
    table.add_column("Text")
    table.add_column("Contradicts")
    for g in results:
        table.add_row(g.claim_id[:10], g.epistemic_status, g.claim_text[:80], str(g.n_contradicts))
    console.print(table)


@cli.command()
@click.argument("claim_id")
@click.pass_context
def evidence(ctx, claim_id):
    """Show the weighted evidence summary for a specific claim node."""
    v = _v(ctx)
    summary = v.evidence(claim_id)
    if summary is None:
        console.print(f"[red]No such claim:[/red] {claim_id}")
        raise SystemExit(1)
    console.print_json(data=summary.__dict__)


@cli.command()
@click.pass_context
def patterns(ctx):
    """Analyze conversation history for usage patterns (Phase B self-learning)."""
    v = _v(ctx)
    result = v.patterns()

    console.print(f"Total conversations: {result['total_conversations']}")

    console.print("\n[bold]Top queried sources:[/bold]")
    if result["top_queried_sources"]:
        # Items are dicts {source_id, count, label} from PatternDetector.analyze()
        for src in result["top_queried_sources"]:
            console.print(f"  {src['count']:>3}  {src['label']}")
    else:
        console.print("  [dim](none yet)[/dim]")

    console.print("\n[bold]Suggested experiments:[/bold]")
    if result["suggested_experiments"]:
        for s in result["suggested_experiments"]:
            console.print(f"  • {s}")
    else:
        console.print("  [dim](none yet)[/dim]")

    # Also show the rich digest
    _show_pattern_digest(v)


@cli.command()
@click.pass_context
def decay(ctx):
    """Manually trigger a temporal decay pass over all graph nodes (F-014)."""
    v = _v(ctx)
    v.apply_decay()
    console.print("[green]Temporal decay applied and graph saved.[/green]")


# ── Node inspection / control ─────────────────────────────────────────────────

@cli.command()
@click.argument("node_id")
@click.pass_context
def inspect(ctx, node_id):
    """Show a full structured view of any graph node by ID."""
    v = _v(ctx)
    result = v.inspect(node_id)
    if result is None:
        console.print(f"[red]No such node:[/red] {node_id}")
        raise SystemExit(1)
    console.print_json(data=result)


@cli.command()
@click.argument("node_id")
@click.pass_context
def freeze(ctx, node_id):
    """Lock a node so it can't be overwritten by future extraction."""
    v = _v(ctx)
    ok = v.freeze(node_id)
    if ok:
        console.print(f"[green]Frozen:[/green] {node_id}")
    else:
        console.print(f"[red]No such node:[/red] {node_id}")
        raise SystemExit(1)


@cli.command()
@click.argument("node_id")
@click.pass_context
def unfreeze(ctx, node_id):
    """Unlock a previously frozen node."""
    v = _v(ctx)
    ok = v.unfreeze(node_id)
    if ok:
        console.print(f"[green]Unfrozen:[/green] {node_id}")
    else:
        console.print(f"[red]No such node:[/red] {node_id}")
        raise SystemExit(1)


@cli.command()
@click.argument("source_id")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@click.pass_context
def delete(ctx, source_id, yes):
    """Delete a document and ALL nodes/chunks derived from it. Irreversible."""
    if not yes and not click.confirm(f"Delete source '{source_id}' and everything derived from it?"):
        console.print("Aborted.")
        return
    v = _v(ctx)
    result = v.delete(source_id)
    console.print(f"[green]Deleted[/green] {result['deleted_nodes']} graph node(s) and their vector chunks.")


@cli.command()
@click.argument("node_ids", nargs=-1, required=True)
@click.option("--output", "-o", required=True, type=click.Path(), help="Output JSON filepath.")
@click.option("--no-edges", is_flag=True, help="Exclude edges from the export.")
@click.pass_context
def export(ctx, node_ids, output, no_edges):
    """
    Export specific nodes to a JSON file — the permission switch.
    Nothing leaves your device unless you run this explicitly.
    """
    v = _v(ctx)
    result = v.export(list(node_ids), output, include_edges=not no_edges)
    console.print(
        f"[green]Exported[/green] {result['n_nodes']} node(s), "
        f"{result['n_edges']} edge(s) -> {result['filepath']}"
    )


@cli.command()
@click.argument("node_id")
@click.pass_context
def mask(ctx, node_id):
    """
    Mask a node — suppress its content from LLM answers while keeping
    it in the graph.

    The node's edges, embeddings, and connections remain fully active.
    ConflictDetector and GapDetector still see it. The LLM only sees
    an anchor placeholder: '[MASKED — ...]' until you unmask it.

    
    This is different from freeze:
      freeze  → prevents content from being overwritten
      mask    → suppresses content from surfacing in answers

    
    Example:
      victor mask abc123def456
      victor ask "what did we measure?" → shows [MASKED] anchor
      victor unmask abc123def456        → content surfaces again
    """
    v = _v(ctx)
    ok = v.mask(node_id)
    if ok:
        console.print(f"[yellow]Masked:[/yellow] {node_id}  — content withheld from answers.")
        console.print(f"[dim]Run 'victor unmask {node_id}' to reveal.[/dim]")
    else:
        console.print(f"[red]No such node:[/red] {node_id}")
        raise SystemExit(1)


@cli.command()
@click.argument("node_id")
@click.pass_context
def unmask(ctx, node_id):
    """Unmask a node — allow its content to surface in answers again."""
    v = _v(ctx)
    ok = v.unmask(node_id)
    if ok:
        console.print(f"[green]Unmasked:[/green] {node_id}  — content will now surface in answers.")
    else:
        console.print(f"[red]No such node:[/red] {node_id}")
        raise SystemExit(1)


# ── Introspection ─────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def stats(ctx):
    """Show vector store + graph statistics and LLM provider availability."""
    v = _v(ctx)
    console.print_json(data=v.stats())


@cli.group(name="list")
def list_group():
    """List nodes of a given type (claims, papers, experiments, conversations)."""


@list_group.command(name="claims")
@click.pass_context
def list_claims(ctx):
    """List every claim node in the graph."""
    _print_node_table(_v(ctx).list_claims(), "Claims")


@list_group.command(name="papers")
@click.pass_context
def list_papers(ctx):
    """List every paper node in the graph."""
    _print_node_table(_v(ctx).list_papers(), "Papers")


@list_group.command(name="experiments")
@click.pass_context
def list_experiments(ctx):
    """List every experiment node in the graph."""
    _print_node_table(_v(ctx).list_experiments(), "Experiments")


@list_group.command(name="conversations")
@click.pass_context
def list_conversations(ctx):
    """List every conversation node in the graph."""
    _print_node_table(_v(ctx).list_conversations(), "Conversations")


@list_group.command(name="masked")
@click.pass_context
def list_masked(ctx):
    """List every node currently masked (content suppressed from answers)."""
    nodes = _v(ctx).list_masked()
    if not nodes:
        console.print("[dim]No masked nodes.[/dim]")
        return
    table = Table(title="Masked Nodes")
    table.add_column("ID")
    table.add_column("Type")
    table.add_column("Label")
    table.add_column("Frozen", justify="center")
    table.add_column("Importance", justify="right")
    for n in nodes:
        meta = n.get("metadata", {})
        table.add_row(
            n["id"][:16],
            n.get("ntype", ""),
            (n.get("label") or "")[:60],
            "✓" if meta.get("frozen") else "",
            f"{meta.get('importance_score', 0):.2f}",
        )
    console.print(table)
    console.print(f"[dim]{len(nodes)} masked node(s). Run 'victor unmask <id>' to reveal.[/dim]")


# ── Computation kernels (DoD #8: StatisticsKernel) ─────────────────────────────

@cli.group(name="compute")
def compute_group():
    """Run computation kernels on graph nodes (statistics, effect size)."""


@compute_group.command(name="stats")
@click.argument("nodes", nargs=-1, required=True)
@click.option("--metric", default="value", help="Metric name to extract from node metadata (default: value).")
@click.option("--confidence", default=0.95, type=float, help="Confidence level for CI (default: 0.95).")
@click.pass_context
def compute_stats(ctx, nodes, metric, confidence):
    """Compute descriptive statistics (mean, variance, std, CI) over node values."""
    v = _v(ctx)
    try:
        result = v.compute_statistics(
            node_ids=list(nodes),
            metric_name=metric,
            confidence_level=confidence,
        )
    except Exception as e:
        console.print(f"[red]Statistics computation failed:[/red] {e}")
        raise SystemExit(1)

    # Summary panel
    console.print(Panel(
        f"Computed node: [bold cyan]{result['computed_node_id']}[/bold cyan]\n"
        f"Kernel: {result['kernel']} v{result['kernel_version']}\n"
        f"Inputs: {result['n_values']} values from {len(result['input_node_ids'])} node(s)\n"
        f"Reproducibility hash: {result['reproducibility_hash'][:24]}…",
        title="[bold green]Statistics Computed[/bold green]",
        border_style="green",
    ))

    # Results table
    table = Table(title="Descriptive Statistics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    outputs = result["outputs"]
    table.add_row("n", f"{int(outputs['n'])}")
    table.add_row("Mean", f"{outputs['mean']:.6f}")
    table.add_row("Variance", f"{outputs['variance']:.6f}")
    table.add_row("Std Dev", f"{outputs['std']:.6f}")
    table.add_row(f"CI ({outputs['confidence_level']*100:.0f}%)",
                  f"[{outputs['ci_low']:.6f}, {outputs['ci_high']:.6f}]")
    if result.get("uncertainty"):
        table.add_row("Std Error", f"{result['uncertainty'].get('se', 0):.6f}")
    console.print(table)

    if result.get("notes"):
        console.print(f"[dim]Note: {result['notes']}[/dim]")


@compute_group.command(name="effect")
@click.option("--group-a", required=True, multiple=True, help="Node IDs for group A.")
@click.option("--group-b", required=True, multiple=True, help="Node IDs for group B.")
@click.pass_context
def compute_effect(ctx, group_a, group_b):
    """Compute Cohen's d effect size between two groups of nodes."""
    v = _v(ctx)
    try:
        result = v.compute_effect_size(
            group_a_node_ids=list(group_a),
            group_b_node_ids=list(group_b),
        )
    except Exception as e:
        console.print(f"[red]Effect size computation failed:[/red] {e}")
        raise SystemExit(1)

    # Summary panel
    console.print(Panel(
        f"Computed node: [bold cyan]{result['computed_node_id']}[/bold cyan]\n"
        f"Kernel: {result['kernel']} v{result['kernel_version']}\n"
        f"Group A: {result['n_group_a']} values from {len(result['group_a_node_ids'])} node(s)\n"
        f"Group B: {result['n_group_b']} values from {len(result['group_b_node_ids'])} node(s)\n"
        f"Reproducibility hash: {result['reproducibility_hash'][:24]}…",
        title="[bold green]Effect Size Computed[/bold green]",
        border_style="green",
    ))

    # Results table
    outputs = result["outputs"]
    magnitude_color = {
        "negligible": "dim",
        "small": "yellow",
        "medium": "bold yellow",
        "large": "bold red",
    }.get(outputs.get("magnitude", ""), "white")

    table = Table(title="Effect Size (Cohen's d)")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Mean A", f"{outputs['mean_a']:.6f}")
    table.add_row("Mean B", f"{outputs['mean_b']:.6f}")
    table.add_row("Pooled Std", f"{outputs['pooled_std']:.6f}")
    table.add_row("Cohen's d", f"{outputs['cohens_d']:.6f}")
    table.add_row("Magnitude", f"[{magnitude_color}]{outputs['magnitude']}[/{magnitude_color}]")
    console.print(table)


if __name__ == "__main__":
    cli()
