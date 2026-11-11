"""Per-application document checklist: missing, rejected and pending documents, verified income,
and ID expiry. Mirrors local/loanops/logic.py::document_checklist."""

from pyspark.sql import functions as F
from transforms.api import Input, Output, transform_df

from loanops.policy import REQUIRED_DOCS

ROOT = "/Loan Operations/datasets"


def _required_docs_col():
    return F.coalesce(*[F.when(F.col("product") == p, F.array(*[F.lit(d) for d in docs]))
                        for p, docs in REQUIRED_DOCS.items()])


@transform_df(
    Output(f"{ROOT}/clean/document_checklist"),
    applications=Input(f"{ROOT}/clean/clean_applications"),
    documents=Input(f"{ROOT}/raw/documents"),
)
def compute(applications, documents):
    docs = documents.withColumn("id_expiration_date", F.to_timestamp("id_expiration_date"))
    agg = docs.groupBy("application_id").agg(
        F.collect_set("document_type").alias("present"),
        F.array_sort(F.collect_set(F.when(F.col("status") == "rejected", F.col("document_type")))).alias("rejected_documents"),
        F.array_sort(F.collect_set(F.when(F.col("status") == "pending_review", F.col("document_type")))).alias("pending_documents"),
        F.first(F.when(F.col("document_type").isin("paystub", "business_tax_return"),
                       F.col("extracted_annual_income")), ignorenulls=True).alias("verified_annual_income"),
        F.min(F.when(F.col("document_type") == "government_id", F.col("id_expiration_date"))).alias("id_expires"),
    )
    df = (applications.select("application_id", "product", "submitted_at")
          .join(agg, "application_id", "left")
          .withColumn("present", F.coalesce("present", F.array().cast("array<string>")))
          .withColumn("rejected_documents", F.coalesce("rejected_documents", F.array().cast("array<string>")))
          .withColumn("pending_documents", F.coalesce("pending_documents", F.array().cast("array<string>")))
          .withColumn("missing_documents", F.array_except(_required_docs_col(), F.col("present")))
          .withColumn("id_expired", F.coalesce(F.col("id_expires") < F.col("submitted_at"), F.lit(False)))
          .withColumn("file_complete", (F.size("missing_documents") == 0) & (F.size("rejected_documents") == 0)
                      & (F.size("pending_documents") == 0)))
    return df.drop("present", "id_expires", "product", "submitted_at")
