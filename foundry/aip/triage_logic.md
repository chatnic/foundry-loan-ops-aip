# AIP Logic Function: `triageLoanApplication`

**Purpose:** given one LoanApplication, produce a short file summary for the underwriter, a recommended next step grounded in the credit policy, and (if documents are needed) a ready-to-send borrower email. **It changes nothing on its own.** The underwriter reviews the output and applies it with an Action.

## Inputs
| Name | Type |
|---|---|
| `application` | Object: LoanApplication |

## Blocks

1. **Gather context (no LLM).**
   - Get properties of `application`.
   - Search around → linked `UnderwritingException` objects where `status = open`.
   - Search around → linked `Applicant` (first name only is passed to the email step).
   - Search around → linked `Document` objects.

2. **Summarize and recommend (LLM block).**
   - Model: a Foundry-provided LLM.
   - Tools available to the block: *none*. All facts are supplied in the prompt. The policy text comes from the `credit_policy` document attached as context (see `docs/policy/credit_policy.md`).
   - Output: a struct `{summary: string, recommended_action: string, rationale: string, policy_sections: string[]}`.
   - Prompt:

   ```text
   You are assisting a loan underwriter. Using ONLY the application data, open exceptions,
   documents and the credit policy provided, write:

   1. summary: three sentences or fewer describing the application and what is blocking a decision.
   2. recommended_action: exactly one of [decide, request_documents, verify_documents,
      recalculate_with_verified_income, escalate_senior_review, counteroffer_lower_amount,
      decline_or_counteroffer, route_second_approval].
      It must match the pipeline's next_action ({application.next_action}) unless the data
      clearly shows otherwise; if you disagree, say why in rationale.
   3. rationale: two sentences or fewer, citing policy section numbers.
   4. policy_sections: the section numbers you relied on.

   Never invent figures. If information is missing, say so.

   Application: {application}
   Open exceptions: {exceptions}
   Documents: {documents}
   ```

3. **Draft borrower email (LLM block, conditional).** Runs only when `recommended_action = request_documents`.
   - Inputs: applicant first name, missing/rejected document list, product.
   - Rules from policy section 7: list each item, explain why it's needed, give a 10-day deadline, **never mention credit score or internal risk ratings**.

4. **Guardrail check (no LLM).**
   - If the email text contains a 3-digit number between 300 and 850, or the words "credit score" / "risk", replace the draft with a fixed template and flag `guardrail_triggered = true`.

## Output
```json
{
  "summary": "...",
  "recommended_action": "request_documents",
  "rationale": "...",
  "policy_sections": ["2", "4"],
  "borrower_email_draft": "...",
  "guardrail_triggered": false
}
```

## Evaluation plan (AIP Evals)
Build an eval suite from 50 in-review applications. The expected `recommended_action` comes from the pipeline's deterministic `next_action`. Score:
- **Action agreement** with the policy engine (target ≥ 95%; every disagreement reviewed by hand)
- **Faithfulness:** every number in the summary must appear in the inputs (string check)
- **Email compliance:** guardrail triggers = 0, and every missing document is mentioned
