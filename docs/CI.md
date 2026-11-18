# CI and upstream integration

## Source contract (local and hosted)

```sh
python3 -B -m unittest discover -s ci/tests -p 'test_*.py' -v
```

The tests cover clean merges, real overlapping conflicts, stale source/upstream SHAs, wrong upstream remote, foreign ancestry and unsafe Git revision parameters. They use disposable repositories and do not alter your working tree.

## Hosted PR qualification

`.github/workflows/vlc-pr.yml` runs source contracts and then a real Android debug test/build job on GitHub-hosted Ubuntu. Termux does **not** execute Gradle or provision Android SDKs.

The upstream checkout requires `org.videolan.android:medialibrary-all:0.13.24-rd1` built with a KuchiSofts patch and normally retrieved through a local Maven repository. Configure GitHub Actions repository variable `VLC_RD_MAVEN_BASE_URL` to a trusted **HTTPS Maven repo containing that exact patched artifact** before expecting Android CI to pass. Without it, the build fails with a clear error; it must not fall back to unpatched MediaLibrary. Audit artifact provenance and add checksum/dependency verification before release qualification. No credentials should be passed to untrusted PR jobs.

The repository has no Gradle wrapper checked in. Hosted CI now provisions **Gradle 9.6.0**, required by upstream **Android Gradle Plugin 9.4.1** (Android Developers' AGP 9.4 compatibility table), along with Android 36 build-tools and Android NDK 21. Build success remains a hosted-run requirement: local source validation does not qualify Android artifacts. Do not interpret workflow registration or a downloaded dependency as a passed build.

## Daily upstream simulation

`.github/workflows/vlc-upstream.yml` runs daily and supports manual dispatch. It fetches direct upstream main, checks ancestry and generates `ci/_reports/upstream-merge.json`. A conflicting merge results in a failing job and a retained diagnostic artifact; the checkout is not merged and no PR or GitHub ref is changed. A green simulation means only that Git's tree merge is clean; it does not imply application compatibility.

## Required-check registration

The GitHub workflow identity was independently observed in the fork from PR #1's original failed run **44371205406**:

- Workflow: `VLC Android PR qualification`
- Numeric GitHub workflow ID: `422964106`
- Required event: `pull_request` (PR source HEAD and actual workflow run must match)
- Base: `main`

`config/delivery-required-ci.json` now declares that exact name/ID pair with `release_qualification: separate`. The committed policy is read by native Devtool after the source-bound commit, and is not rewritten at runtime. The existing M0+M1 durable session `52eeb8afcdd540fbb8d2b2b6819a00b3` was created **before** this policy existed: its historical `REQUIRED_CI_SKIPPED_NO_POLICY` receipt is accurate and must never be upgraded in place. A new native source-bound delivery session for this follow-up commit may watch required CI.

The workflow's **Native source contracts** job now calls `python3 -B ci/workflow_policy.py` rather than grepping its own YAML for a forbidden trigger. `ci/tests/test_workflow_policy.py` exercises the real checked-in workflows and negative event/permission/policy/version examples. Both source and Android jobs remain required **inside** the one required workflow: a failed, cancelled or skipped Android job is **not** a successful build or qualified CI run.

The original PR's failing run is evidence of a false-positive workflow guard, not passing CI. Once this update is committed, verify the new PR HEAD, the resulting distinct workflow run ID, exact attempted job statuses and Devtool's persisted CI receipt. GitHub required checks/branch protection must be configured and verified separately; a valid policy file alone does not establish hosted acceptance.

## Known hosted build dependency

KuchiSofts uses patched MediaLibrary `org.videolan.android:medialibrary-all:0.13.24-rd1`, which is **not** supplied by the stock Maven artifact. Unless the repository variable `VLC_RD_MAVEN_BASE_URL` points to a verified HTTPS Maven repository serving the exact patched version, the Android job intentionally fails. No substitution, omitted job, optional failure, static qualification or Termux Gradle execution is permitted. Release signing and on-device checks remain distinct.

## Release and secrets

The PR workflow uses `permissions: contents: read`, never signs release APKs, and never runs privileged `pull_request_target`. Release signing, protected environments and device verification belong to M7. Debug build artifacts are short-lived and are not a production release.
