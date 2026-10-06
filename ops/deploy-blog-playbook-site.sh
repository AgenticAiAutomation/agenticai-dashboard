#!/usr/bin/env bash
# Blog Playbook — marketing site step, run as root on the VPS.
#
#   bash /root/blog-playbook-site.sh          (asks first)
#   bash /root/blog-playbook-site.sh --yes
#
# Moves /var/www/agenticai to the new `main` (filter + CSS), restarts the site,
# and proves an existing blog post renders byte-identical: the article body is
# saved before the change and compared after. Any difference, or the site not
# coming back, puts the previous commit back and restarts again.
set -euo pipefail

REPO=/var/www/agenticai
BRANCH=main
SERVICE=agenticai
LOCAL=http://127.0.0.1:5001
STAMP=$(date +%Y%m%d-%H%M%S)
BK=/root/backups/blog-playbook-site-$STAMP

say()  { printf '\n==> %s\n' "$*"; }
stop() { printf '\n!!! %s\n    Nothing was changed.\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || stop "Run this as root."
cd "$REPO"

say "Checking the site"
PREV_SHA=$(git rev-parse HEAD)
CUR_BRANCH=$(git symbolic-ref --quiet --short HEAD || true)
[ "$CUR_BRANCH" = "$BRANCH" ] || stop "The site is on '${CUR_BRANCH:-detached}', expected $BRANCH."
DIRTY=$(git status --porcelain --untracked-files=no)
[ -z "$DIRTY" ] || stop "The live site has local edits git doesn't know about:
$DIRTY"
git fetch -q origin "$BRANCH"
NEW_SHA=$(git rev-parse FETCH_HEAD)
[ "$NEW_SHA" != "$PREV_SHA" ] || stop "Already up to date."
git merge-base --is-ancestor HEAD "$NEW_SHA" || stop "origin/$BRANCH does not contain the live commit."
curl -fsS -o /dev/null "$LOCAL/" || stop "The site is not answering on $LOCAL before the change."

# One existing post, to prove the filter leaves it alone.
POST=$(curl -fsS "$LOCAL/sitemap-blog.xml" 2>/dev/null | grep -o '<loc>[^<]*</loc>' | head -1 \
       | sed -E 's#<loc>https?://[^/]+##; s#</loc>##' || true)
body_of() { curl -fsS "$LOCAL$1" | awk '/<article class="postbody">/{on=1} on{print} /<\/article>/{if(on){exit}}'; }

say "These commits will go live"
git log --oneline "HEAD..$NEW_SHA"
echo
echo "    check post: ${POST:-none published — comparison skipped}"
if [ "${1:-}" = --yes ]; then
  echo "Deploy? yes (given as --yes)"
else
  OK=""
  while [ -z "$OK" ]; do
    read -r -p "Deploy? Type yes to continue: " OK || stop "No answer."
    OK=${OK//$'\r'/}
  done
  [ "$OK" = yes ] || stop "Cancelled."
fi

mkdir -p "$BK"
echo "$PREV_SHA" > "$BK/previous-commit.txt"
if [ -n "$POST" ]; then
  body_of "$POST" > "$BK/post-before.html" || stop "Could not fetch $POST."
  # An empty capture would make the comparison meaningless.
  [ -s "$BK/post-before.html" ] || stop "$POST has no <article class=\"postbody\"> to compare."
fi

rollback() {
  printf '\n!!! %s — rolling back\n' "$1" >&2
  git checkout -q -B "$BRANCH" "$PREV_SHA"
  systemctl restart "$SERVICE"; sleep 4
  curl -fsS -o /dev/null "$LOCAL/" && echo "    Rolled back to $(git rev-parse --short HEAD); site healthy." >&2 \
    || echo "    Rolled back but the site is not answering — journalctl -u $SERVICE" >&2
  exit 1
}

say "Code → $BRANCH @ $(git rev-parse --short "$NEW_SHA")"
git merge -q --ff-only "$NEW_SHA"
systemctl restart "$SERVICE"
UP=0
for _ in $(seq 1 12); do sleep 3; curl -fsS -o /dev/null "$LOCAL/" && { UP=1; break; }; done
[ "$UP" = 1 ] || rollback "site not answering after restart"

if [ -n "$POST" ]; then
  body_of "$POST" > "$BK/post-after.html" || rollback "could not fetch $POST after the change"
  cmp -s "$BK/post-before.html" "$BK/post-after.html" || rollback "$POST changed — it must stay byte-identical"
  echo "    $POST: article body byte-identical"
fi

say "Done — site on $(git rev-parse --short HEAD)"
echo "    Next: bash /root/blog-playbook-flag.sh me"
