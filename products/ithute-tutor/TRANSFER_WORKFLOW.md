# !thute Tutor — Professional Learner Transfer Workflow

The learner transfer process is a controlled handover between two school workspaces. A transfer claim code identifies the receiving school, but does not itself change enrolment ownership.

## Status lifecycle

```text
released -> under_review -> accepted
                      \-> rejected
released/under_review -> cancelled
released -> expired
```

## 1. Releasing school

A principal, vice-principal, registrar, admissions officer or school administrator:

1. selects the currently enrolled learner;
2. records the transfer reason and optional handover note;
3. confirms that learner/parent/guardian authorization required by the school's process has been recorded;
4. releases the transfer;
5. receives a permanent transfer reference and a short-lived, one-time claim code.

The learner remains actively enrolled at the releasing school during this stage.

## 2. Receiving school claim

The receiving school enters the one-time code. Tutor then:

- binds that transfer case to the receiving school;
- changes the case to `under_review`;
- records who claimed it and when;
- opens a controlled admission-review packet.

Claiming does **not** deactivate the source enrolment and does **not** create the destination enrolment.

## 3. Admission review

The receiving school can review only information necessary for the transfer decision:

- learner identity and admission number;
- releasing school;
- current class/grade/year/term;
- recent attendance summary;
- recent published academic results;
- releasing-school transfer reason/note.

Finance data is not shared. Source-school records remain read-only.

Admission-review packet access exists only while the transfer is `under_review`. If the case is rejected or cancelled, that review access closes and only the transfer audit record remains.

## 4. Decision

### Accept

Before acceptance the receiving school must:

- select the receiving class;
- choose the effective start date;
- confirm the transfer packet was reviewed;
- optionally record an admission/placement note.

Final acceptance cannot be performed before the effective transfer date. If a future move is planned, the case remains `under_review` until that date so the learner stays active at the releasing school in the meantime.

Acceptance is atomic:

1. source enrolment becomes historical/transferred;
2. source student membership is deactivated;
3. destination enrolment is created and activated;
4. destination student membership is activated;
5. the learner keeps the same !thute Tutor identity;
6. full read-only longitudinal academic/attendance history becomes available to the receiving school.

### Reject

A rejection requires a reason. The transfer case closes, but the learner remains active at the releasing school.

### Cancel

The releasing school may cancel a released or under-review transfer with a reason. The learner remains active at the releasing school.

## 5. Audit and privacy

Every transfer has a permanent reference such as `TR-2026-...` and an event history recording release, claim, acceptance, rejection, cancellation or expiry.

The receiving school cannot browse arbitrary learners at another school. Cross-school record access exists only through an explicit transfer relationship, and financial records are excluded from the transfer dossier.

For multi-hop transfers such as School A -> School B -> School C, School C receives the learner's prior accepted academic/attendance lineage from A and B after the B -> C transfer is completed. Ownership of the original records remains with the school that created them.
