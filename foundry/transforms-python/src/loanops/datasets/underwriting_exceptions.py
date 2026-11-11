"""One row per open policy exception on an in-review application. This is the backing
dataset for the UnderwritingException object type. Mirrors
local/loanops/logic.py::underwriting_exceptions."""

from functools import reduce

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from transforms.api import Input, Output, transform_df

from loanops import policy

ROOT = "/Loan Operations/datasets"


def _by_product(mapping):
    return F.coalesce(*[F.when(F.col("product") == p, F.lit(v)) for p, v in mapping.items()])


@transform_df(
    Output(f"{ROOT}/ontology/underwriting_exceptions"),
    applications=Input(f"{ROOT}/clean/clean_applications"),
    checklist=Input(f"{ROOT}/clean/document_checklist"),
    underwriters=Input(f"{ROOT}/raw/underwriters"),
)
def compute(applications, checklist, underwriters):
    uw = underwriters.select(F.col("underwriter_id").alias("assigned_underwriter_id"), "authority_limit")
    df = (applications.filter(F.col("status") == "in_review")
          .join(checklist, "application_id")
          .join(uw, "assigned_underwriter_id", "left"))
    income = F.coalesce("verified_annual_income", "stated_annual_income")
    dti = (F.col("monthly_debt_payments") + F.col("est_monthly_payment")) / (income / 12)
    gap = F.col("stated_annual_income") / F.col("verified_annual_income") - 1
    money = lambda c: F.format_number(F.col(c), 0)  # noqa: E731

    checks = {
        "missing_document": (F.size("missing_documents") > 0,
                             F.concat(F.lit("Missing: "), F.array_join("missing_documents", ", "))),
        "document_rejected": (F.size("rejected_documents") > 0,
                              F.concat(F.lit("Rejected: "), F.array_join("rejected_documents", ", "))),
        "document_pending_review": (F.size("pending_documents") > 0,
                                    F.concat(F.lit("Pending review: "), F.array_join("pending_documents", ", "))),
        "expired_id": (F.col("id_expired"), F.lit("Government ID expired before submission")),
        "income_fraud_review": (gap > policy.INCOME_DISCREPANCY_ESCALATE,
                                F.concat(F.lit("Stated $"), money("stated_annual_income"),
                                         F.lit(" vs verified $"), money("verified_annual_income"))),
        "income_discrepancy": ((gap > policy.INCOME_DISCREPANCY_NOTE) & (gap <= policy.INCOME_DISCREPANCY_ESCALATE),
                               F.concat(F.lit("Stated $"), money("stated_annual_income"),
                                        F.lit(" vs verified $"), money("verified_annual_income"))),
        "dti_above_limit": (dti > _by_product(policy.MAX_DTI),
                            F.concat(F.lit("DTI "), F.format_number(dti * 100, 0), F.lit("%"))),
        "credit_score_below_min": (F.col("credit_score") < _by_product(policy.MIN_CREDIT_SCORE),
                                   F.concat(F.lit("Credit score below product minimum"))),
        "ltv_above_limit": ((F.col("product") == "auto_loan") & (F.col("ltv") > policy.MAX_LTV_AUTO),
                            F.concat(F.lit("LTV "), F.format_number(F.col("ltv") * 100, 0), F.lit("%"))),
        "loan_to_income_above_limit": ((F.col("product") == "personal_loan")
                                       & (F.col("requested_amount") > policy.MAX_PERSONAL_LOAN_TO_INCOME * income),
                                       F.concat(F.lit("$"), money("requested_amount"), F.lit(" exceeds 50% of income"))),
        "business_tenure_below_min": ((F.col("product") == "small_business_loan")
                                      & (F.col("employment_years") < policy.MIN_BUSINESS_YEARS),
                                      F.concat(F.col("employment_years").cast("string"), F.lit(" years in operation"))),
        "above_underwriter_authority": (F.col("requested_amount") > F.col("authority_limit"),
                                        F.concat(F.lit("$"), money("requested_amount"), F.lit(" above $"),
                                                 money("authority_limit"), F.lit(" authority"))),
    }

    parts: list[DataFrame] = []
    for etype, (cond, detail) in checks.items():
        severity, section, action = policy.EXCEPTIONS[etype]
        parts.append(df.filter(F.coalesce(cond, F.lit(False))).select(
            F.concat_ws("-", "application_id", F.lit(etype)).alias("exception_id"),
            "application_id",
            F.lit(etype).alias("exception_type"),
            F.lit(severity).alias("severity"),
            F.lit(section).alias("policy_section"),
            F.lit(action).alias("recommended_action"),
            detail.alias("detail"),
            F.lit("open").alias("status"),
            F.current_timestamp().alias("created_at"),
        ))
    return reduce(DataFrame.unionByName, parts)
