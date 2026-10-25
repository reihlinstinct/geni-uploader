"""Render a Jenkins-style per-test report from junit.xml to stdout (markdown).

Failures/errors first with their messages, then skips with reasons, then
passes collapsed. Used by the CI workflow's summary step.
"""

import sys
import xml.etree.ElementTree as ET


def main(path):
    tree = ET.parse(path)
    suites = tree.getroot().iter("testsuite")
    passed, failed, skipped = [], [], []
    for case in (c for s in suites for c in s.iter("testcase")):
        name = f"{case.get('classname')}::{case.get('name')}"
        # ElementTree: an element with no children is falsy - never use
        # `find(...) or find(...)` here, it misclassifies failures as passes.
        fail = case.find("failure")
        if fail is None:
            fail = case.find("error")
        skip = case.find("skipped")
        if fail is not None:
            failed.append((name, (fail.get("message") or "").strip()))
        elif skip is not None:
            skipped.append((name, (skip.get("message") or "no reason given").strip()))
        else:
            passed.append(name)
    total = len(passed) + len(failed) + len(skipped)
    print(
        f"## Test report: {total} tests - "
        f"{len(passed)} passed, {len(failed)} failed, {len(skipped)} skipped\n"
    )
    if failed:
        print("### Failures\n")
        for name, msg in failed:
            print(f"<details><summary>FAIL {name}</summary>\n\n```\n{msg}\n```\n</details>\n")
    if skipped:
        print("### Skipped (with reason)\n")
        for name, msg in skipped:
            print(f"- SKIP {name} - {msg}")
        print()
    if passed:
        print(f"<details><summary>{len(passed)} passed</summary>\n")
        for name in passed:
            print(f"- PASS {name}")
        print("\n</details>")
    return 0  # the pytest step owns the job conclusion; this report always posts


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
