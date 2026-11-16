"""Fresh protected-run snapshot reader. No dispatch or deployment approval writer."""

import base64
import hashlib
import json
import re

from geni_uploader.core.merge_request import InvalidMergeRequest
from geni_uploader.evidence.github_review import inspect, requests
from geni_uploader.workflow.merge_http import BoundedJSONHTTP

# Section: Read authenticated run/environment/approval/workflow snapshots


def read_protected_snapshot(client, pins, intent_sha256, workflow_sha256):
    """Require exact run title and workflow bytes plus the existing strict gate.

    pins must come from reviewed immutable release configuration, never a proposal
    or supplied provider body. Snapshot checks do not establish historical rule
    protection, revoke an approval, correlate arbitrary additional jobs or grant
    execution. The public merge execution release remains closed.
    """
    try:
        if type(client) is not BoundedJSONHTTP or client.origin != "https://api.github.com":
            raise InvalidMergeRequest("merge approval source blocked")
        for value in (intent_sha256, workflow_sha256):
            if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
                raise InvalidMergeRequest("merge approval digest blocked")
        descriptors = requests(pins)
        responses, bodies = [], []
        for descriptor in descriptors:
            body = client("GET", descriptor["route"])
            bodies.append(body)
            responses.append(
                {
                    "request": descriptor,
                    "status": 200,
                    "redirected": False,
                    "link": None,
                    "raw": json.dumps(body).encode(),
                }
            )
        checked = inspect(pins, responses)
        run = bodies[0]
        if run.get("display_title") != "explicit-merge:" + intent_sha256:
            raise InvalidMergeRequest("merge approval run binding blocked")
        if run.get("status") != "in_progress" or run.get("conclusion") is not None:
            raise InvalidMergeRequest("merge approval inactive run blocked")
        root = "/repos/" + pins["owner"] + "/" + pins["repo"]
        workflow = client("GET", root + "/contents/" + pins["workflow"] + "?ref=" + pins["sha"])
        if type(workflow) is not dict or workflow.get("encoding") != "base64":
            raise InvalidMergeRequest("merge approval workflow blocked")
        if workflow.get("path") != pins["workflow"] or workflow.get("type") != "file":
            raise InvalidMergeRequest("merge approval workflow source blocked")
        content = base64.b64decode("".join(workflow["content"].split()), validate=True)
        if len(content) > 1024 * 1024 or hashlib.sha256(content).hexdigest() != workflow_sha256:
            raise InvalidMergeRequest("merge approval workflow binding blocked")
        return {
            "run_id": pins["run_id"],
            "attempt": 1,
            "intent_sha256": intent_sha256,
            "workflow_sha256": workflow_sha256,
            "reviewer_id": pins["reviewer_id"],
            "snapshot_sha256": hashlib.sha256(
                json.dumps(bodies, sort_keys=True).encode()
            ).hexdigest(),
            "fresh_snapshot_consistent": True,
            "post_permitted": False,
            "unresolved_release_gaps": checked["release_gaps"],
        }
    except Exception:  # noqa: BLE001 - fixed-message private evidence boundary
        raise InvalidMergeRequest("protected merge snapshot blocked") from None
