"""The correctness check: tool measurements are required to agree.

A case whose sidecar holds a closed form is compared against it; a case without
one is decided by the answers agreeing with each other, and counts as checked
only where two tools answered it. A case with nothing to compare, or with only
one tool behind it, is reported as unchecked, which is not a failure. Each
record's `status` becomes `disputed` where it is part of a disagreement and
`finished` where it is not, written only when it changes; that field is the
only thing in a record this program changes.

Invoked as `bench check <tier> [--runs-directory PATH]`; see `bench.cli`.
"""

from dataclasses import dataclass, field

from bench import cases, records

FINISHED = "finished"
DISPUTED = "disputed"
COMPARABLE = (FINISHED, DISPUTED)
DEFAULT_CONFIG = "default"


@dataclass
class CheckReport:
    checked: int = 0
    disputed_records: int = 0
    disputed: list[dict] = field(default_factory=list)
    unchecked: list[dict] = field(default_factory=list)


def check_tier(manifest, tier_name, runs_directory=records.RUNS_DIRECTORY):
    report = CheckReport()
    found = group_by_case(tier_name, runs_directory)
    for name in manifest.tiers[tier_name].cases:
        if name not in found:
            continue
        case = cases.load_case(name, manifest)
        key = "bar_counts" if case.graded else "betti"
        comparable = [
            (path, record)
            for path, record in found[name]
            if record["status"] in COMPARABLE and record["answer"].get(key) is not None
        ]
        known = case.bar_counts if key == "bar_counts" else case.betti
        if known is not None:
            check_against_sidecar(report, comparable, key, known)
        else:
            check_across_answers(report, name, comparable, key)
    return report


def group_by_case(tier_name, runs_directory):
    grouped = {}
    for path in records.paths_in(tier_name, runs_directory):
        record = records.read(path)
        grouped.setdefault(record["case"], []).append((path, record))
    return grouped


def check_against_sidecar(report, comparable, key, known):
    for path, record in comparable:
        expected, found = compared(
            known, record["answer"][key], record["config"].get("check_dimensions")
        )
        if expected == found:
            report.checked += 1
            settle(path, record, FINISHED)
            continue
        report.disputed_records += 1
        settle(path, record, DISPUTED)
        report.disputed.append(
            {"path": str(path), "expected": expected, "found": found}
        )


def check_across_answers(report, name, comparable, key):
    """Decide a case with no closed form: one answer per tool and configuration,
    every repetition equal to it and every pair of them agreeing. A case only
    one tool answered can be disputed, since a tool disagreeing with itself is
    a finding, but it is never counted as checked."""
    if len(comparable) < 2:
        reason = f"no closed form and only {len(comparable)} of the records answered"
        report.unchecked.append({"case": name, "reason": reason})
        return
    groups = {}
    for path, record in sorted(comparable, key=lambda entry: entry[0]):
        groups.setdefault(configuration_of(record), []).append(record)
    answers = {}
    comparisons = 0
    disagreeing = False
    for label, grouped in groups.items():
        answers[label] = grouped[0]["answer"][key]
        for repeated in grouped[1:]:
            comparisons += 1
            if repeated["answer"][key] == answers[label]:
                continue
            disagreeing = True
            differs = f"{label} repetition {repeated['repetition']} differs"
            answers[differs] = repeated["answer"][key]
    pairs, pairs_disagree = compare_pairwise(
        [
            (grouped[0]["answer"][key], grouped[0]["config"].get("check_dimensions"))
            for grouped in groups.values()
        ]
    )
    comparisons += pairs
    disagreeing = disagreeing or pairs_disagree
    if disagreeing:
        for path, record in comparable:
            settle(path, record, DISPUTED)
        report.disputed_records += len(comparable)
        report.disputed.append({"case": name, "answers": answers})
        return
    if comparisons == 0:
        report.unchecked.append({"case": name, "reason": "no shared dimensions"})
        return
    for path, record in comparable:
        settle(path, record, FINISHED)
    tools = sorted({grouped[0]["tool"] for grouped in groups.values()})
    if len(tools) < 2:
        report.unchecked.append({"case": name, "reason": f"only {tools[0]} answered"})
        return
    report.checked += len(comparable)


def configuration_of(record):
    """How a record's answer is named in a report: its tool, and its
    configuration too where the tool has more than the one."""
    name = record["config"]["name"]
    if name == DEFAULT_CONFIG:
        return record["tool"]
    return f"{record['tool']} {name}"


def compare_pairwise(representatives):
    """How many pairs of representatives shared a dimension to compare, and
    whether any such pair disagreed."""
    comparisons = 0
    disagreeing = False
    for index, (first, first_dimensions) in enumerate(representatives):
        for second, second_dimensions in representatives[index + 1 :]:
            left, right = compared(first, second, first_dimensions, second_dimensions)
            if not left:
                continue
            comparisons += 1
            disagreeing = disagreeing or left != right
    return comparisons, disagreeing


def compared(first, second, *restrictions):
    """The two answers on the dimensions both reported, narrowed to the
    dimensions a restricted configuration declares its answer holds on."""
    dimensions = list(range(min(len(first), len(second))))
    for restriction in restrictions:
        if restriction is not None:
            dimensions = [
                dimension for dimension in dimensions if dimension in restriction
            ]
    return (
        [first[dimension] for dimension in dimensions],
        [second[dimension] for dimension in dimensions],
    )


def settle(path, record, status):
    if status != record["status"]:
        record["status"] = status
        records.save_at(path, record)


def print_report(report):
    for entry in report.disputed:
        if "path" in entry:
            print(
                f"disputed {entry['path']}"
                f" expected {entry['expected']} found {entry['found']}"
            )
            continue
        print(f"disagreement {entry['case']}")
        for label, answer in entry["answers"].items():
            print(f"  {label} {answer}")
    for entry in report.unchecked:
        print(f"unchecked {entry['case']} {entry['reason']}")
    print(
        f"{report.checked} checked, {report.disputed_records} disputed,"
        f" {len(report.unchecked)} unchecked"
    )
