# Security-grade backup deployment

Ithute control-plane backups are designed so the primary backup job cannot erase the off-site recovery history.

## Required production controls

1. Run the normal backup stack and enable the `offsite-backup` profile.
2. Set `ITHUTE_BACKUP_REMOTE` to a dedicated remote path.
3. Mount a dedicated `ITHUTE_BACKUP_RCLONE_CONFIG` that is not shared with the database or API containers.
4. Configure the remote account with write/list/read permissions but no delete permission where the provider supports it.
5. Enable provider-side object lock / immutability with retention longer than the local retention window.
6. Leave `ITHUTE_BACKUP_REQUIRE_OFFSITE=true` in production.
7. Monitor `/api/v1/backups/status` and weekly restore-drill history.

The off-site worker uses `rclone copy --immutable`; it never issues delete or purge operations. Local retention therefore cannot delete remote backups.

Every PostgreSQL dump gets a SHA-256 sidecar. Restore drills verify that checksum before running `pg_restore`.

## Two-person destructive changes

Production enables `SECURITY_DUAL_CONTROL_ENABLED=true` by default. Protected operations such as mail-node failover require an approval created by one platform owner and approved by another. Approvals expire, are single-use, and are bound to the exact operation payload.

For failover, request an approval with:

- action: `mail_node.failover`
- resource_type: `mail_node`
- resource_id: source node UUID
- payload: target_node_id and snapshot_id

The requester cannot approve their own change.
