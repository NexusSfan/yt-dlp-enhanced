# Developer testing

Run the existing core tests with the test dependencies installed (or use the existing Hatch test environment):

```sh
uv run python -m devscripts.run_tests core
```

For an optional parallel run from a clean, committed checkout:

```sh
uv run python -m devscripts.run_tests --parallel --workers 7 core
```

Add `--verify` to run the same selection serially first and compare individual test outcomes, including skips and subtests. Verification runs both strategies; its total time is not a speedup. The previous spelling `--opt` remains an alias. The serial command remains the default. The commands also work with `python` in a prepared environment. Parallel mode requires Git and the existing pytest dependencies, supports 1–32 workers and `-k`, and rejects arbitrary pytest arguments and retries.

Tests are grouped by module and run in separate copies of committed files. Checkout filters, ignored files and Git metadata are not included. Source bytes and modes, selected test identities, report structure and observed Python/package/plugin identities are checked. JSON input is limited to 32 MiB. Failed or interrupted runs report completed attempt timings and exit unsuccessfully. Timings overlap; do not sum them as wall time.

Use trusted tests and a trusted Python environment. These copies are not a sandbox. Package identities do not authenticate dependency bytes, and subtest value representations may collide. POSIX timeouts kill the process group; escaped or lingering descendants and Windows process trees are not contained. External supervision is needed for stronger guarantees.

## Upstream synchronisation

Use ordinary Git merges when the remote shares history and the intended upstream commit should remain an ancestor. The patch-based `devscripts/merge_upstream.sh` is for an explicitly maintained `upstream-base` tag; do not mix the two workflows or move the tag without review. Run it only from a clean `master` with exclusive access. It stages changes in a temporary worktree and updates both refs in one transaction; checkout refresh follows and can fail separately. Inspect the reported commits and status before recovery.

## Update and cookie handling

An executable update requires a matching SHA-256 checksum; a release-provided checksum alone does not authenticate its publisher. Concurrent updates and hostile writers in the installation directory are not supported. Cookie reload refuses missing, malformed or known incomplete sources, but cannot establish that a browser supplied every cookie.

## Provenance

The parallel test runner was developed using ideas from [OPT v1.5.0](https://github.com/QSOLKCB/OPT/tree/2e521bba0f10f84046a59dfd5c3daee31b37d697). Earlier experimental diagnostics, audit context and benchmark notes are preserved in [the pre-cleanup revision](https://github.com/QSOLKCB/yt-dlp-enhanced/tree/4f9435dc916fd86b377a44aa76809bc4f8f06026). They are not required to run or maintain the downloader.
