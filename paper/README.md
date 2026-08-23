# Victor -- AAAI-27 Submission Paper

## Files

| File | Purpose |
|------|---------|
| `victor_aaai27.tex` | Main LaTeX source (AAAI-27 formatted) |
| `references.bib` | BibTeX bibliography (18 references) |
| `reproducibility_checklist.tex` | Separate reproducibility checklist PDF |
| `README.md` | This file |

## Prerequisites

- LaTeX distribution: TeX Live 2023+ or MiKTeX
- The official **AAAI-27 Author Kit** from `aaai.org`

## Getting the Official AAAI-27 Author Kit

The AAAI style files **must** be obtained from the official source:

1. **https://aaai.org/conference/aaai/aaai-27/**
2. Navigate to **Submission Instructions** $\rightarrow$ **Author Kit**
3. Download the ZIP archive containing:
   - `aaai27.sty` (or `aaai.sty`) -- the style file
   - `aaai27.bst` (or `aaai.bst`) -- the bibliography style
4. Place both files in this `paper/` directory

> **If the kit uses year-specific filenames** (e.g., `aaai27.sty`, `aaai27.bst`):
> Change line 7 in `victor_aaai27.tex` from:
> ```latex
> \usepackage[submission]{aaai}
> ```
> to:
> ```latex
> \usepackage[submission]{aaai27}
> ```
> The `aaai.sty` file handles bibliography style internally -- no `\bibliographystyle{}` command is needed.

## Compilation

```bash
cd paper/
pdflatex victor_aaai27 && bibtex victor_aaai27 && pdflatex victor_aaai27 && pdflatex victor_aaai27
```

For reproducibility checklist (separate PDF):
```bash
pdflatex reproducibility_checklist
```

## Overleaf (Recommended)

1. Go to https://www.overleaf.com
2. Create new blank project
3. Upload all files from `paper/` directory
4. Set compiler to **pdfLaTeX**
5. Compile

## Page Limit

AAAI-27: **7 pages** of main content + additional pages for references only.

## Paper Structure

```
Title & Authors
Abstract
1.  Introduction (contributions listed as bulleted items)
2.  Related Work (RAG, KG-QA, NLI, Agentic RAG, PKM)
3.  System Design (Epistemic Artifact, graph, ingestion, retrieval,
                   conflict detection, reasoning, sovereignty, kernels)
4.  Implementation (Python v5.3.0, 16 modules, 196 tests)
5.  Evaluation (SciFact, 5 configurations, best 71.0%)
6.  Discussion (agreement bias, label-order, covert channel)
7.  Limitations (6 items)
8.  Conclusion
References
```

## AAAI Formatting Notes

- Uses `\usepackage[submission]{aaai}` -- DO NOT change or add other packages
- No `hyperref`, `geometry`, `fullpage`, `setspace`, `titlesec`, `float`, `authblk`
- No `\newpage`, `\pagebreak`, `\clearpage`, `\addtolength`, `\vspace{-}` in proximity to floats
- Section numbering off by default (`\setcounter{secnumdepth}{0}`)
