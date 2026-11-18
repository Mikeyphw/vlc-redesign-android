# M0 + M1 native Devtool handoff

This milestone is delivered with the **canonical** `python3 -B -m devtool.launcher_contract_v3 build` native immutable builder, not copied into the target. The bootstrap creates (or verifies) a real GitHub fork, a clean named feature checkout and a separately staged immutable payload. The launcher then validates the exact origin/branch/HEAD/tree/preimages/payload, runs the source contract unit tests through native Devtool, applies atomically, records a durable session and (only when explicitly approved) pushes and creates a PR. No automatic merge or release.

The bootstrap refuses nonfork repositories, untrusted remotes, dirty/occupied worktrees, mismatched upstream HEAD/tree, unavailable or incompatible Devtool runtime, extra/missing payload files, and preexisting added paths. Native Devtool owns preflight, overlay validation, apply, rollback, commit, session, push, PR and CI observation.

No Gradle is run in Termux. The required hosted Android build is blocked until the patched MediaLibrary Maven source is configured. Native session CI is not formally qualified until committed `config/delivery-required-ci.json` has real workflow IDs.

If a native session committed but PR/CI observation failed, **never reapply the package**. Use `python3 -B PACKAGE.pyz status --session-id ID` / `deliver --session-id ID` / `ci --session-id ID` after reading the native session receipt. Keep full stdout/stderr diagnostics; use no automatic clipboard copying.
