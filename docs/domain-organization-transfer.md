# Domain organization transfer

Ithute can move an existing domain from one organization to another without releasing or recreating the global domain claim.

## Rules

- The domain keeps the same domain ID, DNS mode, verification state, public DNS configuration and lifecycle state.
- Current mail resources owned by the domain move with it: mailboxes, aliases, distribution groups, DKIM keys and mailbox-level operational configuration.
- Historical audit records, domain events and verification attempts are not rewritten. Transfer-out and transfer-in records are added so the ownership change remains traceable.
- The source and destination organizations must both authorize organization administration (`identity.manage`). Platform owners retain their platform-wide bypass.
- The destination organization must be active and, in production, must have billing entitlement for another domain.
- Archived domains cannot be transferred.
- A transfer does not perform a registrar change, nameserver cutover or DNS record replacement.

The domain portfolio UI exposes **Move** only to platform owners and tenant administrators who have an eligible destination organization.
