# IP / legal compliance record — edgereckon

- **Original name:** "edgereckon" was coined for this project.
  Collision-checked against GitHub, PyPI, and npm on 2026-11-21 and
  re-verified the same day at build time (GitHub repository search:
  0 results; PyPI: 404; npm: 404). Full record in
  [NAME_CHECK.md](NAME_CHECK.md).
- **Original code and copy:** all code and documentation in this
  repository were written for this project. The motivating idea —
  that the call graphs AI coding agents navigate by should be
  verified against ground truth before they are trusted — came from
  a landscape analysis of code-intelligence tools; no third-party
  code, text, graph format implementation, or documentation was
  copied from any of them.
- **License-specific care (from the landscape scan's compliance
  flags):**
  - **GitNexus (PolyForm Noncommercial 1.0.0):** no GitNexus code
    used, no dependency on GitNexus; edgereckon does not ingest its
    export format in v1.
  - **jCodeMunch (custom non-commercial license):** no code used, no
    dependency.
  - **Serena (application GPL-3.0-or-later):** no Serena code
    embedded or adapted.
  - **Graphify (Apache-2.0):** v1 ingests the Graphify `graph.json`
    *format* (node-link JSON) — reading a data file format produced
    by a user's own run of a tool is data processing; no Graphify
    code is used or bundled.
- **License:** this project is released under the MIT License
  ([LICENSE](LICENSE)).
- **Third-party dependencies:** none. The implementation uses only
  the Python standard library, so there are no third-party licenses
  to comply with and nothing bundled to attribute.
- **Asset provenance:** no images, fonts, data files, or other
  assets are bundled. The fixtures under `fixtures/` were written by
  hand for this project, including the Graphify-format fixture graph,
  whose planted errors are labelled as such.
- **Secrets scan:** the tree contains no credentials or key material
  of any kind.
