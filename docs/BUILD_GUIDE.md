# Build Guide: Recreate This in Your Foundry Developer Tier

About 3–4 hours end to end. Menu names can vary slightly between Foundry versions.

## 0. Get an environment
Sign up for the free **AIP Developer Tier** at [build.palantir.com](https://build.palantir.com). Create a project folder named **Loan Operations**.

## 1. Load raw data
1. Locally: `python data/generate_data.py --out data/raw`
2. In Foundry, upload each CSV (`applicants`, `applications`, `documents`, `underwriters`, `as_of`) into `Loan Operations/datasets/raw/`. Use the upload dialog to create one dataset per file, and check that the schema types are inferred correctly (timestamps, doubles).

## 2. Transforms (Code Repositories)
1. Create a **Python transforms** Code Repository in the project.
2. Copy `foundry/transforms-python/src/loanops/` into the repository's `src/` folder. Update the `ROOT` path at the top of each dataset file if your folder path differs, and point the repository's pipeline entry at `loanops/pipeline.py`.
3. Commit, then build in this order: `clean_applications` → `document_checklist` → `underwriting_exceptions` → `loan_applications`.
4. **Check the results against the local run:** row counts and the exception counts by type should match `reports/tables/open_exceptions_by_type.csv` (the policy constants are shared through `loanops/policy.py`).
5. Optional: set up a **schedule** in Data Lineage so the pipeline rebuilds when raw data updates.

## 3. Ontology
Follow `foundry/ontology/ontology.md` in **Ontology Manager**:
1. Create the five object types with their backing datasets and primary keys.
2. Create the four link types.
3. Create the Actions with the parameters and submission criteria listed. Test each one in the Action preview.

## 4. AIP Logic
In **AIP Logic**, create `triageLoanApplication` following `foundry/aip/triage_logic.md`. Test it on 5–10 applications with different `primary_exception` values. Then build the eval suite described in the doc.

## 5. AIP Agent
In **AIP Agent Studio**, create the *Underwriting Copilot* following `foundry/aip/agent.md`. Upload `docs/policy/credit_policy.md` as context. Run the five test conversations, and make sure the agent refuses to approve.

## 6. Workshop
Build the three pages in `foundry/workshop/app_design.md`.

## 7. Capture it for the portfolio
- Screenshots: lineage graph, Ontology graph, the queue page with the agent panel open, the manager overview.
- A 2–3 minute screen recording: pick the top SLA-breached file → ask the Copilot to summarize → draft the document request → confirm the Action → watch the queue update.
- Save screenshots to `docs/screenshots/` and add them to the README.
