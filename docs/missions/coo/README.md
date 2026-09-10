# COO missions

This folder is the contract between `techpulse` and agent-os. A
Chief Operating Officer agent (the "COO") proposes features here, a human
approves or rejects them from the agent-os dashboard, and either agent-os
or the COO routine builds what was approved and reports back. Nothing in
this folder is application code.

## Layout

- `docs/missions/coo/proposals/NNN-<slug>.md` -- one proposal per file, numbered in
  order of creation. The YAML frontmatter carries `title`, `status`,
  `attempts` and `branch`; the body explains what you get, why now, the
  problem, the proposed solution, effort, a validation contract and risks.
- `docs/missions/coo/reports/<slug>.md` -- written when a proposal ships: branch,
  pull request, validation and review output.
- `docs/missions/coo/state.md` -- the COO's running log and shipped count.

## Proposal status

| status | meaning |
| --- | --- |
| `proposed` | waiting for a human decision in agent-os |
| `approved` | cleared to build; picked up by agent-os (with a build grant) or the COO routine |
| `rejected` | closed, kept for the record |
| `building` | agent-os is building it right now; the COO routine leaves it alone |
| `shipped` | merged or ready to merge; a report exists |

## How it flows

1. agent-os mirrors `docs/missions/coo/` into its raw layer on every sync and raises a
   decision for each `proposed` file.
2. Approving a decision rewrites the file to `approved` on the base branch.
3. The builder works on a `req/<slug>` (agent-os) or `coo/<slug>` (COO routine)
   branch, opens a pull request, waits for CI to pass, then marks the
   proposal `shipped` and writes the report.

Edit proposals by hand if you like; agent-os re-reads them on the next sync.
