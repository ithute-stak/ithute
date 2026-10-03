# Ithute Mail Node Agent

This agent turns a registered VPS or dedicated server into an Ithute-managed mail storage node.

It deliberately replaces persistent SSH control. SSH may be used by an administrator for the initial installation, but normal mailbox provisioning uses a one-time Ithute node credential and HTTPS calls to the control plane.

## Install

1. Register the VPS under **Operations → Mail nodes**.
2. Generate the node's agent credential. It is shown once.
3. Copy `agent.py` to `/opt/ithute-mail-agent/agent.py`.
4. Create `/etc/ithute-mail-node/agent.env` from the example and put the one-time token there with mode 0600.
5. Install the systemd service and start it.

The agent reports disk capacity/usage, verifies SMTP ports 25/587, verifies IMAPS on 993 with the node hostname certificate, and claims only commands assigned to its authenticated node.

## Docker Mailserver

`ITHUTE_MAIL_ACCOUNTS_FILE` must point at the Docker Mailserver account file that the mail container watches. The agent writes that file in place so the watcher keeps the same inode.

The agent synchronizes mailbox existence, active/suspended state, password hashes and Dovecot quota limits. `ITHUTE_MAIL_QUOTAS_FILE` must point to Docker Mailserver's `dovecot-quotas.cf` file in the same watched config directory as `postfix-accounts.cf`.

Never commit the node token.
