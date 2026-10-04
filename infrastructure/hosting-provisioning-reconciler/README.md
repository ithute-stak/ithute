# Ithute Hosting Provisioning Reconciler

Runs the control-plane reconciliation pass for active hosting workflows.

It advances healthy deployments through private-origin handoff, DNS propagation,
Caddy route activation and HTTPS readiness. The reconciler is idempotent and
safe to run repeatedly.

Install the service and timer on the Ithute control-plane host, then enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ithute-hosting-provisioning-reconciler.timer
```

The backend container must have `ITHUTE_HOSTING_ORIGIN_CIDRS` configured with
the private/VPN hosting-origin networks reachable from the edge host.
