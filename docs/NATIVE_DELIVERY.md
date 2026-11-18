# M0 + M1 native Devtool handoff

This milestone is delivered with the **canonical** `python3 -B -m devtool.launcher_contract_v3 build` native immutable builder, not copied into the target. The original bootstrap created and verified the real GitHub fork. Follow-up delivery reuses the existing clean named feature branch at its exact committed HEAD, and stages a separate immutable payload; it must not recreate the branch or replay the prior overlay. The launcher then validates the exact origin/branch/HEAD/tree/preimages/payload, runs the source contract unit tests through native Devtool, applies atomically, records a durable session and (only when explicitly approved) pushes and creates a PR. No automatic merge or release.

The bootstrap refuses nonfork repositories, untrusted remotes, dirty/occupied worktrees, mismatched upstream HEAD/tree, unavailable or incompatible Devtool runtime, extra/missing payload files, and preexisting added paths. Native Devtool owns preflight, overlay validation, apply, rollback, commit, session, push, PR and CI observation.

No Gradle is run in Termux. Android builds remain hosted and fail closed until the patched MediaLibrary Maven source is configured. The follow-up adds committed `config/delivery-required-ci.json` using the observed numeric workflow ID. This enables **new** native sessions to qualify CI after hosted checks pass, but does not retroactively qualify the historical session.

If a native session committed but PR/CI observation failed, **never reapply the package**. Use `python3 -B PACKAGE.pyz status --session-id ID` / `deliver --session-id ID` / `ci --session-id ID` after reading the native session receipt. Keep full stdout/stderr diagnostics; use no automatic clipboard copying.

For the M0+M1 CI correction, continue on existing PR #1 (do not create a competing PR). Devtool must prove its source-bound new branch HEAD, fast-forward push, existing PR reuse, required-CI registration, and actual hosted results. The new native commit changes workflow security checking, hosted Gradle pairing, CI policy, current regression tests, and these docs only.
