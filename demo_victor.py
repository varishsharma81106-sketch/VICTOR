#!/usr/bin/env python3
"""
Victor Demo — See what's built with your own eyes
Run: python demo_victor.py

No GPU required. CPU only.
"""

import sys
from pathlib import Path

# Add victor to path
sys.path.insert(0, str(Path(__file__).parent))

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_step(num, text):
    print(f"\n[{num}] {text}")
    print("-" * 40)

def main():
    print_header("VICTOR DEMO — Local-First Research Intelligence")
    
    # Step 1: Initialize Victor
    print_step(1, "Initializing Victor...")
    try:
        from victor import Victor
        from victor.config import VictorConfig
        
        # Use mock embedder for speed (no model download needed)
        config = VictorConfig(
            use_mock_embedder=True,
            use_mock_nli=True,
            use_mock_llm=False,  # Use real LLM if Ollama is running
        )
        
        v = Victor(config)
        print("  ✓ Victor initialized successfully")
        print(f"  ✓ Graph: {v.graph._g.number_of_nodes()} nodes, {v.graph._g.number_of_edges()} edges")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        print("  Try: pip install -e .")
        return
    
    # Step 2: Show stats
    print_step(2, "Current Knowledge Graph Stats")
    stats = v.stats()
    print(f"  Nodes: {stats['graph']['nodes']}")
    print(f"  Edges: {stats['graph']['edges']}")
    print(f"  LLM: {stats['llm_model']}")
    print(f"  LLM Online: {stats['llm_online']}")
    print(f"  Retriever: {stats['retriever_type']}")
    print(f"  Tools: {stats['tool_count']}")
    
    # Step 3: Ingest a sample paper
    print_step(3, "Ingesting Sample Paper...")
    sample_paper = Path("examples/sample_paper.md")
    if sample_paper.exists():
        result = v.ingest_file(sample_paper, source_type="paper")
        print(f"  ✓ Ingested: {result.get('title', 'Unknown')}")
        print(f"  ✓ Source ID: {result.get('source_id', 'N/A')}")
        print(f"  ✓ Chunks: {result.get('n_chunks', 0)}")
        print(f"  ✓ Claims: {result.get('n_claims', 0)}")
        print(f"  ✓ Concepts: {result.get('n_concepts', 0)}")
    else:
        print("  ⚠ Sample paper not found, skipping ingestion")
    
    # Step 4: Show updated stats
    print_step(4, "Updated Knowledge Graph")
    stats = v.stats()
    print(f"  Nodes: {stats['graph']['nodes']}")
    print(f"  Edges: {stats['graph']['edges']}")
    
    # Step 5: Ask a question (if LLM is available)
    print_step(5, "Asking Victor a Question...")
    if stats['llm_online']:
        try:
            answer = v.ask("What is the main contribution of this paper?")
            print(f"  Answer: {answer[0][:200]}...")
        except Exception as e:
            print(f"  ⚠ LLM not available: {e}")
            print("  Start Ollama: ollama serve")
    else:
        print("  ⚠ Ollama not running. Start it: ollama serve")
    
    # Step 6: Show gaps
    print_step(6, "Research Gaps (what's unconfirmed)")
    try:
        gaps = v.gaps()
        if gaps:
            for i, gap in enumerate(gaps[:3], 1):
                print(f"  {i}. {gap.claim_text[:80]}...")
        else:
            print("  No gaps found (all claims confirmed)")
    except Exception as e:
        print(f"  ⚠ Error: {e}")
    
    # Step 7: Show masked memory demo
    print_step(7, "Masked Memory Demo")
    if stats['graph']['nodes'] > 0:
        # Get a node to mask
        claims = v.list_claims()
        if claims:
            node_id = claims[0]['node_id']
            print(f"  Masking node: {node_id[:16]}...")
            v.mask(node_id)
            print(f"  ✓ Node masked")
            
            # Show it's now masked
            masked = v.list_masked()
            print(f"  ✓ Masked nodes: {len(masked)}")
            
            # Unmask it
            v.unmask(node_id)
            print(f"  ✓ Node unmasked")
        else:
            print("  No claims to mask")
    else:
        print("  No nodes in graph yet")
    
    # Summary
    print_header("DEMO COMPLETE")
    print("What you just saw:")
    print("  1. Victor initializes with local models (no cloud)")
    print("  2. Ingests papers and extracts claims/concepts")
    print("  3. Builds a typed knowledge graph")
    print("  4. Answers questions using the graph")
    print("  5. Surfaces research gaps")
    print("  6. Masks/unmasks sensitive content")
    print()
    print("Next steps:")
    print("  - Start Ollama: ollama serve")
    print("  - Run: python demo_victor.py")
    print("  - Ask real questions about your research")
    print()
    print("For more:")
    print("  - Read: docs/VICTOR_STATUS_2026-08-12.md")
    print("  - Docs: docs/VICTOR_INDEX.md")

if __name__ == "__main__":
    main()
