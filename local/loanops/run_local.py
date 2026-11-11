"""Run the transform logic locally on the generated CSVs and summarize the operations picture.

    python local/loanops/run_local.py --data data/raw --out reports
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logic import application_queue, clean_applications, document_checklist, underwriting_exceptions  # noqa: E402


def run(data: Path, out: Path) -> dict:
    apps = pd.read_csv(data / "applications.csv")
    applicants = pd.read_csv(data / "applicants.csv")
    docs = pd.read_csv(data / "documents.csv")
    uw = pd.read_csv(data / "underwriters.csv")
    as_of = pd.Timestamp(pd.read_csv(data / "as_of.csv")["as_of"].iloc[0])

    clean = clean_applications(apps, applicants)
    checklist = document_checklist(clean, docs)
    exc = underwriting_exceptions(clean, checklist, uw, as_of)
    queue = application_queue(clean, checklist, exc, as_of)

    open_q = queue[queue.status == "in_review"]
    workload = (open_q.groupby("assigned_underwriter_id")
                .agg(open_applications=("application_id", "size"),
                     needs_attention=("queue_status", lambda s: (s == "needs_attention").sum()),
                     sla_breached=("sla_breached", "sum"), oldest_days=("days_open", "max"))
                .join(uw.set_index("underwriter_id")[["name", "team", "daily_capacity"]]))
    workload["days_of_backlog"] = (workload.open_applications / workload.daily_capacity).round(1)

    by_type = exc.groupby(["exception_type", "severity"]).size().rename("open_exceptions").reset_index() \
        .sort_values("open_exceptions", ascending=False)
    metrics = {
        "as_of": str(as_of.date()),
        "applications": len(queue),
        "in_review": int(len(open_q)),
        "ready_to_decide": int((open_q.queue_status == "ready_to_decide").sum()),
        "needs_attention": int((open_q.queue_status == "needs_attention").sum()),
        "open_exceptions": int(len(exc)),
        "sla_breached": int(open_q.sla_breached.sum()),
        "share_needing_borrower_contact": float(open_q.next_action.isin(["request_documents"]).mean()),
        "top_exceptions": by_type.head(5).set_index("exception_type")["open_exceptions"].to_dict(),
        "median_days_to_decision": float(queue.loc[queue.status != "in_review", "days_open"].median()),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "tables").mkdir(exist_ok=True)
    by_type.to_csv(out / "tables" / "open_exceptions_by_type.csv", index=False)
    workload.reset_index().to_csv(out / "tables" / "underwriter_workload.csv", index=False)
    queue.head(200).to_csv(out / "tables" / "application_queue_sample.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    figure(by_type, open_q, out / "figures")
    print(json.dumps(metrics, indent=2, default=str))
    return metrics


def figure(by_type: pd.DataFrame, open_q: pd.DataFrame, fig_dir: Path) -> None:
    fig_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "font.size": 10})
    colors = {"high": "#c62828", "medium": "#e08a2c", "low": "#9aa5b1"}
    t = by_type.sort_values("open_exceptions")
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), gridspec_kw={"width_ratios": [1.6, 1]})
    axes[0].barh(t.exception_type.str.replace("_", " "), t.open_exceptions, color=t.severity.map(colors))
    axes[0].set_title("Open underwriting exceptions by type (color = severity)")
    axes[0].set_xlabel("Open exceptions")
    counts = open_q.queue_status.value_counts()
    axes[1].bar(["Ready to decide", "Needs attention"],
                [counts.get("ready_to_decide", 0), counts.get("needs_attention", 0)], color=["#2e7d32", "#1f4e8c"])
    axes[1].set_title("Applications in review")
    for i, v in enumerate([counts.get("ready_to_decide", 0), counts.get("needs_attention", 0)]):
        axes[1].text(i, v + 3, str(v), ha="center")
    fig.tight_layout(); fig.savefig(fig_dir / "exception_overview.png", dpi=150); plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data/raw"))
    p.add_argument("--out", type=Path, default=Path("reports"))
    a = p.parse_args()
    run(a.data, a.out)


if __name__ == "__main__":
    main()
