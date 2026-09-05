FROM postgres:16-alpine

RUN apk add --no-cache restic jq coreutils ca-certificates tzdata python3

COPY backup.sh /usr/local/bin/mailbox-backup
COPY restore-drill.sh /usr/local/bin/mailbox-restore-drill
COPY scheduler.sh /usr/local/bin/mailbox-backup-scheduler
COPY status.sh /usr/local/bin/mailbox-backup-status
COPY recovery_server.py /usr/local/bin/mailbox-recovery-server
RUN chmod 0755 \
    /usr/local/bin/mailbox-backup \
    /usr/local/bin/mailbox-restore-drill \
    /usr/local/bin/mailbox-backup-scheduler \
    /usr/local/bin/mailbox-backup-status \
    /usr/local/bin/mailbox-recovery-server

WORKDIR /workspace
CMD ["sh", "-c", "trap : TERM INT; sleep infinity & wait"]
