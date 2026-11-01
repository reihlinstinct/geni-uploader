# Generic pullable runtime image for the user-run Geni uploader (issue #49).
# Carries the REVIEWED uploader script pinned in the image; the runtime repo
# is DATA only - no family material, no repository name, no credentials are
# baked in. Safe to publish to a public registry; audit with
# `podman history` before pushing.
# Build context: the repository root (publish-image.yml builds with `docker build .`):
#   docker build -t geni-uploader .
# Base pinned by multi-arch index digest (resolved 2026-10-25).
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV PYTHONPATH=/opt/pkg
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "PyYAML==6.0.3"
COPY geni_upload.py /opt/geni_upload.py
COPY cli_spec.py /opt/cli_spec.py
COPY source_details.py /opt/source_details.py
COPY plan_report.py /opt/plan_report.py
COPY visual_plan.py /opt/visual_plan.py
COPY src/geni_uploader/__init__.py /opt/pkg/geni_uploader/__init__.py
COPY src/geni_uploader/presentation/__init__.py /opt/pkg/geni_uploader/presentation/__init__.py
COPY src/geni_uploader/presentation/plan_report.py /opt/pkg/geni_uploader/presentation/plan_report.py
COPY src/geni_uploader/presentation/visual_plan.py /opt/pkg/geni_uploader/presentation/visual_plan.py
COPY entrypoint.sh /usr/local/bin/geni-uploader-entrypoint
RUN chmod 755 /usr/local/bin/geni-uploader-entrypoint
ENTRYPOINT ["/usr/local/bin/geni-uploader-entrypoint"]
CMD []

