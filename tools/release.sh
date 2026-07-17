#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: tools/release.sh [patch|minor|major] [options]
       tools/release.sh --version X.Y.Z [options]

Default bump is patch.

Options:
  --version X.Y.Z   Release an explicit semantic version.
  --no-push         Commit and tag locally, but do not push.
  --dry-run         Show the planned version and checks without changing files.
  -h, --help        Show this help.

Examples:
  tools/release.sh
  tools/release.sh minor
  tools/release.sh major
  tools/release.sh --version 1.0.0
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Run this from inside the Git repository."
cd "${repo_root}"

bump="patch"
explicit_version=""
push=1
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    patch|minor|major)
      bump="$1"
      ;;
    --version)
      [[ $# -ge 2 ]] || die "--version requires X.Y.Z"
      explicit_version="$2"
      shift
      ;;
    --no-push)
      push=0
      ;;
    --dry-run)
      dry_run=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

[[ -f VERSION ]] || die "VERSION file not found."
current="$(tr -d '[:space:]' < VERSION)"
[[ "${current}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION must be X.Y.Z, got '${current}'."

if [[ -n "${explicit_version}" ]]; then
  next="${explicit_version}"
else
  IFS=. read -r major minor patch <<< "${current}"
  case "${bump}" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    major) major=$((major + 1)); minor=0; patch=0 ;;
  esac
  next="${major}.${minor}.${patch}"
fi

[[ "${next}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "Release version must be X.Y.Z, got '${next}'."
[[ "${next}" != "${current}" ]] || die "Next version is the same as current version."

tag="v${next}"
if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  die "Tag ${tag} already exists locally."
fi
if git ls-remote --exit-code --tags origin "${tag}" >/dev/null 2>&1; then
  die "Tag ${tag} already exists on origin."
fi

upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
if [[ -n "${upstream}" ]]; then
  git fetch --quiet
  local_head="$(git rev-parse HEAD)"
  remote_head="$(git rev-parse "${upstream}")"
  merge_base="$(git merge-base HEAD "${upstream}")"
  if [[ "${local_head}" != "${merge_base}" && "${remote_head}" != "${merge_base}" ]]; then
    die "Local branch and ${upstream} have diverged. Pull/rebase before releasing."
  fi
  if [[ "${local_head}" == "${merge_base}" && "${local_head}" != "${remote_head}" ]]; then
    die "Remote ${upstream} has commits that are not local. Pull before releasing."
  fi
fi

echo "Current version: ${current}"
echo "Next version:    ${next}"
echo "Tag:             ${tag}"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Pending changes will be included in the release commit."
fi

if [[ "${dry_run}" == "1" ]]; then
  echo "Dry run only. No files, commits, or tags were changed."
  exit 0
fi

printf '%s\n' "${next}" > VERSION

python3 -m py_compile app/vm_proxy_gateway.py app/vm_proxy_gateway_gui.py tools/validate_scenarios.py
bash -n install.sh
bash -n uninstall.sh
python3 tools/validate_scenarios.py
find . -type d -name __pycache__ -prune -exec rm -rf {} +

git add -A
git commit -m "Release ${tag}"
git tag -a "${tag}" -m "Release ${tag}"

if [[ "${push}" == "1" ]]; then
  git push origin main
  git push origin "${tag}"
else
  echo "Created local commit and tag only. Push later with:"
  echo "  git push origin main"
  echo "  git push origin ${tag}"
fi
