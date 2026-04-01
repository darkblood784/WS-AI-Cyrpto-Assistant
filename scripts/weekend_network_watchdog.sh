#!/usr/bin/env bash
set -euo pipefail

# Weekend watchdog: records LAN/WAN health and captures evidence on anomalies.
# Run as root (sudo). Default runtime: 48 hours.

IFACE="${IFACE:-enp4s0}"
GATEWAY_IP="${GATEWAY_IP:-192.168.100.99}"
WAN_PROBE_IP="${WAN_PROBE_IP:-1.1.1.1}"
DNS_PROBE_HOST="${DNS_PROBE_HOST:-google.com}"
CLIENT_PROBE_IPS="${CLIENT_PROBE_IPS:-}"  # comma-separated office client IPs, e.g. 192.168.100.12,192.168.100.14
INTERVAL_SECS="${INTERVAL_SECS:-30}"
RUNTIME_SECS="${RUNTIME_SECS:-172800}"  # 48h
OUT_DIR="${OUT_DIR:-/home/whales/Whale_Strategy/wsai/net-debug/weekend-watchdog}"
PCAP_ON_ALERT_SECS="${PCAP_ON_ALERT_SECS:-20}"
ARP_ALERT_THRESHOLD="${ARP_ALERT_THRESHOLD:-60}"    # in 5s sample
DHCP_ALERT_THRESHOLD="${DHCP_ALERT_THRESHOLD:-20}"  # in 5s sample
CLIENT_FAIL_ALERT_THRESHOLD="${CLIENT_FAIL_ALERT_THRESHOLD:-1}"

mkdir -p "$OUT_DIR"
CSV_FILE="${OUT_DIR}/metrics_$(date +%Y%m%d_%H%M%S).csv"
EVENT_FILE="${OUT_DIR}/events_$(date +%Y%m%d_%H%M%S).log"

log_event() {
  echo "[$(date -Is)] $*" | tee -a "$EVENT_FILE"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "ERROR: missing command: $1" >&2
    exit 1
  }
}

iface_stat() {
  local key="$1"
  cat "/sys/class/net/${IFACE}/statistics/${key}" 2>/dev/null || echo 0
}

capture_snapshot() {
  local reason="$1"
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"
  local snap="${OUT_DIR}/snapshot_${ts}.txt"
  local pcap="${OUT_DIR}/alert_${ts}.pcap"

  {
    echo "=== snapshot ts=${ts} reason=${reason} ==="
    date -Is
    echo "--- ip -br a ---"
    ip -br a || true
    echo "--- ip route ---"
    ip route || true
    echo "--- ip neigh (gateway+server ip) ---"
    ip neigh | egrep "${GATEWAY_IP}|192.168.100.42" || true
    echo "--- ss -s ---"
    ss -s || true
    echo "--- docker ps ---"
    docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
    echo "--- recent kernel net logs ---"
    journalctl -k --since "2 min ago" --no-pager || true
    echo "--- recent docker logs ---"
    journalctl -u docker --since "2 min ago" --no-pager || true
  } > "$snap" 2>&1

  timeout "$PCAP_ON_ALERT_SECS" tcpdump -ni "$IFACE" -w "$pcap" 'arp or (udp and (port 67 or 68))' >/dev/null 2>&1 || true
  log_event "ALERT snapshot saved: ${snap}"
  log_event "ALERT pcap saved: ${pcap}"
}

main() {
  need_cmd ping
  need_cmd timeout
  need_cmd tcpdump
  need_cmd getent
  need_cmd awk
  need_cmd wc
  need_cmd ip
  need_cmd ss

  if [[ $EUID -ne 0 ]]; then
    echo "ERROR: run with sudo/root." >&2
    exit 1
  fi

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "ERROR: interface not found: $IFACE" >&2
    exit 1
  fi

  echo "timestamp,gw_ok,wan_ok,dns_ok,client_ok,client_fail,client_ok_ips,client_fail_ips,arp_5s,dhcp_5s,rx_drop_delta,tx_drop_delta,docker_running_count" > "$CSV_FILE"
  log_event "watchdog started iface=${IFACE} gateway=${GATEWAY_IP} wan_probe=${WAN_PROBE_IP} interval=${INTERVAL_SECS}s runtime=${RUNTIME_SECS}s"
  log_event "client_probe_ips=${CLIENT_PROBE_IPS:-none}"
  log_event "csv=${CSV_FILE}"
  log_event "events=${EVENT_FILE}"

  local end
  end=$((SECONDS + RUNTIME_SECS))
  while (( SECONDS < end )); do
    local gw_ok wan_ok dns_ok arp_cnt dhcp_cnt rx0 rx1 tx0 tx1 docker_count reason
    local client_ok client_fail
    local client_ok_ips client_fail_ips
    local ts
    ts="$(date -Is)"
    rx0="$(iface_stat rx_dropped)"
    tx0="$(iface_stat tx_dropped)"

    if ping -n -c 2 -W 1 "$GATEWAY_IP" >/dev/null 2>&1; then gw_ok=1; else gw_ok=0; fi
    if ping -n -c 2 -W 1 "$WAN_PROBE_IP" >/dev/null 2>&1; then wan_ok=1; else wan_ok=0; fi
    if getent hosts "$DNS_PROBE_HOST" >/dev/null 2>&1; then dns_ok=1; else dns_ok=0; fi
    client_ok=0
    client_fail=0
    client_ok_ips=""
    client_fail_ips=""
    if [[ -n "$CLIENT_PROBE_IPS" ]]; then
      IFS=',' read -r -a _clients <<< "$CLIENT_PROBE_IPS"
      for cip in "${_clients[@]}"; do
        if ping -n -c 1 -W 1 "$cip" >/dev/null 2>&1; then
          client_ok=$((client_ok + 1))
          client_ok_ips="${client_ok_ips:+${client_ok_ips}|}${cip}"
        else
          client_fail=$((client_fail + 1))
          client_fail_ips="${client_fail_ips:+${client_fail_ips}|}${cip}"
        fi
      done
    fi

    arp_cnt="$( (timeout 5 tcpdump -ni "$IFACE" 'arp' 2>/dev/null || true) | wc -l | awk '{print $1}' )"
    dhcp_cnt="$( (timeout 5 tcpdump -ni "$IFACE" 'udp and (port 67 or 68)' 2>/dev/null || true) | wc -l | awk '{print $1}' )"

    rx1="$(iface_stat rx_dropped)"
    tx1="$(iface_stat tx_dropped)"
    docker_count="$(docker ps -q 2>/dev/null | wc -l | awk '{print $1}')"

    echo "${ts},${gw_ok},${wan_ok},${dns_ok},${client_ok},${client_fail},\"${client_ok_ips}\",\"${client_fail_ips}\",${arp_cnt},${dhcp_cnt},$((rx1-rx0)),$((tx1-tx0)),${docker_count}" >> "$CSV_FILE"

    reason=""
    if [[ "$gw_ok" -eq 0 ]]; then reason="gateway_unreachable"; fi
    if [[ "$wan_ok" -eq 0 ]]; then reason="${reason:+${reason}+}wan_unreachable"; fi
    if [[ "$dns_ok" -eq 0 ]]; then reason="${reason:+${reason}+}dns_fail"; fi
    if [[ "$client_fail" -ge "$CLIENT_FAIL_ALERT_THRESHOLD" && -n "$CLIENT_PROBE_IPS" ]]; then
      reason="${reason:+${reason}+}office_client_probe_fail"
    fi
    if [[ "$gw_ok" -eq 1 && "$wan_ok" -eq 1 && "$dns_ok" -eq 1 && "$client_fail" -ge "$CLIENT_FAIL_ALERT_THRESHOLD" && -n "$CLIENT_PROBE_IPS" ]]; then
      reason="${reason:+${reason}+}server_ok_office_clients_bad"
    fi
    if [[ "$arp_cnt" -gt "$ARP_ALERT_THRESHOLD" ]]; then reason="${reason:+${reason}+}arp_spike"; fi
    if [[ "$dhcp_cnt" -gt "$DHCP_ALERT_THRESHOLD" ]]; then reason="${reason:+${reason}+}dhcp_spike"; fi
    if [[ "$((rx1-rx0))" -gt 50 ]]; then reason="${reason:+${reason}+}rx_drop_spike"; fi

    if [[ -n "$reason" ]]; then
      log_event "ALERT reason=${reason} gw_ok=${gw_ok} wan_ok=${wan_ok} dns_ok=${dns_ok} client_ok=${client_ok} client_fail=${client_fail} client_ok_ips=${client_ok_ips:-none} client_fail_ips=${client_fail_ips:-none} arp_5s=${arp_cnt} dhcp_5s=${dhcp_cnt} rx_drop_delta=$((rx1-rx0)) tx_drop_delta=$((tx1-tx0)) docker_running=${docker_count}"
      capture_snapshot "$reason"
    fi

    sleep "$INTERVAL_SECS"
  done

  log_event "watchdog finished normally"
}

main "$@"
