# QSOL integration candidate

Baseline: `29490a6c9b53e1b9d2c2471c48303afbc44c4796`. Experimental branch only; no release or upstream submission authorised.

## OPT execution convention

```sh
uv run python -m devscripts.run_tests --opt --workers 7 core
```

The existing serial command and compatibility CI remain authoritative. OPT is an opt-in experimental core-only path, with 1–32 workers, deterministic module grouping and isolated private copies of one raw committed Git object generation. It refuses a dirty checkout, unsupported tracked symlinks, empty/duplicate collections, arbitrary pytest arguments and failed/incomplete shard receipts. It retains the core marker and flaky-selection policy. It does not introduce runtime dependencies or retries. It requires Git and the existing pytest test dependencies in the selected interpreter. One global collection defines selected IDs; each worker collects only its assigned modules under the same marker and keyword filters. Workers reject missing/extra IDs before execution. Private copies are removed after their subprocess completes. The ordinary OPT invocation records source and coverage checks. Use the explicit verification mode below to compare observed per-test outcomes before promotion. The snapshots use raw Git blobs, verified against Git object IDs and a SHA-256 byte/mode manifest; checkout filters and export-ignore do not apply. The trusted launcher, interpreter and plugins are outside this source-byte receipt's scope. It is not protection against malicious test code or a compromised Git/interpreter. Snapshots omit ignored/untracked generated files and Git metadata; tests depending on those may fail and must be investigated, not silently skipped. This is not a verified speedup.

OPT provenance: QSOLKCB/OPT v1.5.0 (`2e521bba0f10f84046a59dfd5c3daee31b37d697`), OPT-PY-001, OPT-PAR-001, OPT-CRIT-001, OPT-BUDGET-001, OPT-HYBRID-001. Conceptual adaptations, not a dependency or theorem transfer.

## Outcome qualification (C-03)

```sh
uv run --locked --no-default-groups --group test --extra pin-curl-cffi python -m devscripts.run_tests --opt --verify --workers 7 core
```

The full serial run and workers use private copies of the same source generation and the same interpreter, selection options and installed environment. The serial run supplies the selected IDs, avoiding another complete coordinator collection. The verifier compares parent lifecycle outcomes, skip reasons, expected-failure annotations and ordered subtest labels/outcomes by node ID; count equality is not sufficient. A mismatch fails without fallback. The receipt distinguishes the serial oracle/collection interval, the parallel phase and total elapsed time including materialisation and cleanup. These are staged-run measurements, not a benchmark against ordinary serial execution. The full verification cost is paid by this invocation. Test outcome parity is an observation, not proof of identical side effects or dependencies' immutable bytes. Logs remain diagnostic and are not transactionally staged. Do not use these receipts for automatic promotion.

## Audit follow-up

YTDLP-AUDIT-001 (candidate `42e72529d839d2e862373386c611896fef602d3d`): C-01 and C-02 have candidate fixes; P-01/P-02 remove broad worker collection and unnecessary retention of completed workspaces. These are implementation changes, not validated speedups. The source manifest is checked before execution; it is not a sandbox for malicious tests. Seven workers remains explicit and experimental. No automatic path promotion is enabled.

## YTDLP-JS-001: local-only runtime smoke

```sh
uv run --no-project --with 'yt-dlp-ejs==0.8.0' python -m devscripts.js_runtime_smoke --bun "$HOME/.bun/bin/bun"
```

This optional developer diagnostic accepts an explicit trusted executable, runs a fixed synthetic JavaScript fixture in a temporary working directory with reduced inherited environment, disables package installation, checks exact JSON output, and records runtime version, executable/fixture digests, EJS distribution version and raw process-startup-plus-execution samples. It does not retrieve remote scripts, access browser profiles, contact a media service, test EJS challenge solving or establish a security sandbox. No runtime is installed or selected automatically. The existing Bun support ceiling and deprecation warning are unchanged. The end-point executable rehash is diagnostic, not protection against intervening modification. Actual Bun compatibility and isolation remain separate audit/acceptance work.

## Remaining acceptance work

- Validate the new C-03 outcome gate across the full workload; measure ordinary serial and qualified OPT under symmetric lifecycle boundaries, including memory and runner time.
- Validate on Ubuntu and Windows; retain all existing compatibility and security checks.
- Test upstream sync in temporary repositories, including failed fetch, apply, commit and ref update. A failed temporary commit or ref transaction leaves the real checkout untouched. After a successful ref transaction, checkout refresh can still fail or be interrupted; inspect the reported commits and status before recovery.
- Validate CLI opt-in and explicit opt-out using synthetic configuration fixtures only.
- Review update origin/checksum policy, file handling, subprocess trust, dependencies and credential confidentiality. Do not extend service restriction circumvention.
- Build portable Linux artifact from the existing Makefile, record SHA-256 and source identity; test on physical hardware. No release publication yet.
- Independently review exact PR head, then obtain owner acceptance before external submission.

## Hardened foundations — staged remediation

Receipts use schema 1 with strict JSON member handling, lifecycle validation and observed structured subtest contexts. The pytest safe representation of arbitrary values can still truncate or collide; this is not semantic application-value identity. Self-update now requires a valid matching SHA-256 before changing installed files; all variants use an exclusively created stage; POSIX and ZIP updates replace atomically, while Windows executable updates retain a backup-and-restore path. Checksums supplied by the release origin do not establish independent authenticity. Sync requires master descended from upstream-base, commits in a detached temporary worktree, rechecks branch, HEAD, baseline and cleanliness, and advances the branch and baseline in one checked ref transaction. Checkout refresh follows the transaction and is not atomic with it; exclusive operator access is required. The workflow check uses the pinned upstream zizmor CLI with a release asset SHA-256 rather than a policy-disallowed action; the policy owner must confirm this execution mechanism is acceptable. No security gate is disabled; the nine ignored and two persona-suppressed zizmor observations are inherited, unchanged exceptions. Cookie reload never accepts a missing or malformed file as a successful replacement; ambiguous empty or known partial browser results are refused before sources are merged. No change to service-restriction handling is introduced.

### Evidence and execution lifecycle

OPT receipts bind observed Python version, platform, installed distribution name/version inventory and loaded plugin distribution names and versions. This is an environment comparison, not a dependency-byte or host-resource attestation. Failed or interrupted attempts print a separate non-success receipt with elapsed times for completed, failed and interrupted invocations, including coordinator cancellation; abrupt host termination and output failure remain outside this guarantee. Timings overlap; do not add worker intervals to wall time. POSIX developer subprocess timeouts kill the process group and reap the direct child; escaped sessions, successful lingering descendants, concurrently running siblings, hard resource quotas and Windows descendant termination are not guaranteed. Use only trusted tests and runtime executables under an external supervisor where stronger containment is necessary. No browser data or credentials are needed for the developer diagnostics. The Bun executable endpoint hashes are streamed and do not establish protection against replacement races.

The optional module_costs argument to partition is a bounded, deterministic scheduling experiment for supplied positive integer module weights. The CLI still uses test counts, ordinary serial remains authoritative, no automatic promotion or historical timing cache is enabled. Synthetic balance tests demonstrate scheduling arithmetic only; real duration-aware experiments require source/environment/workload-qualified samples and complete lifecycle accounting.

Receipt and assignment files are capped at 32 MiB; excessive decoder nesting is rejected. This is a parser input limit, not a host resource quota or adversarial sandbox.

The update staging change removes the predictable `.new` write path. Concurrent updater exclusion, Windows reparse/ACL behavior, power-loss durability, independent release authentication, and hostile same-directory writers remain outside verified scope. The browser extraction completeness flag covers known Chromium decryption and Safari decoding failures, not independent verification that a browser supplied every cookie.
