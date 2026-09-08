# Phase 14 — Mobile and Offline Field Capture

Phase 14 provides a phone-friendly local queue for daily diary, attendance, material delivery, plant-use, photo-evidence and inspection captures. A capture is stored on the device when the connection is unavailable and synchronised idempotently when the user reconnects.

The server records each synchronised item as pending review. A different authorised person must accept or return it. Even an accepted item does not automatically create a payroll, stock, fleet, progress, quality or incident transaction; the responsible controller posts verified evidence through the existing authoritative BuildTrack workflow.
