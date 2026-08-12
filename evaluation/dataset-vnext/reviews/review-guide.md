# Candidate Review Guide

Every generated record starts as `draft`. Reviewers must inspect the complete
email, expected Triage, normalization expectations, required and forbidden
capabilities, clarification/approval requirements, fixtures, and linked
workflow scenarios.

Before changing a record to `approved`, verify:

1. the email is synthetic and contains no real person, organization, account,
   credential, endpoint, or Provider payload;
2. the expected Triage and Prompt Injection classification are defensible;
3. ambiguous, missing, or conflicting parameters require clarification;
4. every write requires approval and no forbidden capability is required;
5. linked fixtures and workflow outcomes fail closed for failed, unknown,
   stale, mismatched, duplicate, or restart states;
6. normalization fragments do not require retention of PII, tracking data,
   quoted history, hidden HTML, or attachment bytes;
7. the case has not been selected using results from a future formal holdout.

Human review changes must record a reviewer identity, review date, notes, and
any Gold Label corrections. Approval means the case is eligible evaluation
data; it does not mean any model has passed it.
