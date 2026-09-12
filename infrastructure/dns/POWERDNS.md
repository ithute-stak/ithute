# Ithute authoritative DNS runtime

Production uses PowerDNS Authoritative as the managed DNS engine because the Mailbox DNS control plane performs DNS changes through the PowerDNS HTTP API.

- `ithute-dns` is the only production service that publishes TCP/UDP port 53.
- The HTTP API listens only on the internal Ithute Docker network; port 8081 is not published on the VPS.
- The API key comes from the persistent `ITHUTE_APP_POWERDNS_API_KEY` runtime secret and is shared only with `ithute-app-api` and `ithute-dns`.
- Authoritative data lives in the named volume `ithute_powerdns_data`.
- On the first PowerDNS start only, `infrastructure/dns/zones/db.ithute.co.ls` seeds the current `ithute.co.ls` zone. If the zone already exists in the persistent database, startup never reloads or overwrites it.
- The former BIND cache volume is deliberately left declared during migration so routine Compose deployment cannot delete it. Compose deployment does not use `down -v`, volume prune, or system prune.

The checked-in seed is therefore a first-start migration source, not the ongoing production source of truth. After migration, DNS record changes are persisted by PowerDNS and are made through the control-plane API.
