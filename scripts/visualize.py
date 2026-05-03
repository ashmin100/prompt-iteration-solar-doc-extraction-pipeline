"""
Visualize eval results from results/eval_v1_v2_v3.json.

Usage:
    python scripts/visualize.py                          # default path
    python scripts/visualize.py results/my_eval.json    # custom path
    python scripts/visualize.py --run                   # re-run eval first, then plot
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — save to file
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# --------------------------------------------------------------------------- #
VERSIONS = ["v1", "v2", "v3"]
VERSION_COLORS = {"v1": "#5B8DB8", "v2": "#F5A623", "v3": "#7ED321"}
TIER_COLORS   = {"synthetic": "#5B8DB8", "blank": "#F5A623", "filled": "#7ED321"}


def _load(json_path: Path) -> dict:
    return json.loads(json_path.read_text())


def _runs_by_version(data: dict) -> dict[str, dict]:
    return {r["prompt_version"]: r for r in data["runs"]}


# --------------------------------------------------------------------------- #
#  Console table                                                              #
# --------------------------------------------------------------------------- #
def print_table(data: dict) -> None:
    runs = data["runs"]
    col_w = [10, 8, 14, 11, 7, 13, 10, 13, 13]
    headers = ["Version", "N docs", "Schema valid", "Field acc", "F1",
               "Halluc rate", "Omit rate", "Latency p50", "Latency p95"]

    def _row(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, col_w))

    sep = "  ".join("-" * w for w in col_w)
    print()
    print("  Overall results")
    print("  " + sep)
    print("  " + _row(headers))
    print("  " + sep)
    for r in runs:
        m = r["overall"]
        print("  " + _row([
            r["prompt_version"],
            m["n_documents"],
            f"{m['schema_validity_rate']:.1%}",
            f"{m['field_accuracy']:.1%}",
            f"{m['f1']:.3f}",
            f"{m['hallucination_rate']:.1%}",
            f"{m['omission_rate']:.1%}",
            f"{m['latency_p50_ms']:.0f} ms",
            f"{m['latency_p95_ms']:.0f} ms",
        ]))
    print("  " + sep)

    tiers = sorted({t for r in runs for t in r.get("by_tier", {})})
    for tier in tiers:
        print()
        print(f"  {tier.capitalize()} tier")
        print("  " + sep)
        print("  " + _row(headers))
        print("  " + sep)
        for r in runs:
            m = r.get("by_tier", {}).get(tier)
            if m is None:
                continue
            print("  " + _row([
                r["prompt_version"],
                m["n_documents"],
                f"{m['schema_validity_rate']:.1%}",
                f"{m['field_accuracy']:.1%}",
                f"{m['f1']:.3f}",
                f"{m['hallucination_rate']:.1%}",
                f"{m['omission_rate']:.1%}",
                f"{m['latency_p50_ms']:.0f} ms",
                f"{m['latency_p95_ms']:.0f} ms",
            ]))
        print("  " + sep)
    print()


# --------------------------------------------------------------------------- #
#  Chart helpers                                                              #
# --------------------------------------------------------------------------- #
def _bar_group(ax, versions, values_per_metric, metric_labels, title, ylabel,
               ymax=1.0, pct=True):
    x = np.arange(len(versions))
    n = len(metric_labels)
    width = 0.7 / n
    offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

    for i, (label, values) in enumerate(zip(metric_labels, values_per_metric)):
        bars = ax.bar(x + offsets[i], values, width, label=label, alpha=0.88)
        for bar, val in zip(bars, values):
            fmt = f"{val:.1%}" if pct else f"{val:.0f}"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.005 * ymax,
                fmt,
                ha="center", va="bottom", fontsize=7.5
            )

    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([f"Prompt {v}" for v in versions], fontsize=9)
    ax.set_ylim(0, ymax)
    ax.legend(fontsize=8, loc="upper left")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda y, _: f"{y:.0%}") if pct else plt.FuncFormatter(lambda y, _: f"{y:.0f}")
    )
    ax.grid(axis="y", alpha=0.25)


# --------------------------------------------------------------------------- #
#  Main chart                                                                 #
# --------------------------------------------------------------------------- #
def make_charts(data: dict, out_path: Path) -> None:
    runs_by_v = _runs_by_version(data)
    versions = [v for v in VERSIONS if v in runs_by_v]
    tiers = sorted({t for r in data["runs"] for t in r.get("by_tier", {})})

    fig = plt.figure(figsize=(16, 12))
    fig.patch.set_facecolor("#FAFAFA")

    gs = fig.add_gridspec(3, 2, hspace=0.55, wspace=0.38,
                          left=0.07, right=0.97, top=0.92, bottom=0.06)

    model = data["runs"][0]["model"] if data["runs"] else "unknown"
    fig.suptitle(
        f"Extraction Pipeline — Prompt Version Comparison\n"
        f"Model: {model}  |  Dataset: {data['dataset_size']} docs  |  "
        f"Parser: {data['parser_mode']}",
        fontsize=12, fontweight="bold", y=0.97
    )

    # ── Chart 1: Accuracy metrics (F1 / field acc / schema valid) ──────────
    ax1 = fig.add_subplot(gs[0, 0])
    _bar_group(
        ax1, versions,
        [
            [runs_by_v[v]["overall"]["f1"] for v in versions],
            [runs_by_v[v]["overall"]["field_accuracy"] for v in versions],
            [runs_by_v[v]["overall"]["schema_validity_rate"] for v in versions],
        ],
        ["F1", "Field accuracy", "Schema valid"],
        "Accuracy metrics (overall)", "Rate", ymax=1.08,
    )

    # ── Chart 2: Error rates ────────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    _bar_group(
        ax2, versions,
        [
            [runs_by_v[v]["overall"]["hallucination_rate"] for v in versions],
            [runs_by_v[v]["overall"]["omission_rate"] for v in versions],
        ],
        ["Hallucination", "Omission"],
        "Error rates (overall)", "Rate", ymax=1.08,
    )

    # ── Chart 3: F1 by tier ─────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    if tiers:
        tier_f1 = [
            [runs_by_v[v]["by_tier"].get(t, {}).get("f1", 0.0) for v in versions]
            for t in tiers
        ]
        _bar_group(ax3, versions, tier_f1, tiers,
                   "F1 by dataset tier", "F1", ymax=1.08)
    else:
        ax3.set_title("F1 by tier (no tiers found)")
        ax3.axis("off")

    # ── Chart 4: Hallucination / omission by tier ───────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    if tiers:
        tier_halluc = [
            [runs_by_v[v]["by_tier"].get(t, {}).get("hallucination_rate", 0.0) for v in versions]
            for t in tiers
        ]
        _bar_group(ax4, versions, tier_halluc, [f"{t} halluc" for t in tiers],
                   "Hallucination rate by tier", "Rate", ymax=1.08)
    else:
        ax4.axis("off")

    # ── Chart 5: Latency (p50 / p95) ───────────────────────────────────────
    ax5 = fig.add_subplot(gs[2, 0])
    _bar_group(
        ax5, versions,
        [
            [runs_by_v[v]["overall"]["latency_p50_ms"] for v in versions],
            [runs_by_v[v]["overall"]["latency_p95_ms"] for v in versions],
        ],
        ["p50", "p95"],
        "LLM latency (ms)", "Milliseconds",
        ymax=max(runs_by_v[v]["overall"]["latency_p95_ms"] for v in versions) * 1.25,
        pct=False,
    )

    # ── Chart 6: Radar / spider chart — overall shape ───────────────────────
    ax6 = fig.add_subplot(gs[2, 1], polar=True)
    _radar(ax6, versions, runs_by_v)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  Chart saved → {out_path}")


def _radar(ax, versions, runs_by_v):
    metrics = ["F1", "Schema\nvalid", "Field\nacc", "1−Halluc", "1−Omit"]
    n = len(metrics)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]  # close polygon

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_thetagrids(np.degrees(angles[:-1]), metrics, fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=6.5, color="grey")
    ax.grid(color="grey", alpha=0.3)
    ax.spines["polar"].set_color("lightgrey")
    ax.set_title("Shape of performance", fontsize=10, fontweight="bold", pad=14)

    for v in versions:
        m = runs_by_v[v]["overall"]
        vals = [
            m["f1"],
            m["schema_validity_rate"],
            m["field_accuracy"],
            max(0.0, 1 - m["hallucination_rate"]),
            max(0.0, 1 - m["omission_rate"]),
        ]
        vals += vals[:1]
        color = VERSION_COLORS.get(v, "#888888")
        ax.plot(angles, vals, "o-", linewidth=2, color=color, label=f"Prompt {v}", markersize=4)
        ax.fill(angles, vals, alpha=0.10, color=color)

    ax.legend(loc="upper right", bbox_to_anchor=(1.32, 1.12), fontsize=8)


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    # Handle --run flag
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    rerun = "--run" in sys.argv

    if rerun:
        print("Running evaluation first …")
        import os
        from dotenv import load_dotenv
        load_dotenv()
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from src.eval.harness import run_evaluation
        from src.eval.report import write_report
        report = run_evaluation()
        write_report(report, Path("results/eval_v1_v2_v3.md"))
        print("Eval done.")

    json_path = Path(args[0]) if args else Path("results/eval_v1_v2_v3.json")

    if not json_path.exists():
        print(f"Result file not found: {json_path}")
        print("Run the eval first:  python -m src.cli evaluate")
        print("Then re-run this:    python scripts/visualize.py")
        sys.exit(1)

    data = _load(json_path)
    print_table(data)

    chart_path = json_path.with_name(json_path.stem + "_charts.png")
    make_charts(data, chart_path)
