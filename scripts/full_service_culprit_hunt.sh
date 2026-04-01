#!/usr/bin/env bash
set -euo pipefail

# Non-disruptive culprit hunt:
# - Enumerates docker compose services + systemd enabled services
# - Starts inactive services one-by-one
# - Never stops already running services
# - Probes connectivity and L2 signal after each start

IFACE="${IFACE:-enp4s0}"
GATEWAY_IP="${GATEWAY_IP:-192.168.100.99}"
WAN_PROBE_IP="${WAN_PROBE_IP:-1.1.1.1}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
REPORT_DIR="${REPORT_DIR:-./net-debug}"
GRACE_SECS="${GRACE_SECS:-8}"
PROBE_SECS="${PROBE_SECS:-15}"

# Safety gate: starting all enabled systemd services can be risky.
# User must explicitly opt in.
ALLOW_ALL_SYSTEMD_START="${ALLOW_ALL_SYSTEMD_START:-no}"

REPORT_FILE=""

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run with sudo/root." >&2
    exit 1
  fi
}

log() {
  echo "$@" | tee -a "$REPORT_FILE"
}

iface_stat() {
  local key="$1"
  cat "/sys/class/net/${IFACE}/statistics/${key}" 2>/dev/null || echo 0
}

probe_once() {
  local tag="$1"
  local gw_ok wan_ok arp_cnt dhcp_cnt rx0 rx1 tx0 tx1
  rx0="$(iface_stat rx_dropped)"
  tx0="$(iface_stat tx_dropped)"

  if ping -n -c 4 -W 1 "$GATEWAY_IP" >/dev/null 2>&1; then gw_ok=1; else gw_ok=0; fi
  if ping -n -c 4 -W 1 "$WAN_PROBE_IP" >/dev/null 2>&1; then wan_ok=1; else wan_ok=0; fi

  # timeout returns 124 by design; keep pipeline successful under pipefail.
  arp_cnt="$( (timeout "$PROBE_SECS" tcpdump -ni "$IFACE" 'arp' 2>/dev/null || true) | wc -l | awk '{print $1}' )"
  dhcp_cnt="$( (timeout "$PROBE_SECS" tcpdump -ni "$IFACE" 'udp and (port 67 or 68)' 2>/dev/null || true) | wc -l | awk '{print $1}' )"

  rx1="$(iface_stat rx_dropped)"
  tx1="$(iface_stat tx_dropped)"

  log "probe tag=${tag} time=$(date -Is) gw_ok=${gw_ok} wan_ok=${wan_ok} arp_${PROBE_SECS}s=${arp_cnt} dhcp_${PROBE_SECS}s=${dhcp_cnt} rx_drop_delta=$((rx1-rx0)) tx_drop_delta=$((tx1-tx0))"
}

is_systemd_active() {
  local unit="$1"
  systemctl is-active --quiet "$unit"
}

list_enabled_systemd_services() {
  systemctl list-unit-files --type=service --state=enabled --no-legend \
    | awk '{print $1}' \
    | grep -E '\.service$' \
    | sort -u
}

list_compose_services() {
  docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null || true
}

is_compose_running() {
  local svc="$1"
  local id
  id="$(docker compose -f "$COMPOSE_FILE" ps -q "$svc" 2>/dev/null || true)"
  if [[ -z "$id" ]]; then
    return 1
  fi
  [[ "$(docker inspect -f '{{.State.Running}}' "$id" 2>/dev/null || echo false)" == "true" ]]
}

start_compose_service_if_needed() {
  local svc="$1"
  if is_compose_running "$svc"; then
    log "docker service ${svc}: already running, skipped"
    return 2
  fi
  if docker compose -f "$COMPOSE_FILE" up -d "$svc" >>"$REPORT_FILE" 2>&1; then
    log "docker service ${svc}: started"
    return 0
  fi
  log "docker service ${svc}: failed to start"
  return 1
}

start_systemd_service_if_needed() {
  local unit="$1"
  if is_systemd_active "$unit"; then
    log "systemd ${unit}: already active, skipped"
    return 2
  fi

  if [[ "$ALLOW_ALL_SYSTEMD_START" != "yes" ]]; then
    log "systemd ${unit}: inactive, NOT started (set ALLOW_ALL_SYSTEMD_START=yes to enable)"
    return 3
  fi

  if systemctl start "$unit" >>"$REPORT_FILE" 2>&1; then
    log "systemd ${unit}: started"
    return 0
  fi
  log "systemd ${unit}: failed to start"
  return 1
}

main() {
  need_cmd docker
  need_cmd systemctl
  need_cmd tcpdump
  need_cmd timeout
  need_cmd ping
  need_cmd awk
  require_root

  mkdir -p "$REPORT_DIR"
  REPORT_FILE="${REPORT_DIR}/full_service_culprit_hunt_$(date +%Y%m%d_%H%M%S).log"

  log "# Full Service Culprit Hunt"
  log "# started=$(date -Is)"
  log "# iface=${IFACE} gateway=${GATEWAY_IP} wan_probe=${WAN_PROBE_IP}"
  log "# probe_secs=${PROBE_SECS} grace_secs=${GRACE_SECS}"
  log "# compose_file=${COMPOSE_FILE}"
  log "# allow_all_systemd_start=${ALLOW_ALL_SYSTEMD_START}"
  log "# note=non-disruptive: running services are not stopped"

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    log "ERROR: interface not found: ${IFACE}"
    exit 1
  fi

  mapfile -t compose_svcs < <(list_compose_services)
  mapfile -t systemd_svcs < <(list_enabled_systemd_services)

  log
  log "## inventory"
  log "compose_service_count=${#compose_svcs[@]}"
  log "systemd_enabled_service_count=${#systemd_svcs[@]}"
  if [[ "${#compose_svcs[@]}" -gt 0 ]]; then
    log "compose_services=${compose_svcs[*]}"
  fi

  log
  log "## baseline probe"
  probe_once "baseline"

  log
  log "## phase: docker compose services"
  for svc in "${compose_svcs[@]}"; do
    log
    log "### docker service=${svc} begin $(date -Is)"
    start_compose_service_if_needed "$svc" || true
    sleep "$GRACE_SECS"
    probe_once "after_docker_${svc}"
  done

  log
  log "## phase: enabled systemd services"
  for unit in "${systemd_svcs[@]}"; do
    log
    log "### systemd unit=${unit} begin $(date -Is)"
    start_systemd_service_if_needed "$unit" || true
    sleep 1
    probe_once "after_systemd_${unit%.service}"
  done

  log
  log "# finished=$(date -Is)"
  log "# report_file=${REPORT_FILE}"
}

main "$@"
