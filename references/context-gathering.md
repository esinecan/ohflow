# Context gathering: evidence atlas

Use this branch when the deliverable is a high-fidelity map of an unfamiliar
repository, system, incident, or architecture rather than a code change. The
reusable shape is **scout → synthesize → challenge → cartograph**. Start from
[`scripts/ohflow/workflows/evidence_atlas_template.py`](../scripts/ohflow/workflows/evidence_atlas_template.py).

## 1. Price the evidence

Name the primary evidence roots, contextual-only material, and claims the run
must never silently import. Define provenance classes before choosing agent
domains. When ownership changed over time, require git history rather than
present-tree inspection.

Done when every future claim fits one provenance class and excluded evidence is
named in the briefs.

## 2. Split by evidence seam

Give each scout one end-to-end seam, not a keyword bucket. Useful seams include
runtime topology, lifecycle/orchestration, data movement, security boundaries,
observability, domain flows, and change provenance. Each scout traces at least
one representative flow; a directory inventory is incomplete.

Every scout emits the same atomic units:

- components with responsibilities and edges;
- ordered flows with triggers, terminal states, and failures;
- falsifiable claims with path/line/symbol evidence, provenance, confidence,
  limits, and related claim IDs;
- unknowns naming bounded searches already performed;
- contradictions kept side by side.

Done when overlap exists only at deliberate cross-layer edges and every scout
has an explicit trace obligation.

## 3. Use two independent syntheses

One synthesizer builds the canonical component and flow model. A second is the
**provenance firewall**: it samples citations, checks ownership, rejects context
contamination, and downgrades unsupported certainty. Both consume every scout
final message and retain source claim IDs.

Done when integration and admissibility are separate findings files produced without
seeing each other's conclusions.

## 4. Challenge the joins

Run three reviewers in parallel:

1. **provenance** — source class, ownership, citation strength, inference;
2. **consistency** — cross-layer lifecycle and identity/data context;
3. **coverage** — omitted runtimes, negative evidence, failure paths, and facts
   the available checkout cannot establish.

Findings name claim IDs and give a replacement, deletion, or confidence
downgrade. The final cartographer applies every blocking finding or rebuts it
with stronger evidence.

Done when a validator can falsify claims without reconstructing scout scope.

## 5. Deliver map and ledger

The atlas explains the architecture; the claim ledger makes it auditable and
updateable. Add diagrams only after claims stabilize, and map every edge to
claim IDs. Keep gaps and contradictions as a first-class deliverable.

Recommended outputs: `ARCHITECTURE-ATLAS.md`, `CLAIM-LEDGER.json`,
`DIAGRAMS.md`, `GAPS-AND-CONTRADICTIONS.md`, and `EXECUTIVE-SUMMARY.md`.

Done when the ledger parses, every material statement maps to a claim, and
every diagram edge maps to evidence.

## Operating defaults

- Run the scouts on `pi`. The evidence atlas template runs on `pi` at the
  `light` tier.
- The default tool set is the uninhibited tool policy. Attach MCP servers
  only when the evidence requires them.
- Give parallel scouts separate worktrees. An accidental write then fails one
  agent's `tree_clean` gate without contaminating peers.
- A shared findings directory uses the named-file exception in every brief; create
  it before launch.
- Keep the Z.AI reserve ([ohflow](ohflow.md#concurrency)). After a burst-rate
  failure, lower the semaphore without deleting assignments.
- Dry-run, inspect one scout brief and the final spec, then revert before launch.

Done when clean-tree and schema gates cover every agent and final artifact
existence plus ledger parsing are mechanical gates.
