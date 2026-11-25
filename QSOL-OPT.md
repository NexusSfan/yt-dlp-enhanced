# QSOL integration candidate

Baseline: `29490a6c9b53e1b9d2c2471c48303afbc44c4796`. Experimental branch only; no release or upstream submission authorised.

## OPT execution convention

```sh
uv run python -m devscripts.run_tests --opt --workers 7 core
```

The existing serial command and compatibility CI remain authoritative. OPT is an opt-in experimental core-only path, with 1–32 workers, deterministic module grouping and isolated private copies of one raw committed Git object generation. It refuses a dirty checkout, unsupported tracked symlinks, empty/duplicate collections, arbitrary pytest arguments and failed/incomplete shard receipts. It retains the core marker and flaky-selection policy. It does not introduce runtime dependencies or retries. It requires Git and the existing pytest test dependencies in the selected interpreter. One global collection defines selected IDs; each worker collects only its assigned modules under the same marker and keyword filters. Workers reject missing/extra IDs before execution. Private copies are removed after their subprocess completes. The receipt records source and coverage checks, not serial/parallel outcome parity; compare separate runs before promotion. The snapshots use raw Git blobs, verified against Git object IDs and a SHA-256 byte/mode manifest; checkout filters and export-ignore do not apply. The trusted launcher, interpreter and plugins are outside this source-byte receipt's scope. It is not protection against malicious test code or a compromised Git/interpreter. Snapshots omit ignored/untracked generated files and Git metadata; tests depending on those may fail and must be investigated, not silently skipped. This is not a verified speedup.

OPT provenance: QSOLKCB/OPT v1.4.0, OPT-PY-001, OPT-PAR-001, OPT-CRIT-001, OPT-BUDGET-001. Conceptual adaptations, not a dependency or theorem transfer.

## Audit follow-up

YTDLP-AUDIT-001 (candidate `42e72529d839d2e862373386c611896fef602d3d`): C-01 and C-02 have candidate fixes; P-01/P-02 remove broad worker collection and unnecessary retention of completed workspaces. These are implementation changes, not validated speedups. The source manifest is checked before execution; it is not a sandbox for malicious tests. Seven workers remains explicit and experimental. No automatic path promotion is enabled.

## Remaining acceptance work

- Run serial and OPT in matching environments, compare exact selection, outcomes and skip reasons; measure wall time including copying and collection, memory and runner time.
- Validate on Ubuntu and Windows; retain all existing compatibility and security checks.
- Test upstream sync in temporary repositories, including failed fetch, apply, commit and ref update. A failed commit can leave staged changes; inspect before retrying. A failed tag compare-and-swap leaves the integration commit for review; no automatic rollback.
- Validate CLI opt-in and explicit opt-out using synthetic configuration fixtures only.
- Review update origin/checksum policy, file handling, subprocess trust, dependencies and credential confidentiality. Do not extend service restriction circumvention.
- Build portable Linux artifact from the existing Makefile, record SHA-256 and source identity; test on physical hardware. No release publication yet.
- Independently review exact PR head, then obtain owner acceptance before external submission.
