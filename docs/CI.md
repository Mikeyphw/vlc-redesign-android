# CI and upstream integration

## Source contract (local and hosted)

```sh
python3 -B -m unittest discover -s ci/tests -p 'test_*.py' -v
```

The tests cover clean merges, real overlapping conflicts, stale source/upstream SHAs, wrong upstream remote, foreign ancestry and unsafe Git revision parameters. They use disposable repositories and do not alter your working tree.

## Hosted PR qualification

`.github/workflows/vlc-pr.yml` runs source contracts and then a real Android debug test/build job on GitHub-hosted Ubuntu. Termux does **not** execute Gradle or provision Android SDKs.

The upstream checkout requires `org.videolan.android:medialibrary-all:0.13.24-rd1` built with a KuchiSofts patch and normally retrieved through a local Maven repository. Configure GitHub Actions repository variable `VLC_RD_MAVEN_BASE_URL` to a trusted **HTTPS Maven repo containing that exact patched artifact** before expecting Android CI to pass. Without it, the build fails with a clear error; it must not fall back to unpatched MediaLibrary. Audit artifact provenance and add checksum/dependency verification before release qualification. No credentials should be passed to untrusted PR jobs.

The repository has no Gradle wrapper checked in. Hosted CI provisions Gradle 9.4.0, Android 36 build-tools and Android NDK 21, subject to independent runtime compatibility checks on the actual runner. Do not interpret workflow registration or a downloaded dependency as a passed build.

## Daily upstream simulation

`.github/workflows/vlc-upstream.yml` runs daily and supports manual dispatch. It fetches direct upstream main, checks ancestry and generates `ci/_reports/upstream-merge.json`. A conflicting merge results in a failing job and a retained diagnostic artifact; the checkout is not merged and no PR or GitHub ref is changed. A green simulation means only that Git's tree merge is clean; it does not imply application compatibility.

## Required-check registration

GitHub Actions workflows receive numeric IDs only **after registration in the new fork**. Do not invent those IDs. Configure `config/delivery-required-ci.json` in a separately reviewed source-bound follow-up once exact IDs and workflow names are observed, including the true pull-request events and head SHAs, then enable branch protection. The first M0/M1 native session may report `REQUIRED_CI_SKIPPED_NO_POLICY`, which means hosted CI is **not** formally qualified by Devtool. Independently inspect the real PR HEAD and hosted job results before advancing to the next milestone.

## Release and secrets

The PR workflow uses `permissions: contents: read`, never signs release APKs, and never runs privileged `pull_request_target`. Release signing, protected environments and device verification belong to M7. Debug build artifacts are short-lived and are not a production release.
