from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WORKSPACE_ROOT.parent


def _resolve_mcp_root() -> Path:
    candidates = [
        PROJECT_ROOT / "fbbp-mcp-rag-server",
        PROJECT_ROOT / "fbtp-mcp-rag-server",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


MCP_ROOT = _resolve_mcp_root()
DESCRIPTOR_PATH = MCP_ROOT / "configs" / "datasets" / "fbbp_private_v2026_04.json"
SNAPSHOT_ROOT = MCP_ROOT / "formal_snapshots" / "fbbp_private_v2026_04"
DEFAULT_OUTPUT_ROOT = WORKSPACE_ROOT / "final_results" / "fbbp_formal_atlas_v2026_04"
PACKAGE_VERSION = "2026.04.18"
DATASET_NAME = "FBBP"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the official full-data FBBP formal results package")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--now")
    return parser.parse_args()


def _parse_now(raw: str | None) -> datetime:
    if raw:
        return datetime.fromisoformat(raw)
    return datetime.now(UTC)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _extract_prefixed_value(content: str, prefix: str) -> str | None:
    for line in content.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
            return value or None
    return None


def _split_csv_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = [item.strip() for item in raw.split(";")]
    return [item for item in values if item and item.lower() != "nan"]


def _split_comma_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = [item.strip() for item in raw.split(",")]
    return [item for item in values if item and item.lower() != "nan"]


def _csv_cell(values: list[str]) -> str:
    return "; ".join(values)


def _top_counter_items(counter: Counter[str], limit: int = 5) -> list[list[Any]]:
    return [[key, count] for key, count in counter.most_common(limit)]


def _load_target_maps(raw_records: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], Counter[str]]:
    conceptual_targets: dict[str, dict[str, Any]] = {}
    species_variants: dict[str, dict[str, Any]] = {}
    source_counts: Counter[str] = Counter()

    for row in raw_records:
        source = str(row.get("source") or "").strip()
        if source:
            source_counts[source] += 1

        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        table_name = str(metadata.get("table_name") or "").strip()
        primary_key = str(metadata.get("primary_key_value") or "").strip()
        content = str(row.get("content") or "")

        if table_name == "targets_conceptual" and primary_key:
            conceptual_targets[primary_key] = {
                "target_concept_id": primary_key,
                "gene_name": _extract_prefixed_value(content, "Gene Name: "),
                "protein_name": _extract_prefixed_value(content, "Protein Name: "),
            }
        elif table_name == "target_species_variants" and primary_key:
            species_variants[primary_key] = {
                "target_variant_id": primary_key,
                "target_concept_id": _extract_prefixed_value(content, "Target Concept Id: "),
                "gene_name_species": _extract_prefixed_value(content, "Gene Name Species: "),
                "species_name": _extract_prefixed_value(content, "Species Name: "),
                "uniprot_id": _extract_prefixed_value(content, "Uniprot Id: "),
            }

    return conceptual_targets, species_variants, source_counts


def _parse_interaction_card(row: dict[str, Any]) -> dict[str, Any]:
    content = str(row.get("content") or "")
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    return {
        "source": row.get("source"),
        "chunk_id": row.get("chunk_id"),
        "interaction_id": _extract_prefixed_value(content, "- Interaction ID: "),
        "domain_id": _extract_prefixed_value(content, "- Domain Id: "),
        "protein_name": _extract_prefixed_value(content, "- Canonical Name: "),
        "organism": _extract_prefixed_value(content, "- Organism: "),
        "description": _extract_prefixed_value(content, "- Description: "),
        "domain_name": _extract_prefixed_value(content, "- Domain Name: "),
        "sequence": _extract_prefixed_value(content, "- Sequence: "),
        "is_engineered": _extract_prefixed_value(content, "- Is Engineered: "),
        "scaffold": _extract_prefixed_value(content, "- Scaffold Type: "),
        "development_stage": _extract_prefixed_value(content, "- Development Stage: "),
        "table_sources": list(metadata.get("table_sources") or _split_comma_values(_extract_prefixed_value(content, "- Tables: "))),
        "protein_id": metadata.get("protein_id"),
        "target_variant_id": metadata.get("target_variant_id"),
        "target_concept_id": metadata.get("target_concept_id"),
    }


def _parse_protein_card(row: dict[str, Any]) -> dict[str, Any]:
    content = str(row.get("content") or "")
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    domain_matches = re.findall(r"- Domain ([^:]+): (.+?) \| scaffold=([^ |]+) \| engineered=([^ |\n]+)", content)
    interaction_matches = re.findall(r"- Interaction ([^:]+): class=([^|\n]+)\s+\|\s+inhibitory=([^\n]+)", content)

    return {
        "protein_id": metadata.get("protein_id"),
        "canonical_name": _extract_prefixed_value(content, "- Canonical Name: "),
        "organism": _extract_prefixed_value(content, "- Organism: "),
        "description": _extract_prefixed_value(content, "- Description: "),
        "domain_summaries": [
            {
                "domain_id": domain_id.strip(),
                "domain_name": domain_name.strip(),
                "scaffold": scaffold.strip(),
                "engineered": engineered.strip(),
            }
            for domain_id, domain_name, scaffold, engineered in domain_matches
        ],
        "interaction_summaries": [
            {
                "interaction_id": interaction_id.strip(),
                "class": interaction_class.strip(),
                "inhibitory": inhibitory.strip(),
            }
            for interaction_id, interaction_class, inhibitory in interaction_matches
        ],
        "table_sources": list(metadata.get("table_sources") or _split_comma_values(_extract_prefixed_value(content, "- Tables: "))),
    }


def _resolve_target_label(
    interaction_row: dict[str, Any],
    conceptual_targets: dict[str, dict[str, Any]],
    species_variants: dict[str, dict[str, Any]],
) -> tuple[str | None, dict[str, Any]]:
    target_variant_id = str(interaction_row.get("target_variant_id") or "").strip()
    target_concept_id = str(interaction_row.get("target_concept_id") or "").strip()

    variant_row = species_variants.get(target_variant_id) if target_variant_id and target_variant_id.lower() != "nan" else None
    if variant_row and not target_concept_id:
        target_concept_id = str(variant_row.get("target_concept_id") or "").strip()

    concept_row = conceptual_targets.get(target_concept_id) if target_concept_id and target_concept_id.lower() != "nan" else None

    label = None
    if variant_row:
        label = variant_row.get("gene_name_species") or variant_row.get("species_name")
    if not label and concept_row:
        label = concept_row.get("gene_name") or concept_row.get("protein_name")

    return (str(label).strip() if label else None), {
        "target_variant_id": target_variant_id or None,
        "target_concept_id": target_concept_id or None,
        "variant": variant_row or {},
        "concept": concept_row or {},
    }


def _build_atlas(
    interaction_cards: list[dict[str, Any]],
    protein_cards: list[dict[str, Any]],
    conceptual_targets: dict[str, dict[str, Any]],
    species_variants: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    protein_by_id = {str(card.get("protein_id")): card for card in protein_cards if card.get("protein_id")}
    scaffold_stats: dict[str, dict[str, Any]] = {}
    target_registry_rows: list[dict[str, Any]] = []

    for row in interaction_cards:
        scaffold = str(row.get("scaffold") or "").strip()
        if not scaffold:
            continue

        bucket = scaffold_stats.setdefault(
            scaffold,
            {
                "scaffold": scaffold,
                "entry_count": 0,
                "protein_ids": set(),
                "protein_counter": Counter(),
                "organism_counter": Counter(),
                "engineered_counter": Counter(),
                "target_counter": Counter(),
                "interaction_class_counter": Counter(),
                "source_table_counter": Counter(),
                "representative_interactions": [],
            },
        )

        bucket["entry_count"] += 1
        protein_id = str(row.get("protein_id") or "").strip()
        if protein_id:
            bucket["protein_ids"].add(protein_id)
        protein_name = str(row.get("protein_name") or "").strip()
        if protein_name:
            bucket["protein_counter"][protein_name] += 1
        organism = str(row.get("organism") or "").strip()
        if organism:
            bucket["organism_counter"][organism] += 1
        engineered = str(row.get("is_engineered") or "Unknown").strip() or "Unknown"
        bucket["engineered_counter"][engineered] += 1
        for table_name in row.get("table_sources") or []:
            bucket["source_table_counter"][str(table_name)] += 1
        if len(bucket["representative_interactions"]) < 5:
            bucket["representative_interactions"].append(str(row.get("interaction_id") or ""))

        target_label, target_meta = _resolve_target_label(row, conceptual_targets, species_variants)
        if target_label:
            bucket["target_counter"][target_label] += 1
            target_registry_rows.append(
                {
                    "scaffold": scaffold,
                    "interaction_id": row.get("interaction_id"),
                    "chunk_id": row.get("chunk_id"),
                    "protein_id": row.get("protein_id"),
                    "protein_name": row.get("protein_name"),
                    "organism": row.get("organism"),
                    "domain_id": row.get("domain_id"),
                    "domain_name": row.get("domain_name"),
                    "target_label": target_label,
                    "target_variant_id": target_meta["target_variant_id"],
                    "target_concept_id": target_meta["target_concept_id"],
                    "target_gene_name_species": target_meta["variant"].get("gene_name_species"),
                    "target_species_name": target_meta["variant"].get("species_name"),
                    "target_concept_gene_name": target_meta["concept"].get("gene_name"),
                    "target_concept_protein_name": target_meta["concept"].get("protein_name"),
                    "source": row.get("source"),
                }
            )

    for protein_card in protein_cards:
        for domain_summary in protein_card.get("domain_summaries") or []:
            scaffold = str(domain_summary.get("scaffold") or "").strip()
            if not scaffold or scaffold not in scaffold_stats:
                continue
            bucket = scaffold_stats[scaffold]
            for interaction_summary in protein_card.get("interaction_summaries") or []:
                interaction_class = str(interaction_summary.get("class") or "").strip()
                if interaction_class and interaction_class.lower() != "n/a":
                    bucket["interaction_class_counter"][interaction_class] += 1

    atlas_rows: list[dict[str, Any]] = []
    for scaffold, bucket in sorted(scaffold_stats.items(), key=lambda item: (-int(item[1]["entry_count"]), item[0].lower())):
        atlas_rows.append(
            {
                "scaffold": scaffold,
                "entry_count": bucket["entry_count"],
                "protein_count": len(bucket["protein_ids"]),
                "engineered_yes_count": bucket["engineered_counter"].get("Yes", 0),
                "engineered_no_count": bucket["engineered_counter"].get("No", 0),
                "engineered_unknown_count": bucket["engineered_counter"].get("Unknown", 0),
                "organism_count": len(bucket["organism_counter"]),
                "top_organisms": _top_counter_items(bucket["organism_counter"], limit=5),
                "target_linked_row_count": sum(bucket["target_counter"].values()),
                "top_targets": _top_counter_items(bucket["target_counter"], limit=5),
                "top_interaction_classes": _top_counter_items(bucket["interaction_class_counter"], limit=5),
                "top_proteins": _top_counter_items(bucket["protein_counter"], limit=5),
                "source_tables": _top_counter_items(bucket["source_table_counter"], limit=8),
                "representative_interactions": list(bucket["representative_interactions"]),
            }
        )

    total_target_linked_rows = len(target_registry_rows)
    overview = {
        "scaffold_count": len(atlas_rows),
        "interaction_card_count": len(interaction_cards),
        "protein_card_count": len(protein_cards),
        "target_linked_row_count": total_target_linked_rows,
        "target_linked_scaffold_count": sum(1 for row in atlas_rows if row["target_linked_row_count"] > 0),
        "top_scaffolds": [
            {
                "scaffold": row["scaffold"],
                "entry_count": row["entry_count"],
                "target_linked_row_count": row["target_linked_row_count"],
            }
            for row in atlas_rows[:5]
        ],
    }
    return atlas_rows, target_registry_rows, overview


def _build_source_registry_snapshot(descriptor: dict[str, Any], source_counts: Counter[str]) -> list[dict[str, Any]]:
    registry = descriptor.get("source_registry") or {}
    if not isinstance(registry, dict):
        return []

    snapshot_rows: list[dict[str, Any]] = []
    for source_name, payload in registry.items():
        row = dict(payload if isinstance(payload, dict) else {})
        row["source"] = source_name
        row["chunk_count"] = int(source_counts.get(source_name, 0))
        snapshot_rows.append(row)

    return sorted(snapshot_rows, key=lambda row: (-int(row.get("chunk_count") or 0), str(row.get("source") or "").lower()))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "| " + " | ".join(headers) + " |\n|" + "|".join(["---"] * len(headers)) + "|\n| n/a | n/a |\n"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines) + "\n"


def _build_overview_markdown(
    *,
    descriptor: dict[str, Any],
    manifest: dict[str, Any],
    atlas_rows: list[dict[str, Any]],
    target_registry_rows: list[dict[str, Any]],
    source_snapshot: list[dict[str, Any]],
) -> str:
    top_scaffold_rows = [
        [
            row["scaffold"],
            row["entry_count"],
            row["target_linked_row_count"],
            _csv_cell([item[0] for item in row["top_targets"][:3]]) or "n/a",
            _csv_cell([item[0] for item in row["top_proteins"][:3]]) or "n/a",
        ]
        for row in atlas_rows
    ]
    target_scaffold_rows = [
        [
            row["scaffold"],
            row["target_linked_row_count"],
            _csv_cell([f"{item[0]} ({item[1]})" for item in row["top_targets"][:5]]) or "n/a",
        ]
        for row in atlas_rows
        if row["target_linked_row_count"] > 0
    ]
    source_rows = [
        [
            row["source"],
            row["chunk_count"],
            row.get("source_category") or "n/a",
            row.get("owner_table") or "n/a",
        ]
        for row in source_snapshot[:10]
    ]

    lines = [
        "# FBBP Formal Atlas Overview",
        "",
        "## Dataset Identity",
        f"- Dataset name: `{manifest['dataset_name']}`",
        f"- Dataset version: `{manifest['dataset_version']}`",
        f"- Runtime profile: `{manifest['runtime_profile']}`",
        f"- DB identity: `{manifest['db_identity']}`",
        f"- Build ID: `{manifest['build_id']}`",
        f"- Source registry version: `{manifest['source_registry_version']}`",
        f"- Package version: `{manifest['package_version']}`",
        "",
        "## Headline Metrics",
        f"- Scaffold classes: `{manifest['scaffold_count']}`",
        f"- Interaction cards analyzed: `{manifest['interaction_card_count']}`",
        f"- Protein cards analyzed: `{manifest['protein_card_count']}`",
        f"- Raw records referenced: `{manifest['raw_record_count']}`",
        f"- Target-linked interaction rows: `{manifest['target_linked_row_count']}`",
        f"- Registered sources in appendix: `{manifest['source_registry_count']}`",
        "",
        "## Scaffold Atlas",
        _markdown_table(
            ["Scaffold", "Interaction rows", "Target-linked rows", "Top targets", "Representative proteins"],
            top_scaffold_rows,
        ).rstrip(),
        "",
        "## Target-Linked Coverage",
        _markdown_table(
            ["Scaffold", "Target-linked rows", "Top supported targets"],
            target_scaffold_rows,
        ).rstrip(),
        "",
        "## Source Registry Highlights",
        _markdown_table(
            ["Source", "Chunk count", "Category", "Owner table"],
            source_rows,
        ).rstrip(),
        "",
        "## Notes",
        "- This package is generated deterministically from the checked-in formal FBBP snapshot under `fbbp-mcp-rag-server/formal_snapshots/fbbp_private_v2026_04/`.",
        "- It is intended to be the canonical GitHub, resume, and demo result package for the current FBBP formal line.",
        "- It avoids demo datasets and does not depend on temporary smoke outputs.",
        f"- The appendix contains `{len(target_registry_rows)}` target-linked registry rows and `{len(source_snapshot)}` source-registry rows.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    now = _parse_now(args.now)
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    descriptor = _load_json(DESCRIPTOR_PATH)
    snapshot_manifest = _load_json(SNAPSHOT_ROOT / "MANIFEST.json")
    raw_records = _load_jsonl(SNAPSHOT_ROOT / "raw_records.jsonl")
    protein_cards = [_parse_protein_card(row) for row in _load_jsonl(SNAPSHOT_ROOT / "protein_cards_v2.jsonl")]
    interaction_cards = [_parse_interaction_card(row) for row in _load_jsonl(SNAPSHOT_ROOT / "interaction_cards_v2.jsonl")]

    conceptual_targets, species_variants, source_counts = _load_target_maps(raw_records)
    atlas_rows, target_registry_rows, overview = _build_atlas(
        interaction_cards=interaction_cards,
        protein_cards=protein_cards,
        conceptual_targets=conceptual_targets,
        species_variants=species_variants,
    )
    source_snapshot = _build_source_registry_snapshot(descriptor, source_counts)

    manifest = {
        "dataset_name": DATASET_NAME,
        "dataset_version": descriptor["dataset_version"],
        "runtime_profile": "local_formal",
        "formal_db_mode": descriptor.get("formal_db_mode"),
        "db_identity": descriptor.get("db_identity"),
        "build_id": descriptor.get("build_id"),
        "source_registry_version": descriptor.get("source_registry_version"),
        "package_version": PACKAGE_VERSION,
        "generated_at_utc": now.astimezone(UTC).isoformat(),
        "generator": "build_fbbp_formal_package.py",
        "snapshot_root": str(SNAPSHOT_ROOT),
        "snapshot_manifest": str(SNAPSHOT_ROOT / "MANIFEST.json"),
        "scaffold_count": overview["scaffold_count"],
        "interaction_card_count": overview["interaction_card_count"],
        "protein_card_count": overview["protein_card_count"],
        "raw_record_count": len(raw_records),
        "target_linked_row_count": overview["target_linked_row_count"],
        "source_registry_count": len(source_snapshot),
    }

    atlas_overview = {
        **manifest,
        "headline_metrics": overview,
        "top_scaffolds": overview["top_scaffolds"],
    }

    scaffold_atlas_csv_rows = [
        {
            "scaffold": row["scaffold"],
            "entry_count": row["entry_count"],
            "protein_count": row["protein_count"],
            "engineered_yes_count": row["engineered_yes_count"],
            "engineered_no_count": row["engineered_no_count"],
            "engineered_unknown_count": row["engineered_unknown_count"],
            "organism_count": row["organism_count"],
            "target_linked_row_count": row["target_linked_row_count"],
            "top_targets": _csv_cell([f"{item[0]} ({item[1]})" for item in row["top_targets"]]),
            "top_interaction_classes": _csv_cell([f"{item[0]} ({item[1]})" for item in row["top_interaction_classes"]]),
            "top_organisms": _csv_cell([f"{item[0]} ({item[1]})" for item in row["top_organisms"]]),
            "top_proteins": _csv_cell([f"{item[0]} ({item[1]})" for item in row["top_proteins"]]),
            "source_tables": _csv_cell([f"{item[0]} ({item[1]})" for item in row["source_tables"]]),
            "representative_interactions": _csv_cell(row["representative_interactions"]),
        }
        for row in atlas_rows
    ]

    target_registry_csv_rows = [
        {
            "scaffold": row["scaffold"],
            "interaction_id": row["interaction_id"],
            "protein_id": row["protein_id"],
            "protein_name": row["protein_name"],
            "organism": row["organism"],
            "domain_id": row["domain_id"],
            "domain_name": row["domain_name"],
            "target_label": row["target_label"],
            "target_variant_id": row["target_variant_id"],
            "target_concept_id": row["target_concept_id"],
            "target_gene_name_species": row["target_gene_name_species"],
            "target_species_name": row["target_species_name"],
            "target_concept_gene_name": row["target_concept_gene_name"],
            "target_concept_protein_name": row["target_concept_protein_name"],
            "source": row["source"],
            "chunk_id": row["chunk_id"],
        }
        for row in sorted(
            target_registry_rows,
            key=lambda item: (
                str(item.get("scaffold") or "").lower(),
                str(item.get("target_label") or "").lower(),
                str(item.get("interaction_id") or "").lower(),
            ),
        )
    ]

    _write_json(output_root / "package_manifest.json", manifest)
    _write_json(output_root / "atlas_overview.json", atlas_overview)
    (output_root / "atlas_overview.md").write_text(
        _build_overview_markdown(
            descriptor=descriptor,
            manifest=manifest,
            atlas_rows=atlas_rows,
            target_registry_rows=target_registry_rows,
            source_snapshot=source_snapshot,
        ),
        encoding="utf-8",
    )
    _write_json(output_root / "scaffold_atlas.json", atlas_rows)
    _write_csv(
        output_root / "scaffold_atlas.csv",
        scaffold_atlas_csv_rows,
        [
            "scaffold",
            "entry_count",
            "protein_count",
            "engineered_yes_count",
            "engineered_no_count",
            "engineered_unknown_count",
            "organism_count",
            "target_linked_row_count",
            "top_targets",
            "top_interaction_classes",
            "top_organisms",
            "top_proteins",
            "source_tables",
            "representative_interactions",
        ],
    )
    _write_json(output_root / "target_registry.json", target_registry_csv_rows)
    _write_csv(
        output_root / "target_registry.csv",
        target_registry_csv_rows,
        [
            "scaffold",
            "interaction_id",
            "protein_id",
            "protein_name",
            "organism",
            "domain_id",
            "domain_name",
            "target_label",
            "target_variant_id",
            "target_concept_id",
            "target_gene_name_species",
            "target_species_name",
            "target_concept_gene_name",
            "target_concept_protein_name",
            "source",
            "chunk_id",
        ],
    )
    _write_json(output_root / "source_registry_snapshot.json", source_snapshot)

    print(json.dumps({"ok": True, "output_root": str(output_root), "scaffold_count": len(atlas_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
