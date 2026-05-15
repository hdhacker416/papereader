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

