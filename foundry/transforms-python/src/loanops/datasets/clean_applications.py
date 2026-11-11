"""Join applications to applicants and compute payment estimates and LTV.

Mirrors local/loanops/logic.py::clean_applications. Replace the dataset paths with the
paths of your raw datasets after uploading data/raw/*.csv to Foundry.
"""

from pyspark.sql import functions as F
from transforms.api import Input, Output, transform_df

from loanops.policy import STANDARD_APR

ROOT = "/Loan Operations/datasets"


@transform_df(
    Output(f"{ROOT}/clean/clean_applications"),
    applications=Input(f"{ROOT}/raw/applications"),
    applicants=Input(f"{ROOT}/raw/applicants"),
)
def compute(applications, applicants):
    apr = F.coalesce(*[F.when(F.col("product") == p, F.lit(r)) for p, r in STANDARD_APR.items()])
    r = apr / 12
    df = (applications.join(applicants, "applicant_id", "left")
          .withColumn("submitted_at", F.to_timestamp("submitted_at"))
          .withColumn("decided_at", F.to_timestamp("decided_at"))
          .withColumn("est_monthly_payment",
                      F.round(F.col("requested_amount") * r / (1 - F.pow(1 + r, -F.col("term_months"))), 2))
          .withColumn("ltv", F.round(F.col("requested_amount") / F.col("vehicle_value"), 3)))
    return df
