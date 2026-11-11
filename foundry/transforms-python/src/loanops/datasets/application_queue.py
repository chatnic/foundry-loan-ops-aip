"""Application-level queue: the backing dataset for the LoanApplication object type.
Mirrors local/loanops/logic.py::application_queue."""

from pyspark.sql import Window
from pyspark.sql import functions as F
from transforms.api import Input, Output, transform_df

from loanops import policy

ROOT = "/Loan Operations/datasets"


@transform_df(
    Output(f"{ROOT}/ontology/loan_applications"),
    applications=Input(f"{ROOT}/clean/clean_applications"),
    checklist=Input(f"{ROOT}/clean/document_checklist"),
    exceptions=Input(f"{ROOT}/ontology/underwriting_exceptions"),
    as_of=Input(f"{ROOT}/raw/as_of"),
)
def compute(applications, checklist, exceptions, as_of):
    # The demo data is fixed in time, so "now" comes from the as_of dataset. In production,
    # replace it with F.current_timestamp().
    now = F.col("as_of_ts")
    rank = F.coalesce(*[F.when(F.col("severity") == s, F.lit(r)) for s, r in policy.SEVERITY_RANK.items()])
    w = Window.partitionBy("application_id").orderBy(rank.desc(), F.col("exception_type"))
    top = (exceptions.withColumn("rn", F.row_number().over(w))
           .groupBy("application_id").agg(
               F.count("*").alias("exception_count"),
               F.first(F.when(F.col("rn") == 1, F.col("severity")), ignorenulls=True).alias("highest_severity"),
               F.first(F.when(F.col("rn") == 1, F.col("exception_type")), ignorenulls=True).alias("primary_exception"),
               F.first(F.when(F.col("rn") == 1, F.col("recommended_action")), ignorenulls=True).alias("next_action")))

    in_review = F.col("status") == "in_review"
    days_open = F.when(in_review, (F.unix_timestamp(now) - F.unix_timestamp("submitted_at")) / 86400) \
        .otherwise((F.unix_timestamp("decided_at") - F.unix_timestamp("submitted_at")) / 86400)
    df = (applications.join(checklist, "application_id").join(top, "application_id", "left")
          .crossJoin(as_of.select(F.to_timestamp("as_of").alias("as_of_ts")))
          .withColumn("exception_count", F.coalesce("exception_count", F.lit(0)))
          .withColumn("days_open", F.round(days_open, 1))
          .withColumn("queue_status", F.when(~in_review, "decided")
                      .when(F.col("exception_count") == 0, "ready_to_decide").otherwise("needs_attention"))
          .withColumn("next_action", F.when(F.col("queue_status") == "ready_to_decide", "decide")
                      .otherwise(F.col("next_action")))
          .withColumn("sla_breached", in_review & (F.col("days_open") > policy.SLA_AGING_REPORT_DAYS))
          .withColumn("missing_documents", F.array_join("missing_documents", ";"))
          .withColumn("rejected_documents", F.array_join("rejected_documents", ";"))
          .withColumn("pending_documents", F.array_join("pending_documents", ";")))
    return df.drop("as_of_ts")
