import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local" / "loanops"))
sys.path.insert(0, str(ROOT / "data"))

from generate_data import generate  # noqa: E402
from logic import application_queue, clean_applications, document_checklist, policy, underwriting_exceptions  # noqa: E402


@pytest.fixture(scope="module")
def built():
    t = generate(n=800, seed=5)
    as_of = pd.Timestamp(t["as_of"]["as_of"].iloc[0])
    clean = clean_applications(t["applications"], t["applicants"])
    chk = document_checklist(clean, t["documents"])
    exc = underwriting_exceptions(clean, chk, t["underwriters"], as_of)
    q = application_queue(clean, chk, exc, as_of)
    return t, clean, chk, exc, q


def test_monthly_payment_formula():
    # $10,000 at 12% APR over 12 months is $888.49.
    assert policy.monthly_payment(10_000, 0.12, 12) == pytest.approx(888.49, abs=0.01)


def test_clean_payment_matches_policy(built):
    _, clean, *_ = built
    r = clean.iloc[0]
    expected = policy.monthly_payment(r.requested_amount, policy.STANDARD_APR[r["product"]], r.term_months)
    assert r.est_monthly_payment == pytest.approx(expected, abs=0.01)


def test_missing_documents_detected(built):
    t, clean, chk, *_ = built
    docs = t["documents"]
    for row in chk.head(200).itertuples():
        product = clean.loc[clean.application_id == row.application_id, "product"].iloc[0]
        present = set(docs.loc[docs.application_id == row.application_id, "document_type"])
        assert set(row.missing_documents) == set(policy.REQUIRED_DOCS[product]) - present


def test_exceptions_only_for_in_review(built):
    _, clean, _, exc, _ = built
    status = clean.set_index("application_id")["status"]
    assert (status.loc[exc.application_id] == "in_review").all()
    assert set(exc.exception_type) <= set(policy.EXCEPTIONS)


def test_queue_status_consistent(built):
    *_, exc, q = built
    open_q = q[q.status == "in_review"]
    with_exc = set(exc.application_id)
    assert (open_q.loc[open_q.application_id.isin(with_exc), "queue_status"] == "needs_attention").all()
    assert (open_q.loc[~open_q.application_id.isin(with_exc), "queue_status"] == "ready_to_decide").all()
    assert (q.loc[q.status != "in_review", "queue_status"] == "decided").all()


def test_primary_exception_is_most_severe(built):
    *_, exc, q = built
    rank = exc.assign(r=exc.severity.map(policy.SEVERITY_RANK)).groupby("application_id").r.max()
    top = q.set_index("application_id").loc[rank.index, "highest_severity"].map(policy.SEVERITY_RANK)
    assert (top.values == rank.values).all()


def test_foundry_transforms_parse_and_share_policy():
    files = list((ROOT / "foundry" / "transforms-python" / "src" / "loanops" / "datasets").glob("*.py"))
    assert len(files) >= 4
    for f in files:
        src = f.read_text()
        ast.parse(src)
    assert any("from loanops.policy import" in f.read_text() or "from loanops import policy" in f.read_text()
               for f in files)
