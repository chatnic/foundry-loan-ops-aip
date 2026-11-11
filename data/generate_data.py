"""Generate synthetic loan-operations data to load into Palantir Foundry.

Outputs four CSVs, each becoming a raw dataset in Foundry:

  applicants.csv      who is applying (identity, income, employment, credit attributes)
  applications.csv    loan applications (product, amount, term, status, timestamps, assigned underwriter)
  documents.csv       documents received per application (type, status, extracted values)
  underwriters.csv    the operations team (name, team, capacity, authority limit)

Realistic operational mess is built in: missing documents, stated income that doesn't match
paystubs, expired IDs, debt-to-income near policy limits, and applications aging past SLA.
These become the exceptions the Foundry workflow and the AIP agent help underwriters clear.

All people and figures are fictional.

Usage:
    python data/generate_data.py --n 5000 --seed 42 --out data/raw
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

FIRST = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Taylor", "Quinn", "Reese", "Skyler", "Drew", "Jamie",
         "Rowan", "Elliot", "Harper", "Logan", "Sasha", "Kai", "Noel", "Parker", "Emerson"]
LAST = ["Alvarez", "Brooks", "Chen", "Dawson", "Ellis", "Fischer", "Grant", "Huang", "Iverson", "Jensen",
        "Kim", "Lopez", "Mendez", "Nakamura", "Owens", "Patel", "Quintero", "Russo", "Singh", "Turner"]
STATES = ["OH", "TX", "FL", "NC", "GA", "PA", "AZ", "MI", "VA", "TN"]
PRODUCTS = {"personal_loan": (0.5, 3000, 40000, [24, 36, 48, 60]),
            "auto_loan": (0.35, 8000, 65000, [36, 48, 60, 72]),
            "small_business_loan": (0.15, 15000, 250000, [36, 60, 84])}
REQUIRED_DOCS = {"personal_loan": ["government_id", "paystub", "bank_statement"],
                 "auto_loan": ["government_id", "paystub", "vehicle_purchase_agreement"],
                 "small_business_loan": ["government_id", "business_tax_return", "bank_statement", "business_license"]}


def generate(n: int = 5000, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2026-08-01")

    uw = pd.DataFrame({
        "underwriter_id": [f"UW{i:02d}" for i in range(1, 13)],
        "name": [f"{FIRST[i]} {LAST[(i * 7) % 20]}" for i in range(12)],
        "team": ["Consumer"] * 7 + ["Small Business"] * 5,
        "daily_capacity": rng.integers(18, 30, 12),
        "authority_limit": [50000] * 4 + [100000] * 3 + [150000] * 3 + [300000] * 2,
    })

    applicant_id = [f"AP{100000 + i}" for i in range(n)]
    income = np.round(rng.lognormal(11.0, 0.45, n), -2)
    applicants = pd.DataFrame({
        "applicant_id": applicant_id,
        "full_name": [f"{FIRST[rng.integers(20)]} {LAST[rng.integers(20)]}" for _ in range(n)],
        "state": rng.choice(STATES, n),
        "stated_annual_income": income,
        "employment_years": np.round(rng.gamma(2, 3, n), 1),
        "credit_score": np.clip(rng.normal(700, 60, n), 520, 850).round().astype(int),
        "monthly_debt_payments": np.round(income / 12 * np.clip(rng.beta(2, 10, n), 0.01, 0.6), 2),
        "existing_customer": (rng.random(n) < 0.4).astype(int),
    })

    prods = list(PRODUCTS)
    product = rng.choice(prods, n, p=[PRODUCTS[p][0] for p in prods])
    amount = np.array([np.round(rng.uniform(PRODUCTS[p][1], PRODUCTS[p][2]), -2) for p in product])
    # Personal loans are sized to the borrower's income, as they are in practice.
    personal = product == "personal_loan"
    amount[personal] = np.clip(np.round(income[personal] * rng.uniform(0.04, 0.45, personal.sum()), -2), 2000, 40000)
    term = np.array([rng.choice(PRODUCTS[p][3]) for p in product])
    submitted = start + pd.to_timedelta(rng.uniform(0, 75, n), unit="D")
    apps = pd.DataFrame({
        "application_id": [f"LA{500000 + i}" for i in range(n)],
        "applicant_id": applicant_id,
        "product": product,
        "requested_amount": amount,
        "term_months": term,
        "channel": rng.choice(["branch", "online", "broker"], n, p=[0.3, 0.55, 0.15]),
        "submitted_at": submitted.round("min"),
        "vehicle_value": np.where(product == "auto_loan", np.round(amount * rng.uniform(0.8, 1.35, n), -2), np.nan),
    })
    team = np.where(product == "small_business_loan", "Small Business", "Consumer")
    apps["assigned_underwriter_id"] = [rng.choice(uw.loc[uw.team == t, "underwriter_id"]) for t in team]
    as_of = start + pd.Timedelta(days=76)
    # Older applications are more likely to be decided already.
    age_days = (as_of - apps["submitted_at"]).dt.total_seconds() / 86400
    decided = rng.random(n) < np.clip(age_days / 18, 0, 0.993)
    apps["status"] = np.where(decided, rng.choice(["approved", "declined", "withdrawn"], n, p=[0.68, 0.24, 0.08]),
                              "in_review")
    decided_at = (apps["submitted_at"] + pd.to_timedelta(np.clip(rng.gamma(2, 2.5, n), 0.2, age_days), unit="D")).dt.round("min")
    apps["decided_at"] = decided_at.where(decided)

    # Documents: each required doc is usually present; some missing, expired or inconsistent.
    doc_rows = []
    for a, ap in zip(apps.itertuples(), applicants.itertuples()):
        for d in REQUIRED_DOCS[a.product]:
            if rng.random() < 0.07:
                continue                                         # missing document
            status = rng.choice(["verified", "pending_review", "rejected"], p=[0.8, 0.15, 0.05])
            extracted_income = np.nan
            expiry = pd.NaT
            if d == "paystub":
                # Most paystubs support stated income; some show materially less.
                factor = rng.normal(1.0, 0.04) if rng.random() < 0.88 else rng.uniform(0.6, 0.85)
                extracted_income = round(ap.stated_annual_income * factor, -2)
            if d == "business_tax_return":
                extracted_income = round(ap.stated_annual_income * rng.uniform(0.7, 1.2), -2)
            if d == "government_id":
                expiry = a.submitted_at + pd.Timedelta(days=int(rng.normal(900, 700)))
            doc_rows.append({"document_id": f"DOC{len(doc_rows) + 1:07d}", "application_id": a.application_id,
                             "document_type": d, "status": status,
                             "received_at": (a.submitted_at + pd.Timedelta(hours=float(rng.uniform(0, 72)))).round("min"),
                             "extracted_annual_income": extracted_income, "id_expiration_date": expiry})
    docs = pd.DataFrame(doc_rows)
    return {"applicants": applicants, "applications": apps, "documents": docs, "underwriters": uw,
            "as_of": pd.DataFrame({"as_of": [as_of]})}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", type=Path, default=Path("data/raw"))
    a = p.parse_args()
    tables = generate(a.n, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(a.out / f"{name}.csv", index=False)
    print({k: len(v) for k, v in tables.items()})


if __name__ == "__main__":
    main()
