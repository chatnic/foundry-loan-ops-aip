# Workshop App: "Loan Ops Workbench"

## Page 1: My Queue (underwriter home)
| Area | Widget | Configuration |
|---|---|---|
| Header | Metric cards | My open applications · Needs attention · SLA breached · Ready to decide |
| Left | Object table: LoanApplication | Filter: `assigned_underwriter_id = current user` and `status = in_review`. Columns: application_id, product, requested_amount, queue_status, primary_exception, highest_severity, days_open, sla_breached. Default sort: sla_breached ↓, highest_severity ↓, days_open ↓. Conditional formatting: red row when `sla_breached` |
| Right (on selection) | Object view: LoanApplication | Properties card · linked UnderwritingException list (with *Resolve* / *Waive* buttons) · linked Document list |
| Right, bottom | AIP Agent widget | Underwriting Copilot, with the selected application passed as context |
| Toolbar | Action buttons | Request documents · Approve · Decline · Reassign · Escalate |

## Page 2: Operations Overview (manager)
| Widget | Content |
|---|---|
| Bar chart | Open exceptions by type, colored by severity |
| Table | Underwriter workload: open applications, needs attention, SLA breached, days of backlog (open ÷ daily capacity) |
| Line chart | Applications submitted vs. decided per day |
| Object table | All SLA-breached applications, with the *Reassign* action |

## Page 3: Exception Explorer
Filterable object table of UnderwritingException (type, severity, product, underwriter), with bulk *Reassign* for the manager.

## Variables
- `selectedApplication` (object set, single): set by the queue table selection and passed to the object view and the AIP Agent widget
- `currentUser`: used to filter the queue
