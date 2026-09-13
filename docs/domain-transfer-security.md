# Domain transfer authorization

Domain ownership changes require organization-administration authority, not only DNS editing authority.

A non-platform user must hold an active membership with `identity.manage` permission in both the source and destination organizations. In the current role model this means tenant administrator access on both sides. DNS administrators cannot move ownership between organizations.

Platform owners may transfer between active organizations. Production billing limits are evaluated against the destination before ownership changes.
