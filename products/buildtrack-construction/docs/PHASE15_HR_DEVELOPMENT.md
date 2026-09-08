# Phase 15 — HR Development and Compliance

Phase 15 completes the people-development layer without duplicating the Phase 3 employee, contract, payroll or security models. Its records remain scoped to the employee’s existing company, branch and site access.

## Included controls

- Candidate pipeline with controlled `applied → screening → interview → offer → appointed/rejected/withdrawn` stages and automatic `CAN` references.
- Employee onboarding items for induction, paperwork, PPE, bank detail confirmation, site orientation or any company-specific joining requirement. Open items have due dates and a completion actor/timestamp.
- Credential and licence register with issuer, reference, controlled evidence document, issue/expiry dates and 30-day/expired compliance indicators.
- Training plans and completions with provider, category, cost, certificate evidence and renewal date.
- Transparent employee performance reviews: delivery, quality, safety and conduct are each scored from 0–5; BuildTrack stores the calculated average and supplied development plan.
- Review acknowledgement is separate from review creation, using the existing scoped permission model.
- HR Manager and Training Officer roles are reconciled into the shared company role catalogue; no separate identity, site or permission system is created.

## Operational boundary

This phase records supplied recruitment, compliance and development evidence. It does not make a hiring decision, issue a licence, verify an external certificate, generate employment contracts, alter payroll, or replace management/employee judgement. A candidate appointed in this register must still be created as a controlled Phase 3 employee before onboarding, site assignment, payroll or attendance is possible.
