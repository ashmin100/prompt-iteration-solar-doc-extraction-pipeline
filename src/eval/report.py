"""Render a HarnessReport as a markdown comparison report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.eval.harness import HarnessReport
from src.eval.metrics import AggregateMetrics


# --------------------------------------------------------------------------- #
def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _ms(x: float) -> str:
    return f"{x:.0f} ms"


def _row(name: str, m: AggregateMetrics) -> str:
    return (
        f"| {name} | {m.n_documents} | "
        f"{_pct(m.schema_validity_rate)} | "
        f"{_pct(m.field_accuracy)} | "
        f"{m.f1:.3f} | "
        f"{_pct(m.hallucination_rate)} | "
        f"{_pct(m.omission_rate)} | "
        f"{_ms(m.latency_p50_ms)} | "
        f"{_ms(m.latency_p95_ms)} |"
    )


_HEADER = (
    "| Version | N | Schema valid | Field acc | F1 | "
    "Hallucination | Omission | Latency p50 | Latency p95 |"
)
_DIVIDER = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"


# --------------------------------------------------------------------------- #
def render(report: HarnessReport) -> str:
    """Render the full markdown report."""
    if not report.runs:
        return "# Eval report\n\n_No runs._\n"

    first = report.runs[0]
    lines: list[str] = []

    lines.append(f"# Eval report — {first.backend} / `{first.model}`")
    lines.append("")
    lines.append(f"_Generated {datetime.now().isoformat(timespec='seconds')}_")
    lines.append("")
    tier_str = ", ".join(f"{k}: {v}" for k, v in sorted(report.tier_counts.items()))
    lines.append(f"**Dataset:** {report.dataset_size} documents ({tier_str}).")
    lines.append(f"**Parser mode:** `{report.parser_mode}`.")
    lines.append("")

    # ---- Overall ---------------------------------------------------------
    lines.append("## Overall")
    lines.append("")
    lines.append(_HEADER)
    lines.append(_DIVIDER)
    for r in report.runs:
        lines.append(_row(r.prompt_version, r.overall))
    lines.append("")

    # ---- By tier ---------------------------------------------------------
    tiers = sorted({t for r in report.runs for t in r.by_tier.keys()})
    for tier in tiers:
        lines.append(f"## {tier.capitalize()} tier")
        lines.append("")
        lines.append(_HEADER)
        lines.append(_DIVIDER)
        for r in report.runs:
            if tier in r.by_tier:
                lines.append(_row(r.prompt_version, r.by_tier[tier]))
        lines.append("")

    # ---- Per-document failure summary -----------------------------------
    lines.append("## Per-document failures")
    lines.append("")
    lines.append("Documents where any version failed schema validation, parse, or had wrong fields.")
    lines.append("")
    lines.append("| Document | Version | Schema | JSON parse | Wrong | Omitted | Hallucinated |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in report.runs:
        for d in r.overall.per_doc:
            if d.tally.wrong + d.tally.omitted + d.tally.hallucinated == 0 and d.schema_valid:
                continue
            schema_cell = "ok" if d.schema_valid else "FAIL"
            parse_cell = "ok" if d.json_parse_error is None else d.json_parse_error[:40]
            lines.append(
                f"| `{d.document_id}` | {d.prompt_version} | {schema_cell} | {parse_cell} | "
                f"{d.tally.wrong} | {d.tally.omitted} | {d.tally.hallucinated} |"
            )
    lines.append("")

    # ---- Notes -----------------------------------------------------------
    lines.append("## Notes")
    lines.append("")
    lines.append("- Schema validity = fraction of predictions that parse + Pydantic-validate.")
    lines.append("- Field accuracy / F1 ignore `raw_notes` (free-form essay).")
    lines.append("- Money values normalized to `Decimal`; dates normalized to ISO 8601 before comparison.")
    lines.append("- Strings (names, addresses) compared with fuzzy ratio ≥ 0.85.")
    lines.append("- List fields (coverages, beneficiaries) matched greedily by their key field.")
    lines.append("")

    return "\n".join(lines)


def write_report(report: HarnessReport, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(report), encoding="utf-8")
    return out_path
