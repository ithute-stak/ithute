# Ithute Mail Node Provisioner Contract

Ithute can provision mail infrastructure through any provider adapter rather than hard-coding one VPS vendor into the control plane.

Configure:

- `MAIL_NODE_PROVISIONER_URL`
- `MAIL_NODE_PROVISIONER_TOKEN`
- `MAIL_NODE_CONTROL_PLANE_URL`

Ithute sends an authenticated POST request to the configured provisioner. The provisioner may call Proxmox, Hetzner, Vultr, DigitalOcean, a private cloud, or another infrastructure API.

## Request

The request contains:

- a stable Ithute `node_id`;
- node name, region, tenant scope and requested hostname;
- requested storage, RAM and CPU;
- a short-lived installation contract containing the Ithute public API URL, one-time mail-node agent token and bootstrap profile `ithute-mail-node-v1`.

The provider adapter must inject the bootstrap values securely into the new server, install the Ithute mail-node bundle, configure off-node backups and TLS, and start the agent.

## Required response

```json
{
  "provider": "proxmox",
  "instance_id": "vm-4201",
  "hostname": "mail-node-01.example.com",
  "public_ip": "203.0.113.10",
  "ssh_user": "root",
  "ssh_port": 22,
  "metadata": {}
}
```

The returned hostname must exactly match the requested hostname. Ithute stores provider metadata but never stores a provider root password or SSH password.

The node remains in `provisioning` and cannot receive mailboxes until its agent reports SMTP, IMAP and TLS all ready. At that point the control plane automatically activates it.

This contract keeps Ithute provider-neutral while still supporting fully automatic VPS creation.
