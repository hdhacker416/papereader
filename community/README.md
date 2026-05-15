# PaperReader Community Prototypes

This folder holds isolated prototypes for the future paper-as-persona community
feature. The first building block is figure extraction from PDFs.

## Figure Extraction

The extractor is caption-driven:

1. Find figure captions such as `Fig. 1` or `Figure 2`.
2. Collect nearby PDF image blocks and vector drawing blocks.
3. Infer a crop bounding box for the figure plus caption.
4. Render both the cropped figure and the source page screenshot.
5. Write a JSON manifest for downstream review and answer generation.

Install dependency:

```bash
python -m pip install PyMuPDF
```

Run on one PDF:

```bash
python -m community.figure_extractor path/to/paper.pdf --output community/output/paper-id
```

Useful flags:

```bash
python -m community.figure_extractor path/to/paper.pdf \
  --output community/output/paper-id \
  --dpi 180 \
  --max-pages 8
```

Output:

```text
community/output/paper-id/
  figures.json
  pages/
    page_001.png
  figures/
    fig_001_page_001.png
```

The `figures.json` manifest stores page numbers, labels, captions, PDF-space
bounding boxes, rendered image paths, confidence scores, and warnings. This is
intended to make extraction quality easy to inspect before connecting it to the
web product.

## Persona Answer Experiment

The current community prototype uses route 4 as the default online path:

1. Search papers from the installed research packs.
2. Download the selected PDFs.
3. Extract local PDF text.
4. Extract figure crops and figure captions locally.
5. Ask DeepSeek to write a first-person, paper-as-persona answer from the text
   and figure manifest.

This avoids the Qwen PDF upload path for user-facing latency. In testing, normal
Qwen chat was fast, but Qwen's PDF/file path could report `processed` while the
chat endpoint still returned `File parsing in progress`, causing multi-minute
waits. Qwen PDF baselines are still available for comparison, but they are not
the default experiment path.

Run the default route 4 experiment:

```bash
python -m community.persona_answer_experiment --limit 5
```

Run the slower Qwen PDF baselines as well:

```bash
python -m community.persona_answer_experiment --limit 5 --include-qwen-baselines
```
