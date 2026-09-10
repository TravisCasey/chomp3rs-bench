"""The benchmark manifest: the cases, the chomp3rs configurations and the tiers.

`load` reads `cases/manifest.toml` into records, resolving each tier's
`includes` into the full case list; `expand` turns a tier into the flat list of
runs it asks for, one per case and tool and configuration, before repetitions.

Used by every subcommand of `bench.cli`.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CHOMP3RS = "chomp3rs"


@dataclass
class CaseEntry:
    name: str
    file: str
    path: Path
    family: str
    columns: str
    size: str
    generator: str | None = None
    seed: int | None = None
    parameters: dict = field(default_factory=dict)


@dataclass
class Study:
    name: str
    cases: list[str]
    configs: list[str]


@dataclass
class Tier:
    name: str
    cases: list[str]
    tools: list[str]
    configs: list[str]
    studies: list[Study]
    repetitions: int
    timeout_seconds: int
    memory_limit_gigabytes: int


@dataclass
class Manifest:
    root: Path
    cases: dict[str, CaseEntry]
    configs: dict[str, dict]
    tiers: dict[str, Tier]


@dataclass
class Run:
    case: str
    tool: str
    config: str
    tier: str


def load(path):
    path = Path(path)
    root = path.parent
    document = tomllib.loads(path.read_text())
    cases = {
        name: CaseEntry(
            name=name,
            file=entry["file"],
            path=root / entry["file"],
            family=entry["family"],
            columns=entry["columns"],
            size=entry["size"],
            generator=entry.get("generator"),
            seed=entry.get("seed"),
            parameters=entry.get("parameters", {}),
        )
        for name, entry in document["cases"].items()
    }
    tiers = {
        name: Tier(
            name=name,
            cases=collect(document["tiers"], name, "cases"),
            tools=entry["tools"],
            configs=entry["configs"],
            studies=[
                Study(
                    name=study["name"],
                    cases=study["cases"],
                    configs=study["configs"],
                )
                for study in collect(document["tiers"], name, "studies")
            ],
            repetitions=entry["repetitions"],
            timeout_seconds=entry["timeout_seconds"],
            memory_limit_gigabytes=entry["memory_limit_gigabytes"],
        )
        for name, entry in document["tiers"].items()
    }
    return Manifest(root=root, cases=cases, configs=document["configs"], tiers=tiers)


def collect(tier_documents, name, key):
    """Gather a tier's entries under `key`, the included tiers' first."""
    entry = tier_documents[name]
    gathered = []
    for included in entry.get("includes", []):
        gathered.extend(collect(tier_documents, included, key))
    gathered.extend(entry.get(key, []))
    unique = []
    for item in gathered:
        if item not in unique:
            unique.append(item)
    return unique


def expand(manifest, tier_name):
    tier = manifest.tiers[tier_name]
    runs = []
    for case in tier.cases:
        for tool in tier.tools:
            if tool != CHOMP3RS:
                runs.append(Run(case=case, tool=tool, config="default", tier=tier.name))
        for config in tier.configs:
            runs.append(Run(case=case, tool=CHOMP3RS, config=config, tier=tier.name))
    for study in tier.studies:
        for case in study.cases:
            for config in study.configs:
                runs.append(
                    Run(case=case, tool=CHOMP3RS, config=config, tier=tier.name)
                )
    return runs
