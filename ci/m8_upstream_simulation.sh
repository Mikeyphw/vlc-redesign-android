#!/usr/bin/env bash
set -Eeuo pipefail
# Simulate the latest direct KuchiSofts upstream merge in an isolated temporary worktree.
# Does not merge/rebase/reset the user's branch, touch M7, or publish changes.

repo=$(git rev-parse --show-toplevel)
branch=$(git -C "$repo" branch --show-current)
if [[ "$branch" != feature/vlc-m8-ui-ux-refinement-20261120 ]]; then
  printf 'M8_UPSTREAM_REFUSED: expected named M8 worktree; found %s\n' "$branch" >&2
  exit 2
fi
if [[ -n "$(git -C "$repo" status --porcelain --untracked-files=all)" ]]; then
  git -C "$repo" status --short
  printf 'M8_UPSTREAM_REFUSED: target worktree not clean\n' >&2
  exit 2
fi
head=$(git -C "$repo" rev-parse HEAD)
command -v git
command -v python3
printf 'M8_UPSTREAM: feature HEAD %s\n' "$head"
printf '=== Fetch direct KuchiSofts upstream main (no branch mutation) ===\n'
git -C "$repo" fetch --no-tags --no-recurse-submodules \
  https://github.com/KuchiSofts/vlc-redesign-android.git refs/heads/main
upstream_sha=$(git -C "$repo" rev-parse FETCH_HEAD)
printf 'M8_UPSTREAM: candidate incoming commit %s\n' "$upstream_sha"

stage=$(mktemp -d "${TMPDIR:-/tmp}/vlc-m8-merge-sim.XXXXXXXX")
candidate="$stage/candidate"
cleanup() {
  local rc=$?
  trap - EXIT
  if [[ -d "$candidate" ]]; then
    printf '=== Remove only the temporary M8 simulation worktree ===\n'
    git -C "$repo" worktree remove --force "$candidate" || {
      printf 'M8_UPSTREAM_CLEANUP_WARNING: inspect %s\n' "$candidate" >&2
    }
  fi
  if [[ -d "$stage" && ! -e "$candidate" ]]; then
    rmdir "$stage" || printf 'M8_UPSTREAM_CLEANUP_WARNING: inspect %s\n' "$stage" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT

git -C "$repo" worktree add --detach "$candidate" "$head"
printf '=== Simulated no-commit merge in isolated worktree ===\n'
if ! git -C "$candidate" merge --no-commit --no-ff "$upstream_sha"; then
  git -C "$candidate" status --short
  printf 'M8_UPSTREAM_MERGE_FAIL: conflicts or merge strategy rejected; original feature worktree preserved\n' >&2
  exit 1
fi
printf '=== Inspect merge candidate and run current source contracts ===\n'
git -C "$candidate" status --short
(
  cd "$candidate"
  export PYTHONDONTWRITEBYTECODE=1
  python3 -B -m unittest discover -s ci/tests -p 'test_*.py'
  python3 -B ci/workflow_policy.py
  python3 -B ci/medialibrary.py source
)
printf 'M8_UPSTREAM_STATIC_MERGE_SIM_PASS head=%s upstream=%s\n' "$head" "$upstream_sha"
printf 'M8_UPSTREAM_HOSTED_ANDROID_STILL_REQUIRED (merge simulation is not a build pass)\n'
