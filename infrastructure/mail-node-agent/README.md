# Ithute Mail Node Agent

This agent turns a registered VPS or dedicated server into an Ithute-managed mail storage node.

It deliberately replaces persistent SSH control. SSH may be used by an administrator for the initial installation, but normal mailbox provisioning uses a one-time Ithute node credential and HTTPS calls to the control plane.

## Install

1. Register the VPS under **Operations → Mail nodes**.
2. Generate the node's agent credential. It is shown once.
3. Copy `agent.py` to `/opt/ithute-mail-agent/agent.py`.
4. Create `/etc/ithute-mail-node/agent.env` from the example and put the one-time token there with mode 0600.
5. Install the systemd service and start it.

The agent reports disk capacity/usage and claims only commands assigned to its authenticated node.

## Docker Mailserver

`ITHUTE_MAIL_ACCOUNTS_FILE` must point at the Docker Mailserver account file that the mail container watches. The agent writes that file in place so the watcher keeps the same inode.

Phase 3 currently synchronizes mailbox existence, active/suspended state and password hashes. Quota is included in the control-plane command payload for the next quota-enforcement step, but is not yet enforced by this agent.

Never commit the node token.
