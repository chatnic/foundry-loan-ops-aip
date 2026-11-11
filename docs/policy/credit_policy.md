# Consumer & Small Business Lending: Credit Policy (Fictional)

*Fictional policy written for this demonstration project. It is the knowledge source the AIP agent retrieves from, and the thresholds below are implemented in the `underwriting_exceptions` transform.*

## 1. Eligibility thresholds

| Product | Minimum credit score | Maximum DTI | Other |
|---|---|---|---|
| Personal loan | 640 | 43% | Loan amount ≤ 50% of verified annual income |
| Auto loan | 620 | 45% | Loan-to-value (LTV) ≤ 120% of vehicle value |
| Small business loan | 660 | 45% | At least 2 years in operation; business license on file |

**Debt-to-income (DTI)** = (existing monthly debt payments + new estimated monthly payment) ÷ verified gross monthly income. Estimate the new payment with the product's standard rate (personal 11.5%, auto 7.9%, small business 9.5% APR).

## 2. Required documents

- **Personal loan:** government ID, most recent paystub, last 2 months of bank statements
- **Auto loan:** government ID, most recent paystub, vehicle purchase agreement
- **Small business loan:** government ID, most recent business tax return, last 3 months of business bank statements, business license

A file is **complete** only when every required document is received and verified.

## 3. Income verification

Verified income comes from the paystub (annualized) or business tax return. If stated income exceeds verified income by **more than 10%**, underwriting must use verified income and note the discrepancy. If it exceeds it by **more than 25%**, escalate to a senior underwriter for a fraud review.

## 4. Identity

A government ID must be unexpired on the application date. An expired ID requires a new ID before any decision.

## 5. Decision authority

Underwriters may approve loans up to their authority limit. Amounts above it require a second approval from an underwriter with sufficient authority.

## 6. Service levels

- First underwriter touch within **1 business day** of submission.
- Decision within **5 business days** of a complete file.
- Applications open more than **10 days** are reported to the operations manager daily.

## 7. Borrower communication

Requests for documents must list each missing item, explain why it's needed, and give a deadline of 10 calendar days. Never include credit score values or internal risk ratings in borrower communications.
