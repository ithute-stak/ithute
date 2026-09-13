# Domain transfer API example

```http
POST /api/v1/tenants/{source_tenant_id}/domains/{domain_id}/transfer
Content-Type: application/json

{
  "target_tenant_id": "00000000-0000-0000-0000-000000000000"
}
```

A successful request returns the existing domain with its new `tenant_id`. The domain is not deleted or recreated.
