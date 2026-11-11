"""Pandas mirror of the Foundry transforms, used to develop and test the logic locally.

Each function corresponds one-to-one to a transform in
foundry/transforms-python/src/loanops/datasets/. Policy constants come from the shared
loanops/policy.py so the two implementations can't drift apart on thresholds.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "foundry" / "transforms-python" / "src"))
from loanops import policy  # noqa: E402


def clean_applications(apps: pd.DataFrame, applicants: pd.DataFrame) -> pd.DataFrame:
    df = apps.merge(applicants, on="applicant_id", how="left")
    df["submitted_at"] = pd.to_datetime(df["submitted_at"])
    df["decided_at"] = pd.to_datetime(df["decided_at"])
    apr = df["product"].map(policy.STANDARD_APR)
    r = apr / 12
    df["est_monthly_payment"] = (df["requested_amount"] * r / (1 - (1 + r) ** (-df["term_months"]))).round(2)
    df["ltv"] = (df["requested_amount"] / df["vehicle_value"]).round(3)
    return df


def document_checklist(apps: pd.DataFrame, docs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    by_app = {k: g for k, g in docs.groupby("application_id")}
    for a in apps.itertuples():
        g = by_app.get(a.application_id, docs.iloc[0:0])
        required = policy.REQUIRED_DOCS[a.product]
        present = set(g["document_type"])
        missing = [d for d in required if d not in present]
        rejected = sorted(set(g.loc[g.status == "rejected", "document_type"]))
        pending = sorted(set(g.loc[g.status == "pending_review", "document_type"]))
        inc = g.loc[g.document_type.isin(["paystub", "business_tax_return"]), "extracted_annual_income"].dropna()
        ids = pd.to_datetime(g.loc[g.document_type == "government_id", "id_expiration_date"]).dropna()
        rows.append({
            "application_id": a.application_id,
            "missing_documents": missing, "rejected_documents": rejected, "pending_documents": pending,
            "verified_annual_income": float(inc.iloc[0]) if len(inc) else np.nan,
            "id_expired": bool(len(ids) and (ids.min() < pd.Timestamp(a.submitted_at))),
            "file_complete": not missing and not rejected and not pending,
        })
    return pd.DataFrame(rows)


def underwriting_exceptions(clean: pd.DataFrame, checklist: pd.DataFrame, underwriters: pd.DataFrame,
                            as_of: pd.Timestamp) -> pd.DataFrame:
    df = clean.merge(checklist, on="application_id").merge(
        underwriters[["underwriter_id", "authority_limit"]], left_on="assigned_underwriter_id",
        right_on="underwriter_id", how="left")
    df = df[df["status"] == "in_review"]
    income = df["verified_annual_income"].fillna(df["stated_annual_income"])
    dti = (df["monthly_debt_payments"] + df["est_monthly_payment"]) / (income / 12)
    gap = df["stated_annual_income"] / df["verified_annual_income"] - 1

    checks = {
        "missing_document": df["missing_documents"].str.len() > 0,
        "document_rejected": df["rejected_documents"].str.len() > 0,
        "document_pending_review": df["pending_documents"].str.len() > 0,
        "expired_id": df["id_expired"],
        "income_fraud_review": gap > policy.INCOME_DISCREPANCY_ESCALATE,
        "income_discrepancy": (gap > policy.INCOME_DISCREPANCY_NOTE) & (gap <= policy.INCOME_DISCREPANCY_ESCALATE),
        "dti_above_limit": dti > df["product"].map(policy.MAX_DTI),
        "credit_score_below_min": df["credit_score"] < df["product"].map(policy.MIN_CREDIT_SCORE),
        "ltv_above_limit": (df["product"] == "auto_loan") & (df["ltv"] > policy.MAX_LTV_AUTO),
        "loan_to_income_above_limit": (df["product"] == "personal_loan")
        & (df["requested_amount"] > policy.MAX_PERSONAL_LOAN_TO_INCOME * income),
        "business_tenure_below_min": (df["product"] == "small_business_loan")
        & (df["employment_years"] < policy.MIN_BUSINESS_YEARS),
        "above_underwriter_authority": df["requested_amount"] > df["authority_limit"],
    }
    detail = {
        "missing_document": lambda r: "Missing: " + ", ".join(r.missing_documents),
        "document_rejected": lambda r: "Rejected: " + ", ".join(r.rejected_documents),
        "document_pending_review": lambda r: "Pending review: " + ", ".join(r.pending_documents),
        "expired_id": lambda r: "Government ID expired before submission",
        "income_fraud_review": lambda r: f"Stated ${r.stated_annual_income:,.0f} vs verified ${r.verified_annual_income:,.0f}",
        "income_discrepancy": lambda r: f"Stated ${r.stated_annual_income:,.0f} vs verified ${r.verified_annual_income:,.0f}",
        "dti_above_limit": lambda r: f"DTI {r._dti:.0%} vs limit {policy.MAX_DTI[r['product']]:.0%}",
        "credit_score_below_min": lambda r: f"Below {policy.MIN_CREDIT_SCORE[r['product']]} minimum",
        "ltv_above_limit": lambda r: f"LTV {r.ltv:.0%} vs limit {policy.MAX_LTV_AUTO:.0%}",
        "loan_to_income_above_limit": lambda r: f"${r.requested_amount:,.0f} exceeds 50% of income",
        "business_tenure_below_min": lambda r: f"{r.employment_years:.1f} years in operation",
        "above_underwriter_authority": lambda r: f"${r.requested_amount:,.0f} above ${r.authority_limit:,.0f} authority",
    }
    df = df.assign(_dti=dti)
    rows = []
    for etype, mask in checks.items():
        sev, section, action = policy.EXCEPTIONS[etype]
        for _, r in df[mask.fillna(False)].iterrows():
            rows.append({"exception_id": f"{r.application_id}-{etype}", "application_id": r.application_id,
                         "exception_type": etype, "severity": sev, "policy_section": section,
                         "recommended_action": action, "detail": detail[etype](r), "status": "open",
                         "created_at": as_of})
    return pd.DataFrame(rows)


def application_queue(clean: pd.DataFrame, checklist: pd.DataFrame, exceptions: pd.DataFrame,
                      as_of: pd.Timestamp) -> pd.DataFrame:
    """Backing dataset for the LoanApplication object type."""
    q = clean.merge(checklist, on="application_id")
    q["days_open"] = np.where(q["status"] == "in_review", (as_of - q["submitted_at"]).dt.total_seconds() / 86400,
                              (q["decided_at"] - q["submitted_at"]).dt.total_seconds() / 86400).round(1)
    if len(exceptions):
        ex = exceptions.assign(rank=exceptions["severity"].map(policy.SEVERITY_RANK))
        agg = ex.sort_values("rank", ascending=False).groupby("application_id").agg(
            exception_count=("exception_type", "size"), highest_severity=("severity", "first"),
            primary_exception=("exception_type", "first"), next_action=("recommended_action", "first"))
        q = q.merge(agg, on="application_id", how="left")
    q["exception_count"] = q["exception_count"].fillna(0).astype(int)
    in_review = q["status"] == "in_review"
    q["queue_status"] = np.select(
        [~in_review, q["exception_count"] == 0],
        ["decided", "ready_to_decide"], default="needs_attention")
    q["next_action"] = np.where(q["queue_status"] == "ready_to_decide", "decide", q["next_action"])
    q["sla_breached"] = in_review & (q["days_open"] > policy.SLA_AGING_REPORT_DAYS)
    q["missing_documents"] = q["missing_documents"].apply(lambda x: ";".join(x))
    for c in ("rejected_documents", "pending_documents"):
        q[c] = q[c].apply(lambda x: ";".join(x))
    return q
