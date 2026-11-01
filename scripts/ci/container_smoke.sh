#!/usr/bin/env bash
# Offline container proof only. Build separately; never log in or push an image.
set -euo pipefail
image=${1:?usage: container_smoke.sh IMAGE}
expected=$(mktemp)
actual=$(mktemp)
trap 'rm -f "$expected" "$actual"' EXIT
sources=(geni_upload.py cli_spec.py source_details.py plan_report.py visual_plan.py entrypoint.sh)
destinations=(/opt/geni_upload.py /opt/cli_spec.py /opt/source_details.py /opt/plan_report.py /opt/visual_plan.py /usr/local/bin/geni-uploader-entrypoint)
for i in "${!sources[@]}"; do
  digest=$(sha256sum "${sources[$i]}" | cut -d' ' -f1)
  printf '%s  %s\n' "$digest" "${destinations[$i]}" >> "$expected"
done
docker run --rm --network none --entrypoint sha256sum "$image" "${destinations[@]}" > "$actual"
diff -u "$expected" "$actual"
docker run --rm --network none --entrypoint python "$image" -c 'import sys, yaml; assert sys.version_info[:2] == (3, 15); print(sys.version)'
for script in geni_upload.py source_details.py visual_plan.py; do
  docker run --rm --network none --entrypoint python "$image" "/opt/$script" --help > /dev/null
done
docker run --rm --network none --entrypoint python "$image" -c 'import sys; sys.path.insert(0, "/opt"); import plan_report'
# The real entrypoint must refuse an empty runtime repo without network/credentials.
set +e
docker run --rm --network none "$image" > "$actual" 2>&1
status=$?
set -e
[ "$status" -eq 1 ]
grep -F 'error: set GENI_UPLOAD_REPO' "$actual"
echo 'Offline runtime smoke passed; no vendor access, credentials or publication.'
