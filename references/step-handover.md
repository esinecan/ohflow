# Handovers between agent steps

`depends_on` says which work must pass first. `consumes` says which agent findings to read. The consumer receives the recorded handover text in its position block, with producer identity, revision and outcome supplied by the engine.

```python
from ohflow.workflow import HandoverSpec, Step
scout = Step(id="scout", kind="agent", agent=scout_agent,
             handover=HandoverSpec(audience="next"))
implement = Step(id="implement", kind="agent", agent=implement_agent,
                 depends_on=("scout",), consumes=("scout",))
```

Validation supplies `HandoverSpec()` when a consumed producer has no explicit spec. A producer can also declare a handover for later inspection without a consumer. Use `audience="reviewer"` for independent review and `audience="consolidator"` for joining contributions. Add task-specific question headings through `extra=("Which compatibility decisions matter?",)`.

## Questions

The contract asks what a reader needs to carry on the work without the producer. Answer every heading in order, use `not established` for unknowns, cite exact artifact paths and commands, and label findings `[verified]` or `[assumed]`. Preserve completed side effects with “already done, do not repeat”. Reference source content rather than copying it. Keep secrets out.

| Heading | Question |
|---|---|
| State | Which artifact or commit is authoritative, where is it, and which copies are stale? |
| Done and undone | What is finished and what remains incomplete? Mark completed side effects: already done, do not repeat. |
| Decisions | Which decisions and reasons must the reader preserve, and what evidence could reopen them? |
| Verified and assumed | What did you verify, by which command or source? What remains assumed? |
| Tried and failed | Which approaches failed, with what symptom, and which workaround worked? |
| Open | Which questions and contradictions remain unresolved? |
| Next | What should the reader do, verify first, and wait for? |

### reviewer

- **How to run it:** Which command runs it in isolation, what setup is required, and what goes wrong without it?
- **What passing does not prove:** What do the checks establish, and what remains untested?
- **Never relax:** Which invariant must remain true, and what breaks if it is relaxed?

### consolidator

- **Interfaces:** Which interfaces and assumptions connect this work to the other contributions?
- **Integration risks:** Which conflicts or mismatches could occur, and which check exposes them?

## Production and receipt

The position block gives the producer an absolute path to `handover.md` in its attempt directory. Write it before the final message, within the default 6000-character limit. The file remains outside the product worktree; pi's editor permits that exact file while retaining its normal write scope.

`handover_written` checks UTF-8 readability, heading order, one answer per heading and the size limit. It checks structure; the recipient verifies the answers. A missing or malformed required handover fails the producer's gate, so its consumers cannot start. An explicit `gate:handover_written` retry policy can retry that failure.

The engine records the file path and SHA-256 digest. Downstream agents read that attempt file; a missing or changed file prevents trusting cached producer output. Consumed digests enter the consumer fingerprint. Each fingerprint version bump, currently at 6, invalidates earlier cache identities once. Paths and attempt numbers remain outside identity.

A retry receives its previous attempt's handover, when present, alongside failed checks. Session continuation is an independent harness capability. A received handover supplies findings; sharing a worktree or merging branches supplies code.

The built-in relay, merge consolidation, implement/review and evidence-atlas workflows declare their handovers. Campaign judge packets include recorded step handovers and earlier judge handovers. A judge handover answers the same seven core headings under a title and a lead paragraph; its format is in the judge brief ([campaign](campaign.md)). Context passed between separate fix runs or milestone implementers is authored in their briefs and artifact references.

## Mechanical proof

Run `python3 tests/run_tests.py -k handover_01` from the root of your ohflow clone. The tests exercise actual engine preparation, gating, retries, cached resumes and deleted/modified evidence with fake agents.

From `scripts`, run `python3 -m ohflow.cli rollcall --cases relay:pi,claude --out <proof-directory>` with `PYTHONPATH=.`. The successor must reproduce a token supplied only through its predecessor's handover; the gate verifies it in `ROLLCALL.md`.
