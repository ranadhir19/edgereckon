"""edgereckon: the code-graph auditor.

AI coding agents navigate codebases by knowledge graphs whose call
edges are asserted from parsing and never checked. edgereckon audits
such a graph before an agent trusts it: it checks the graph's call
edges against independent ground truth -- execution traces harvested
from the target repo's own test suite -- and stamps every edge
VERIFIED, REFUTED, or, honestly, UNVERIFIABLE when the evidence runs
out. Impact questions are answered only over the verified subgraph;
the rest comes back as a refusal with machine-readable reason codes.
"""

__version__ = "0.1.0"
