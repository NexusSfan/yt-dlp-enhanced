# QSOL integration candidate

Baseline: `29490a6c9b53e1b9d2c2471c48303afbc44c4796`. Experimental branch only; no release or upstream submission authorised.

## OPT execution convention

```sh
uv run python -m devscripts.run_tests --opt --workers 7 core
```

The existing serial command and compatibility CI remain authoritative. OPT is an opt-in experimental core-only path, with 1–32 workers, deterministic module grouping and isolated tracked checkout copies. It refuses a dirty checkout, unsupported tracked symlinks, empty/duplicate collections, arbitrary pytest arguments and failed/incomplete shard receipts. It retains the core marker and flaky-selection policy. It does not introduce runtime dependencies or retries. It requires Git and the existing pytest test dependencies in the selected interpreter. It does not benchmark serial/parallel outcome parity automatically; compare separate runs before promotion. The snapshots omit ignored/untracked generated files and Git metadata; tests depending on those may fail and must be investigated, not silently skipped. This is not a verified speedup.

OPT provenance: QSOLKCB/OPT v1.4.0, OPT-PY-001, OPT-PAR-001, OPT-CRIT-001, OPT-BUDGET-001. Conceptual adaptations, not a dependency or theorem transfer.

## Remaining acceptance work

- Run serial and OPT in matching environments, compare exact selection, outcomes and skip reasons; measure wall time including copying and collection, memory and runner time.
- Validate on Ubuntu and Windows; retain all existing compatibility and security checks.
- Test upstream sync in temporary repositories, including failed fetch, apply, commit and ref update. A failed commit can leave staged changes; inspect before retrying. A failed tag compare-and-swap leaves the integration commit for review; no automatic rollback.
- Validate CLI opt-in and explicit opt-out using synthetic configuration fixtures only.
- Review update origin/checksum policy, file handling, subprocess trust, dependencies and credential confidentiality. Do not extend service restriction circumvention.
- Build portable Linux artifact from the existing Makefile, record SHA-256 and source identity; test on physical hardware. No release publication yet.
- Independently review exact PR head, then obtain owner acceptance before external submission.
