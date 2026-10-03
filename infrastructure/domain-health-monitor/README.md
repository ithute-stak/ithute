# Ithute Domain Health Monitor

This production timer runs the domain mail-health transition monitor inside the existing Ithute API container every 15 minutes.

It checks mail-enabled domains using the same health engine exposed in the Control Centre and writes tenant notifications only when health transitions:

- healthy -> attention/pending: one warning notification
- attention/pending -> healthy: one recovery notification
- unchanged degraded state: no repeated notification

## Install

From the production checkout:

```bash
sudo ITHUTE_DIR=/opt/ithute ./infrastructure/domain-health-monitor/install.sh
```

Use `systemctl status ithute-domain-health-monitor.timer` and `journalctl -u ithute-domain-health-monitor.service` for operations.
