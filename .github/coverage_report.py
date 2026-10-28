"""Per-file production coverage from coverage.json, as markdown (#98).

The denominator is explicit: only the PRODUCTION files listed below count.
Tests, CI helpers and the shell entrypoint are never part of it. With
--fail-under N, exits 1 when ANY production file is below N percent, so a
well-covered module cannot hide a weak one inside a combined total.
"""

import argparse
import json
import sys

PRODUCTION = ("geni_upload.py", "source_details.py")
NOT_MEASURED = ("entrypoint.sh",)


def rows(data):
    files = data.get("files", {})
    missing = [name for name in PRODUCTION if name not in files]
    if missing:
        raise SystemExit(f"coverage data lacks production files: {', '.join(missing)}")
    extra = sorted(set(files) - set(PRODUCTION))
    if extra:
        raise SystemExit(f"coverage data includes non-production files: {', '.join(extra)}")
    out = []
    for name in PRODUCTION:
        summary = files[name]["summary"]
        out.append((name, summary["covered_lines"], summary["num_statements"]))
    return out


def percent(covered, statements):
    return 100.0 * covered / statements if statements else 100.0


def render(table, floor):
    lines = [
        "### Production coverage (statements)",
        "",
        "| File | Covered | Statements | Coverage |",
        "|---|---:|---:|---:|",
    ]
    total_cov = sum(c for _, c, _ in table)
    total_stmts = sum(n for _, _, n in table)
    for name, covered, statements in table:
        lines.append(
            f"| `{name}` | {covered} | {statements} | {percent(covered, statements):.2f}% |"
        )
    lines.append(
        f"| **combined** | {total_cov} | {total_stmts} | {percent(total_cov, total_stmts):.2f}% |"
    )
    lines += [
        "",
        f"Denominator: {', '.join(PRODUCTION)} only; tests are excluded.",
        (
            f"Not measured by Python coverage: {', '.join(NOT_MEASURED)} "
            "(shell; exercised by behavioural tests, reported separately)."
        ),
        f"Per-file floor: {floor:g}%.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coverage_json")
    parser.add_argument("--floor", type=float, required=True)
    parser.add_argument(
        "--fail-under",
        action="store_true",
        help="exit 1 when any production file is below the floor",
    )
    args = parser.parse_args(argv)
    with open(args.coverage_json, encoding="utf-8") as stream:
        table = rows(json.load(stream))
    print(render(table, args.floor))
    below = [name for name, c, n in table if percent(c, n) < args.floor]
    if below:
        print(f"\nBelow floor: {', '.join(below)}")
        if args.fail_under:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
