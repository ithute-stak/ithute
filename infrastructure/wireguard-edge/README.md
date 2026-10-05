# Ithute managed private network

The Ithute Edge host owns the `ithute0` WireGuard interface. Hosting VPS nodes
generate their own private keys locally and enroll only their public keys.

The edge reconciler reads the approved peer set from the Ithute control plane
using a dedicated reconciler credential and applies it every 30 seconds. It
never receives node private keys.

Required production settings:

- `ITHUTE_WIREGUARD_SUBNET` — private mesh CIDR, e.g. `10.70.0.0/24`
- `ITHUTE_WIREGUARD_EDGE_ADDRESS` — edge address inside that CIDR, e.g. `10.70.0.1`
- `ITHUTE_WIREGUARD_EDGE_PUBLIC_KEY` — public key derived from the edge private key
- `ITHUTE_WIREGUARD_EDGE_ENDPOINT` — public UDP endpoint, e.g. `204.12.205.224:51820`
- `ITHUTE_WIREGUARD_RECONCILER_TOKEN` — strong secret shared only by the edge reconciler and API
- `ITHUTE_HOSTING_ORIGIN_CIDRS` — should include the managed mesh subnet

The edge private key lives only in `/etc/ithute-wireguard/private.key`.


## Automatic edge bootstrap

Fresh Ithute VPS setup and normal production upgrades now run
`bootstrap.sh` automatically. The helper is idempotent and:

- installs WireGuard tooling and iptables when required;
- generates the edge private key once under `/etc/ithute-wireguard/private.key`;
- derives and writes the edge public key into `.env.production`;
- creates/preserves a strong reconciler credential;
- writes the edge address, subnet, endpoint and UDP listen port into production config;
- opens only the configured WireGuard UDP port through an Ithute-owned persistent firewall service;
- brings up `ithute0` before the API is available, avoiding first-boot circular dependencies;
- installs and enables the peer reconciler timer;
- validates the interface address and listen port before returning success.

The private key and reconciler secret are never printed by the bootstrap.

If the VPS provider has a separate cloud firewall/security group, UDP 51820 (or
the configured listen port) must also be permitted there. Host-level firewall
configuration cannot modify a provider control plane.

For recovery on an existing Ithute edge host, use the same canonical helper:

```bash
sudo ITHUTE_APP_DIR=/home/administrator/ithute-platform \
  bash /home/administrator/ithute-platform/infrastructure/wireguard-edge/bootstrap.sh
```

`scripts/verify-production-readiness.sh` validates the edge interface, address,
public key, listen port, firewall service, reconciler timer and advertised
endpoint whenever the managed-network settings exist in production.

## Default full-mesh peer communication

Every enrolled Ithute node can communicate with every other enrolled node by default across the private WireGuard network. The edge enables IPv4 forwarding and routes `ithute0 -> ithute0` traffic through the dedicated `ITHUTE_WG_MESH` chain, which accepts peer traffic while keeping the mesh separate from public interfaces.

The existing service-grant records remain available as topology metadata and for a future optional restricted/segmented mode, but they are not required for normal node-to-node communication in the default full-mesh mode.
