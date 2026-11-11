# Ontology Design: Loan Operations

The Ontology turns the transformed datasets into the **business objects underwriters actually work with**, linked together and editable only through governed Actions.

```
 Underwriter ──(assigned to)──< LoanApplication >──(submitted by)── Applicant
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
               UnderwritingException          Document
```

## Object types

| Object type | Backing dataset | Primary key | Title |
|---|---|---|---|
| **LoanApplication** | `ontology/loan_applications` | `application_id` | `application_id` + applicant name |
| **UnderwritingException** | `ontology/underwriting_exceptions` | `exception_id` | `exception_type` |
| **Applicant** | `raw/applicants` | `applicant_id` | `full_name` |
| **Document** | `raw/documents` | `document_id` | `document_type` |
| **Underwriter** | `raw/underwriters` | `underwriter_id` | `name` |

### LoanApplication: key properties
| Property | Type | Notes |
|---|---|---|
| `product`, `requested_amount`, `term_months`, `channel` | string / double / integer / string | |
| `status` | string | `in_review`, `approved`, `declined`, `withdrawn` |
| `queue_status` | string | `ready_to_decide`, `needs_attention`, `decided`: drives the Workshop inbox |
| `primary_exception`, `highest_severity`, `exception_count` | string / string / integer | Most severe open exception |
| `next_action` | string | Recommended next step from the policy engine |
| `days_open`, `sla_breached` | double / boolean | SLA tracking |
| `missing_documents`, `pending_documents`, `rejected_documents` | string (`;`-separated) | |
| `est_monthly_payment`, `ltv`, `verified_annual_income`, `file_complete` | double / double / double / boolean | |
| `assigned_underwriter_id` | string | Foreign key → Underwriter |
| `decision_notes` | string | **Editable** through Actions only |

### UnderwritingException: key properties
`exception_type`, `severity` (high/medium/low), `policy_section`, `recommended_action`, `detail`, `status` (open/resolved/waived), `resolution_note` *(editable)*, `resolved_by` *(editable)*.

## Link types

| Link | Cardinality | Join |
|---|---|---|
| LoanApplication → Applicant | many-to-one | `applicant_id` |
| LoanApplication → UnderwritingException | one-to-many | `application_id` |
| LoanApplication → Document | one-to-many | `application_id` |
| LoanApplication → Underwriter | many-to-one | `assigned_underwriter_id` = `underwriter_id` |

## Action types

Every write goes through an Action, which provides validation, permissions and a full audit trail. These are also the **only** tools the AIP agent is allowed to use for changes, and each one asks the human to confirm.

| Action | Parameters | Edits | Submission criteria |
|---|---|---|---|
| **Request documents** | application, documents (multi-select), message to borrower | `queue_status` → `needs_attention`, appends to `decision_notes` | At least one document selected |
| **Resolve exception** | exception, resolution note | exception `status` → `resolved`, `resolution_note`, `resolved_by` = current user | Note ≥ 20 characters |
| **Waive exception** | exception, justification | exception `status` → `waived` | User is in the *Senior Underwriters* group; severity ≠ high unless user authority ≥ requested amount |
| **Approve application** | application, notes | `status` → `approved` | No open high-severity exceptions **and** requested amount ≤ current user's authority limit |
| **Decline application** | application, reason (picklist), notes | `status` → `declined` | Reason required (needed for adverse action notices) |
| **Reassign application** | application, new underwriter | `assigned_underwriter_id` | New underwriter on the same team |
| **Escalate to senior review** | application, reason | adds note, reassigns to an underwriter with authority ≥ amount | — |

## Why the model looks like this
- **Exceptions are objects, not columns.** Each one can be resolved, waived or audited individually, and the AIP agent can reason about them one at a time.
- **Approvals are gated in the Action, not the UI.** Neither the agent nor a hurried user can approve a file with an open high-severity exception or above their authority.
- **`next_action` is computed in the pipeline** (deterministic policy), while **AIP drafts the work**: the borrower email and the file summary. Rules decide; the model writes.
