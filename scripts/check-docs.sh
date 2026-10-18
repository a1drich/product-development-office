#!/usr/bin/env bash
# Fails if the docs have drifted:
#   - a tracked markdown file is not linked from README.md (role prompts in
#     office/prompts/ are prompts, not docs, and are exempt)
#   - a relative markdown link points at a file that does not exist
#
#   ./scripts/check-docs.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
fail=0

# Every markdown file must be linked from README.md.
while IFS= read -r f; do
  [ "$f" = README.md ] && continue
  case "$f" in office/prompts/*) continue ;; esac
  if ! grep -qF "]($f)" README.md; then
    echo "not linked from README.md: $f"
    fail=1
  fi
done < <(git ls-files --cached --others --exclude-standard '*.md')

# Every relative link must resolve. Links are taken from (path) after a ], skipping
# URLs and in-page anchors; a #fragment on a file link is stripped.
while IFS= read -r f; do
  dir=$(dirname "$f")
  while IFS= read -r link; do
    target=${link%%#*}
    [ -z "$target" ] && continue
    if [ ! -e "$dir/$target" ]; then
      echo "broken link in $f: $link"
      fail=1
    fi
  done < <(grep -oE '\]\([^)]+\)' "$f" | sed -E 's/^\]\((.*)\)$/\1/' | grep -vE '^(https?:|mailto:|#)' || true)
done < <(git ls-files --cached --others --exclude-standard '*.md')

if [ "$fail" -ne 0 ]; then
  echo "docs check failed"
  exit 1
fi
echo "docs check passed"
