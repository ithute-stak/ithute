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
