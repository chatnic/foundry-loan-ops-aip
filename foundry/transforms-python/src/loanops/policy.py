"""Credit policy thresholds (docs/policy/credit_policy.md) as code.

Both the Foundry transforms (PySpark) and the local mirror (pandas) import this module,
so the policy lives in exactly one place.
"""

from __future__ import annotations

MIN_CREDIT_SCORE = {"personal_loan": 640, "auto_loan": 620, "small_business_loan": 660}
MAX_DTI = {"personal_loan": 0.43, "auto_loan": 0.45, "small_business_loan": 0.45}
STANDARD_APR = {"personal_loan": 0.115, "auto_loan": 0.079, "small_business_loan": 0.095}
MAX_LTV_AUTO = 1.20
MAX_PERSONAL_LOAN_TO_INCOME = 0.50
MIN_BUSINESS_YEARS = 2.0
INCOME_DISCREPANCY_NOTE = 0.10      # stated exceeds verified by >10%: use verified income
INCOME_DISCREPANCY_ESCALATE = 0.25  # >25%: senior fraud review
SLA_FIRST_TOUCH_DAYS = 1
SLA_DECISION_DAYS = 5
SLA_AGING_REPORT_DAYS = 10

REQUIRED_DOCS = {
    "personal_loan": ["government_id", "paystub", "bank_statement"],
    "auto_loan": ["government_id", "paystub", "vehicle_purchase_agreement"],
    "small_business_loan": ["government_id", "business_tax_return", "bank_statement", "business_license"],
}

# Exception catalog: type -> (severity, policy section, next action)
EXCEPTIONS = {
    "missing_document":        ("medium", "2", "request_documents"),
    "document_rejected":       ("medium", "2", "request_documents"),
    "document_pending_review": ("low",    "2", "verify_documents"),
    "expired_id":              ("high",   "4", "request_documents"),
    "income_discrepancy":      ("medium", "3", "recalculate_with_verified_income"),
    "income_fraud_review":     ("high",   "3", "escalate_senior_review"),
    "dti_above_limit":         ("high",   "1", "decline_or_counteroffer"),
    "credit_score_below_min":  ("high",   "1", "decline_or_counteroffer"),
    "ltv_above_limit":         ("medium", "1", "counteroffer_lower_amount"),
    "loan_to_income_above_limit": ("medium", "1", "counteroffer_lower_amount"),
    "business_tenure_below_min": ("high", "1", "decline_or_counteroffer"),
    "above_underwriter_authority": ("low", "5", "route_second_approval"),
}
SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def monthly_payment(principal: float, apr: float, months: int) -> float:
    """Standard amortizing payment."""
    r = apr / 12
    return principal * r / (1 - (1 + r) ** -months)
