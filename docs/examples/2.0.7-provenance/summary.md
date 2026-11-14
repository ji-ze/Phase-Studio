# Phase Studio run SYNTHETIC-NO-EXECUTION

Status: completed. Started: 2026-11-02T10:42:04.112+00:00. Finished: 2026-11-02T10:42:04.399+00:00.

Effective configuration and full hashes: `run_manifest.json`. Detailed chronology: `events.jsonl` and `diagnostic.log`.

## Run setup
Input: <LOCAL_PATH_0003>
Workflow: Superflip; configured cycles: 2; SharpED model: Synthetic example; no remote request.
Enabled optional operations: 
Evaluation reference: Unavailable
Explicit first-cycle model: Unavailable
Effective referencefile/modelfile roles are recorded from each generated input; an atom count alone is not evidence of a phasing seed.

## Execution summary
Completed cycles: 2; incomplete cycles: {}
Observed session duration (s): 0.2873395000351593; component totals (s, may overlap): {}

## Recorded scientific results

| Cycle | Cycle status | Family | F0.5 | RMSD (A) | Phase agreement | Reference TP / FP | Extracted CIF sites | Feedback feeding this cycle | Input |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | completed | Superflip | 0.5 | 0.2 | Unavailable | 2 / 1 | Unavailable | No preceding step; initial filtered input | <LOCAL_PATH_0003> |
| 1 | completed | SharpED | 0.5 | 0.2 | Unavailable | 2 / 1 | Unavailable | No preceding step; initial filtered input | <LOCAL_PATH_0003> |
| 2 | completed | Superflip | 0.5 | 0.2 | Unavailable | 2 / 1 | Unavailable | Disabled | <LOCAL_PATH_0003> |
| 2 | completed | SharpED | 0.5 | 0.2 | Unavailable | 2 / 1 | Unavailable | Disabled | <LOCAL_PATH_0003> |

## Input and execution
```json
null
```

## Recommendation and later actions
Recommendations remain governed by the existing validation-profile ranking. This logger does not rerank feedback changes.
No selection or handoff is implied by completing a run.
{
  "selections": [],
  "handoffs": []
}

## Reproducibility limits
- SYNTHETIC EXAMPLE: fabricated metric values; no scientific program or remote inference executed. Configuration is a minimal example, not a complete runnable project.
- Remote immutable checkpoint identity unavailable unless the server supplies it.
- No bitwise-reproducibility claim. Automatic random seeds may be uncontrolled.
- The manifest is an audit record, not a replacement for the execution checkpoint/recovery authority.

Hashes identify completed files at the recorded checkpoint. Mutable live logs/events are not immutable scientific inputs.

## Warnings and failures
No warnings or failures recorded.
