"""Copy-and-specialize template for a repository evidence atlas.

Required args: repo=<git repo> root=<output root>
Optional args: base=main subject=<label> evidence_root=<path> max_parallel=5

Replace DOMAINS and strengthen the briefs for the subject. The reusable value is
the phase topology and gates, not these placeholder domain names.
"""

from pathlib import Path

from ohflow.workflow import (
    CheckSpec, GateSpec, ModelConfig, Phase, Workflow, Step,
    AgentSpec, WorktreeSpec, HandoverSpec, house_checks,
)

MODEL = ModelConfig("light",
                    "https://api.z.ai/api/coding/paas/v4",
                    "ZAI_CODING_CN_API_KEY", params={"thinking": "high"})

DOMAINS = {
    "topology": "runtime topology, boundaries, boot paths, and configuration",
    "lifecycle": "primary lifecycle from external trigger to terminal result",
    "data": "data ownership, stores, movement, and consistency boundaries",
    "security": "identity, authorization, tenancy, and containment boundaries",
    "quality": "observability, evaluation, tests, and failure handling",
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "components": {"type": "array", "items": {"type": "object"}},
        "flows": {"type": "array", "items": {"type": "object"}},
        "claims": {"type": "array", "items": {"type": "object"}},
        "unknowns": {"type": "array", "items": {"type": "object"}},
        "contradictions": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["domain", "components", "flows", "claims", "unknowns",
                 "contradictions"],
}

VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "dimension": {"type": "string"},
        "verdict": {"type": "string",
                    "enum": ["PASS", "PASS_WITH_ISSUES", "FAIL"]},
        "findings": {"type": "array", "items": {"type": "object"}},
        "required_corrections": {"type": "array",
                                 "items": {"type": "object"}},
    },
    "required": ["dimension", "verdict", "findings", "required_corrections"],
}


def _gate():
    return GateSpec((CheckSpec("tree_clean", {}),
                     CheckSpec("schema_valid", {}),
                     *house_checks()))


def _agent(role, brief, iterations=220):
    return AgentSpec(role=role, brief=brief, model=MODEL,
                     max_iterations=iterations, harness_executor="pi")


def _json_tail(keys):
    return ("Write the identical UTF-8 JSON object to the named output file and "
            "as the final fenced JSON block. Exact top-level keys: " + keys)


def build(args: dict) -> Workflow:
    if not args.get("repo") or not args.get("root"):
        raise ValueError("evidence_atlas_template requires repo= and root=")
    repo, root = Path(args["repo"]), Path(args["root"])
    base, subject = args.get("base", "main"), args.get("subject", repo.name)
    evidence = Path(args.get("evidence_root", str(repo)))
    reports, deliverables = root / "reports", root / "deliverables"
    parallel = min(int(args.get("max_parallel", 5)), 5)
    dimensions = ("provenance", "consistency", "coverage")
    names = (list(DOMAINS) + ["synth-model", "synth-provenance"] +
             [f"check-{x}" for x in dimensions] + ["cartographer"])
    worktrees = tuple(
        WorktreeSpec(n, root / "worktrees" / n,
                     f"research/evidence-atlas-{n}", base, "none")
        for n in names)

    scouts = tuple(
        Step(id=f"scout-{name}", kind="agent", worktree=name,
             handover=HandoverSpec(audience="consolidator"),
             execution_timeout_s=7200, schema=REPORT_SCHEMA, gate=_gate(), note=scope,
             agent=_agent("evidence scout", f"""Map {scope} for {subject}.
Primary evidence: {evidence}
Named output exception: write only {reports / f'scout-{name}.json'} outside the worktree.
Trace representative behaviour; an inventory is incomplete. Every atomic claim needs path, line, symbol, provenance, confidence, proof, and limits. Record bounded negative searches under unknowns. Keep contradictions side by side. Do not edit the repository.
{_json_tail('domain, components, flows, claims, unknowns, contradictions')}"""))
        for name, scope in DOMAINS.items())
    scout_ids = tuple(x.id for x in scouts)

    synth = tuple(
        Step(id=f"synth-{kind}", kind="agent", worktree=f"synth-{kind}",
             depends_on=scout_ids, consumes=scout_ids, execution_timeout_s=7200, schema=REPORT_SCHEMA,
             gate=_gate(), note=f"{kind} synthesis",
             agent=_agent("evidence synthesizer", f"""Read every scout JSON in {reports}.
{('Build the canonical component, flow, and claim model.' if kind == 'model' else 'Be the provenance firewall: verify citations, ownership, contamination, and inference.')}
Named output exception: write only {reports / f'synthesis-{kind}.json'} outside the worktree. Preserve source claim IDs and contradictions. Do not edit the repository.
{_json_tail('domain, components, flows, claims, unknowns, contradictions')}""", 280))
        for kind in ("model", "provenance"))
    synth_ids = tuple(x.id for x in synth)

    checks = tuple(
        Step(id=f"check-{d}", kind="agent", worktree=f"check-{d}",
             depends_on=synth_ids, consumes=synth_ids, execution_timeout_s=5400,
             schema=VALIDATION_SCHEMA, gate=_gate(), note=f"{d} audit",
             agent=_agent("adversarial validator", f"""Read every report in {reports}; audit {d} and verify material claims directly in {evidence}. Name claim IDs and give a replacement, deletion, or confidence downgrade for every issue.
Named output exception: write only {reports / f'validation-{d}.json'} outside the worktree. Do not edit the repository.
{_json_tail('dimension, verdict, findings, required_corrections')}""", 200))
        for d in dimensions)

    required = ("ARCHITECTURE-ATLAS.md", "CLAIM-LEDGER.json", "DIAGRAMS.md",
                "GAPS-AND-CONTRADICTIONS.md", "EXECUTIVE-SUMMARY.md")
    final_gate = GateSpec((*_gate().checks,
        *(CheckSpec("command_exit", {"cmd": f'test -s "{deliverables / n}"'})
          for n in required),
        CheckSpec("command_exit", {"cmd":
            f'python -m json.tool "{deliverables / "CLAIM-LEDGER.json"}" >/dev/null'})))
    final = Step(
        id="cartographer", kind="agent", worktree="cartographer",
        depends_on=tuple(x.id for x in checks), consumes=tuple(x.id for x in checks), execution_timeout_s=10800,
        schema=REPORT_SCHEMA, gate=final_gate, note="final evidence-linked atlas",
        agent=_agent("final cartographer", f"""Read every report in {reports}. Apply each blocking correction or rebut it with stronger evidence. Create {', '.join(required)} under {deliverables}. Map every material statement and diagram edge to claim IDs. Parse-check the ledger. Do not edit the repository.
{_json_tail('domain, components, flows, claims, unknowns, contradictions')}""", 400))

    return Workflow(
        name=f"evidence-atlas-{subject}", repo=repo, base_branch=base,
        max_parallel=parallel, args=dict(args), worktrees=worktrees,
        phases=(
            Phase("Recon: evidence scouts", scouts, "abort", "all", parallel),
            Phase("Synthesize: independent models", synth, "abort", "all",
                  min(2, parallel)),
            Phase("Validate: adversarial audits", checks, "abort", "all",
                  min(3, parallel)),
            Phase("Deliver: final atlas", (final,), "abort", "all", 1),
        ))
