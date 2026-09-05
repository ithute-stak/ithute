#!/bin/sh
set -eu
: "${MAIL_EDGE_NODE1_HOST:?MAIL_EDGE_NODE1_HOST is required}"
: "${MAIL_EDGE_NODE1_SMTP_PORT:=25}"
: "${MAIL_EDGE_NODE1_SUBMISSION_PORT:=587}"
: "${MAIL_EDGE_NODE1_IMAPS_PORT:=993}"
: "${MAIL_EDGE_NODE2_SMTP_PORT:=25}"
: "${MAIL_EDGE_NODE2_SUBMISSION_PORT:=587}"
: "${MAIL_EDGE_NODE2_IMAPS_PORT:=993}"

add_server() {
  name="$1"; host="$2"; port="$3"
  [ -n "$host" ] || return 0
  echo "    server $name $host:$port check inter 3s fall 3 rise 2"
}

{
cat <<'EOF'
global
    log stdout format raw local0
    maxconn 10000

defaults
    log global
    mode tcp
    timeout connect 5s
    timeout client 2m
    timeout server 2m

frontend smtp_in
    bind *:25
    default_backend smtp_nodes
backend smtp_nodes
    balance roundrobin
EOF
add_server smtp1 "$MAIL_EDGE_NODE1_HOST" "$MAIL_EDGE_NODE1_SMTP_PORT"
add_server smtp2 "${MAIL_EDGE_NODE2_HOST:-}" "$MAIL_EDGE_NODE2_SMTP_PORT"
cat <<'EOF'

frontend submission_in
    bind *:587
    default_backend submission_nodes
backend submission_nodes
    balance leastconn
EOF
add_server submission1 "$MAIL_EDGE_NODE1_HOST" "$MAIL_EDGE_NODE1_SUBMISSION_PORT"
add_server submission2 "${MAIL_EDGE_NODE2_HOST:-}" "$MAIL_EDGE_NODE2_SUBMISSION_PORT"
cat <<'EOF'

frontend imaps_in
    bind *:993
    default_backend imaps_nodes
backend imaps_nodes
    balance leastconn
EOF
add_server imaps1 "$MAIL_EDGE_NODE1_HOST" "$MAIL_EDGE_NODE1_IMAPS_PORT"
add_server imaps2 "${MAIL_EDGE_NODE2_HOST:-}" "$MAIL_EDGE_NODE2_IMAPS_PORT"
} > /tmp/haproxy.cfg

exec haproxy -W -db -f /tmp/haproxy.cfg
