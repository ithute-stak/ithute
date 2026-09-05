# !thute Tutor school workspaces

`!thute Tutor` is one education ecosystem, but every institution operates inside an isolated school workspace.

## Product model

A person has one central `!thute Auth` identity. Tutor keeps school-specific memberships and roles in its own database.

```text
!thute Auth person
       |
       +-- School A membership: teacher
       +-- School B membership: parent
       +-- School C membership: school_admin
```

A learner is also a continuous Tutor learner. Changing school creates a new school enrollment; it does not create a new human identity or erase earlier academic history.

```text
Learner
  +-- School A enrollment (2024-2025)
  +-- School B enrollment (2026-current)
```

## Standalone school experience

Once a school is active, the application must behave as though that institution is the only school using the system:

- the school name/logo/branding identifies the dashboard;
- students are limited to that school's enrollments;
- teachers and employees are limited to that school's employment/assignment;
- classes are enabled through `SchoolClass` mappings;
- attendance, finance, payroll, notifications and social content are school scoped;
- an unauthorized school id returns 403/404 instead of cross-school data;
- switching school clears/reloads school-specific browser state.

A single-school user enters their school automatically and does not see a tenant switcher. A multi-school user gets a school switcher. A user with no school is presented with **Open your school** first.

## School profile lifecycle

Any authenticated Tutor user may open a school profile. The creator becomes that school's `school_admin` through a `SchoolMembership` row.

New schools start unverified. Platform verification confirms the institution; it does not give other schools access to its operational data.

A school profile can contain its name, category, code, registration number, logo, motto, colors, address, phone, email, website, timezone, currency, locale and school-specific settings.

## Active school authorization

The selected school cookie/header is only a workspace selector. It is never trusted as authorization by itself.

For each request the backend verifies:

1. the user is authenticated through central `!thute Auth`;
2. the selected school exists and is active;
3. the user has an active `SchoolMembership` for it, unless they are a platform super-admin;
4. the role for authorization comes from that school membership;
5. the route applies the active `school_id` to every school-owned query/mutation.

## Shared reference data vs school-owned data

Some education definitions can be shared platform reference data, such as Grade 1, Grade 7 or common subject definitions. Schools select/use those definitions through school mappings. An ordinary school must not rename or delete the global catalog for every other school.

School-owned data includes, at minimum:

- memberships and roles;
- enrollments;
- class assignments;
- attendance;
- teacher/employment records;
- fee configuration/plans/invoices/payments;
- payroll;
- notifications;
- social/feed content;
- school-specific reports and settings.

## Transfer-safe records

School ownership must be captured at the time a record is created. It must not be inferred later from a learner's current school.

For example, `FeePayment.school_id` records the school that received the payment. If the learner later transfers, the historical payment stays with the original school.

Legacy payments are automatically backfilled only where enrollment history identifies exactly one school. Ambiguous multi-school history is left unresolved for audited reconciliation rather than guessed.

## Central platform boundary

`!thute Auth` owns identity and authentication. `!thute Push` owns device delivery. Tutor owns education/business authorization and data.

No school gets access to the Auth or Push database, and one school never gets direct database access to another school.
