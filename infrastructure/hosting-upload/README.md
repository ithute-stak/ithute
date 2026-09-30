# Ithute Hosting ZIP Quarantine

This service is the upload trust boundary for customer ZIP source archives. The public Ithute backend registers source metadata and issues a short-lived one-time upload ticket; raw archive bytes are sent directly to this service instead of the control-plane container.

## Security boundary

The service:

- accepts only `PUT /v1/uploads/<source-id>` with a one-time `ith_zip_...` bearer token;
- requires an exact `Content-Length` matching the source registration;
- streams the archive to a quarantine file while calculating SHA-256;
- validates the ZIP central directory without extracting customer files;
- rejects absolute/traversal/backslash paths, duplicate paths, symlinks, special files and encrypted entries;
- enforces 100,000 files, 2 GiB unpacked data, a 512 MiB per-file ceiling and compression-ratio limits;
- atomically promotes a successful archive to the verified store with `os.replace`;
- reports the verified digest, file count and unpacked size to the Ithute control plane;
- deletes failed temporary/verified files and invalidates the upload ticket through the control plane.

It does **not** run customer code, extract archives, build images, access databases, or receive production hosting-node credentials.

## Required environment

```text
ITHUTE_API_URL=https://ithute.co.ls
ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN=ith_upload_<strong-random-secret>
ITHUTE_HOSTING_UPLOAD_LISTEN_HOST=127.0.0.1
ITHUTE_HOSTING_UPLOAD_LISTEN_PORT=8096
ITHUTE_HOSTING_UPLOAD_QUARANTINE_ROOT=/var/lib/ithute-upload/quarantine
ITHUTE_HOSTING_UPLOAD_VERIFIED_ROOT=/var/lib/ithute-upload/verified
```

The backend must receive the same `ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN` and should set `ITHUTE_HOSTING_UPLOAD_PUBLIC_URL` to the externally routed upload-service URL. The service token is infrastructure-only and must never be exposed to customers.

## Storage layout

Quarantine and verified storage should live outside the Ithute application containers. The upload service needs write access to both. The isolated builder should later receive **read-only access only to the verified directory**, never the quarantine directory.

```text
/var/lib/ithute-upload/
  quarantine/       # private temporary files; upload service only
  verified/         # immutable validated ZIP archives
```

Production retention must remove superseded verified archives only through a scoped Ithute cleanup job. Do not use VPS-wide Docker or filesystem pruning for customer hosting data.

## Reverse proxy

Expose only the upload endpoint and health check. Apply a request-body limit no greater than the platform ZIP limit, long upload timeouts appropriate for the configured bandwidth, TLS, rate limiting, and per-IP connection limits. The service itself still validates `Content-Length`, ticket state, checksum and ZIP safety even when a proxy has already applied limits.
