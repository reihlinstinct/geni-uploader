# Generic pullable runtime image for the user-run Geni uploader (issue #49).
# Carries the REVIEWED uploader script pinned in the image; the runtime repo
# is DATA only - no family material, no repository name, no credentials are
# baked in. Safe to publish to a public registry; audit with
# `podman history` before pushing.
# Build context: scripts/geni_upload (its .dockerignore keeps the private
# packages/ out of the daemon):
#   podman build -f scripts/geni_upload/podman/Dockerfile -t geni-uploader scripts/geni_upload
# Base pinned by multi-arch index digest (resolved 2026-10-25).
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "PyYAML==6.0.3"
COPY geni_upload.py /opt/geni_upload.py
COPY source_details.py /opt/source_details.py
COPY plan_report.py /opt/plan_report.py
COPY visual_plan.py /opt/visual_plan.py
COPY entrypoint.sh /usr/local/bin/geni-uploader-entrypoint
RUN chmod 755 /usr/local/bin/geni-uploader-entrypoint
ENTRYPOINT ["/usr/local/bin/geni-uploader-entrypoint"]
CMD []
