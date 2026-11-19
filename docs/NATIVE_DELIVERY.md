# Native Devtool delivery for VLC Android

All future code overlays must be immutable, source-bound and use the latest
compatible canonical Devtool Launcher 3.2+ from `Mikeyphw/devtool` main. The
launcher delegates scaffold, artifact validation, executable hook/testing,
atomic apply/commit, durable delivery, push, PR and required-CI observation
to **Devtool itself**. It does not implement a competing overlay mechanism.

This follow-up targets the existing feature branch and PR #1, not `main`.
Source origin/branch/HEAD/tree, modified-file Git blobs, every proposed
payload hash and runtime identity are verified before native Devtool mutation.
Do not reset/rebase, force-push, overwrite unrelated changes or reapply after
a successful native commit. Use the new committed native delivery session for
subsequent `status`, `deliver`, `ci` and `report` actions.

Native operation sets the supported non-Textual/clipboard controls:

```sh
DEVTOOL_EXECUTION_PRESENTATION=plain
DEVTOOL_JOB_UI=plain
DEVTOOL_TEXTUAL_APPLY_HOST=0
DEVTOOL_TEXTUAL_EXECUTION_HOST=0
```

The target Termux checkout only runs lightweight Python and source validation.
**All Gradle/Android/NDK/LibVLC compilation happens in GitHub Actions.**
A passing local hook is not hosted native build evidence, a compiled debug
APK is not a signed release, and unsigned Android artifacts are not device
qualification. Required-CI watching must check the exact new PR SHA and the
committed `config/delivery-required-ci.json`, never upgrade an old receipt.

See `docs/CI.md` for verified artifact cache, KuchiSofts MediaLibrary source
pins, Maven packaging, negative gates, and explicit release limitations.
