# HyLogger Explorer: live site

This branch holds the GitHub Pages site at
<https://nhuannguyen87.github.io/hackathon_hylogger/>. It is the HyLogger
Explorer app itself (Explore, 3D, Minerals, How to read), exported as static
files. The app's code is on the
[`main`](https://github.com/nhuannguyen87/hackathon_hylogger/tree/main) branch.

There is no server and no data in this branch. Each visitor's browser reads
GSWA's public services directly:

- the hole list from GSWA's borehole web feature service (`gsmlp:BoreholeView`,
  NVCL holes only);
- the mineral logs, tray photos and scan records from NVCL's data services,
  public logs only.

Mineral calls, the specific mineral each group holds, and the core photo cut
from tray photos are all worked out in the browser.

What this site leaves out: GSWA's DASC download is not a live service, so the
lab assays, the rock the company logged, the unusual-reading flags and what each
hole was drilled for are not here. About 4 in 10 NVCL holes keep their mineral
logs private; those show on the map as grey dots.

The files here are `next build` output (`output: "export"`, `basePath:
"/hackathon_hylogger"`). `.nojekyll` keeps GitHub Pages from hiding `_next/`.
To update the site, rebuild and replace everything here except `.git`,
`.nojekyll` and this README, then push.
