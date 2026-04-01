#!/usr/bin/env bash
set -euo pipefail

# Staged network diagnosis for Docker-related LAN instability.
# Runs timed phases and records connectivity + ARP/DHCP signal levels.

IFACE="${IFACE:-enp4s0}"
GATEWAY_IP="${GATEWAY_IP:-192.168.100.99}"
WAN_PROBE_IP="${WAN_PROBE_IP:-1.1.1.1}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
REPORT_DIR="${REPORT_DIR:-./net-debug}"

# Durations (seconds)
BASELINE_SECS="${BASELINE_SECS:-300}"         # 5 min
DAEMON_ONLY_SECS="${DAEMON_ONLY_SECS:-1800}"  # 30 min
POSTGRES_ONLY_SECS="${POSTGRES_ONLY_SECS:-1800}"
FULL_STACK_SECS="${FULL_STACK_SECS:-1800}"
SAMPLE_INTERVAL_SECS="${SAMPLE_INTERVAL_SECS:-30}"

REPORT_FILE=""
CURRENT_STAGE=""

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

sample_once() {
  local ts gw_ok wan_ok arp_cnt dhcp_cnt rx0 rx1 tx0 tx1
  ts="$(date -Is)"
  rx0="$(iface_stat rx_dropped)"
  tx0="$(iface_stat tx_dropped)"

  if ping -n -c 2 -W 1 "$GATEWAY_IP" >/dev/null 2>&1; then gw_ok=1; else gw_ok=0; fi
  if ping -n -c 2 -W 1 "$WAN_PROBE_IP" >/dev/null 2>&1; then wan_ok=1; else wan_ok=0; fi

  arp_cnt="$( (timeout 5 tcpdump -ni "$IFACE" 'arp' 2>/dev/null || true) | wc -l | awk '{print $1}' )"
  dhcp_cnt="$( (timeout 5 tcpdump -ni "$IFACE" 'udp and (port 67 or 68)' 2>/dev/null || true) | wc -l | awk '{print $1}' )"

  rx1="$(iface_stat rx_dropped)"
  tx1="$(iface_stat tx_dropped)"

  log "sample stage=${CURRENT_STAGE} time=${ts} gw_ok=${gw_ok} wan_ok=${wan_ok} arp_5s=${arp_cnt} dhcp_5s=${dhcp_cnt} rx_drop_delta=$((rx1-rx0)) tx_drop_delta=$((tx1-tx0))"
}

run_stage() {
  local stage_name="$1"
  local duration="$2"
  local end
  CURRENT_STAGE="$stage_name"
  log
  log "## stage=${stage_name} duration_secs=${duration} start=$(date -Is)"

  end=$((SECONDS + duration))
  while (( SECONDS < end )); do
    sample_once
    sleep "$SAMPLE_INTERVAL_SECS"
  done

  log "## stage=${stage_name} end=$(date -Is)"
}

compose_services() {
  docker compose -f "$COMPOSE_FILE" config --services
}

main() {
  need_cmd docker
  need_cmd timeout
  need_cmd ping
  need_cmd tcpdump
  need_cmd awk
  need_cmd wc
  need_cmd tee
  require_root

  mkdir -p "$REPORT_DIR"
  REPORT_FILE="${REPORT_DIR}/staged_network_test_$(date +%Y%m%d_%H%M%S).log"

  log "# Staged Docker Network Test"
  log "# started=$(date -Is)"
  log "# iface=${IFACE} gateway=${GATEWAY_IP} wan_probe=${WAN_PROBE_IP}"
  log "# compose_file=${COMPOSE_FILE}"
  log "# durations baseline=${BASELINE_SECS} daemon_only=${DAEMON_ONLY_SECS} postgres_only=${POSTGRES_ONLY_SECS} full_stack=${FULL_STACK_SECS} sample_interval=${SAMPLE_INTERVAL_SECS}"

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    log "ERROR: interface not found: $IFACE"
    exit 1
  fi

  log
  log "# reset to clean state"
  systemctl stop docker docker.socket containerd || true
  sleep 2
  systemctl start containerd docker
  sleep 2
  docker compose -f "$COMPOSE_FILE" down || true
  sleep 2

  run_stage "baseline_no_containers" "$BASELINE_SECS"

  run_stage "docker_daemon_only" "$DAEMON_ONLY_SECS"

  log
  log "# bring postgres only"
  docker compose -f "$COMPOSE_FILE" up -d postgres
  sleep 5
  run_stage "postgres_only" "$POSTGRES_ONLY_SECS"

  log
  log "# bring full stack"
  mapfile -t svcs < <(compose_services)
  if [[ "${#svcs[@]}" -eq 0 ]]; then
    log "ERROR: no services resolved from compose."
    exit 1
  fi
  docker compose -f "$COMPOSE_FILE" up -d "${svcs[@]}"
  sleep 8
  run_stage "full_stack" "$FULL_STACK_SECS"

  log
  log "# cleanup"
  docker compose -f "$COMPOSE_FILE" down || true
  log "# finished=$(date -Is)"
  log "# report_file=${REPORT_FILE}"
}

main "$@"
