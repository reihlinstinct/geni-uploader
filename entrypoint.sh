#!/bin/sh
# Generic runtime git-pull entrypoint (issue #49).
# The image carries the REVIEWED, PINNED uploader at /opt/geni_upload.py;
# the runtime repo is DATA ONLY (manifest, scan, status) - its code is never
# executed. Credentials: a read/write GitHub token mounted at /run/gh-token
# reaches git only through a prompt-aware GIT_ASKPASS that answers ONLY
# github.com prompts. With --rm --tmpfs /work the clone never lands in
# Podman storage (tmpfs is memory; the host kernel may swap).
set -eu

TOKEN_FILE="${GH_TOKEN_FILE:-/run/gh-token}"
REPO="${GENI_UPLOAD_REPO:-}"
REF="${GENI_UPLOAD_REF:-}"
EXPECT_SHA="${GENI_UPLOAD_EXPECT_SHA:-}"
DEST=/work/repo

if [ -z "$REPO" ]; then
  echo "error: set GENI_UPLOAD_REPO (https://github.com/OWNER/REPO.git)" >&2
  exit 1
fi
# Strict URL validation: the askpass will hand the token to github.com ONLY,
# but refuse non-github remotes outright unless explicitly running E2E tests.
case "$REPO" in
  https://github.com/*/*.git|https://x-access-token@github.com/*/*.git) ;;
  *)
    if [ "${GENI_UPLOAD_E2E:-}" != "1" ]; then
      echo "error: GENI_UPLOAD_REPO must be a github.com https URL" >&2
      exit 1
    fi ;;
esac
if [ ! -s "$TOKEN_FILE" ] && [ "${GENI_UPLOAD_E2E:-}" != "1" ]; then
  echo "error: GitHub token file missing or empty at $TOKEN_FILE" >&2
  exit 1
fi

# Prompt-aware askpass: answer github.com prompts only; username prompts get
# the fixed login, password prompts get the token file's content, anything
# else is refused.
if [ -s "$TOKEN_FILE" ]; then
  ASKPASS="$(mktemp)"
  chmod 700 "$ASKPASS"
  cat > "$ASKPASS" <<ASK
#!/bin/sh
case "\$1" in
  *github.com*Username*|*Username*github.com*) printf 'x-access-token' ;;
  *github.com*) exec cat "$TOKEN_FILE" ;;
  *) exit 1 ;;
esac
ASK
  export GIT_ASKPASS="$ASKPASS"
fi
export GIT_TERMINAL_PROMPT=0

if [ -n "$REF" ]; then
  git clone --quiet --depth 1 --branch "$REF" "$REPO" "$DEST"
else
  git clone --quiet --depth 1 "$REPO" "$DEST"
fi
if [ -n "$EXPECT_SHA" ]; then
  ACTUAL="$(git -C "$DEST" rev-parse HEAD)"
  if [ "$ACTUAL" != "$EXPECT_SHA" ]; then
    echo "error: cloned HEAD $ACTUAL != GENI_UPLOAD_EXPECT_SHA $EXPECT_SHA" >&2
    exit 1
  fi
fi
# GIT_ASKPASS stays exported: the uploader pushes upload-status.yaml back to
# the same repo after each verified upload.
echo "pulled $(git -C "$DEST" rev-parse --short HEAD); running the pinned uploader"

cd "$DEST"
case "${1:-}" in
  details-validate|details-plan|details-repair|details-snapshot)
    MODE="${1#details-}"
    shift
    exec python /opt/source_details.py "$MODE" "$@"
    ;;
  *) exec python /opt/geni_upload.py "$@" ;;
esac
