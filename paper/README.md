# Manuscript: box-subdivision outer approximation

Target journal: *Structural and Multidisciplinary Optimization* (Springer Nature).

Build: `latexmk -pdf main.tex`

- Without `sn-jnl.cls` the manuscript falls back to the `article` class for proofreading.
- For submission, download the Springer Nature LaTeX template from the journal's
  submission guidelines and copy `sn-jnl.cls` and `sn-basic.bst` here; `main.tex`
  then switches to the journal class automatically.
- `\todo{...}` marks what the author must fill in or confirm (affiliation, funding,
  AI-use statement, CRediT, DOI of the archived release).
- `figures/` holds PDF conversions of the documentation SVGs and the last frames of
  the GIFs; the PNG frames are low resolution and should be regenerated at 300 dpi
  from `docs/figures.py` before submission.
- Every entry in `references.bib` must be checked against the publisher's record.
