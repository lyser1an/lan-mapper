"""Windows-only, bounded local IPv4 discovery; no third-party dependencies."""
from __future__ import annotations

import base64
import csv
import ipaddress as ip
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from collections.abc import Callable

MAX_TARGETS = 64
MIN_INTERVAL = 1.0
PRIVATE_NETWORKS = tuple(ip.IPv4Network(n) for n in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def powershell(script: str, timeout: float = 25):
    if os.name != "nt":
        raise RuntimeError("Bu uygulama Windows PowerShell gerektirir.")
    script = "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); " + script
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            capture_output=True, encoding="utf-8", errors="replace",
                            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError("PowerShell ağ bilgilerini okuyamadı: " + result.stderr.strip()[:350])
    raw = result.stdout.lstrip("\ufeff").strip()
    return json.loads(raw) if raw else None


@dataclass(frozen=True)
class Interface:
    index: int
    name: str
    address: str
    prefix: int
    gateway: str
    mac: str
    metric: int = 0

    @property
    def network(self) -> ip.IPv4Network:
        return ip.IPv4Interface(f"{self.address}/{self.prefix}").network


def interfaces() -> list[Interface]:
    rows = powershell(r"""
    $rows = @(foreach ($a in (Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' -and $_.InterfaceType -in @(6,71) })) {
      $cfg = Get-NetIPConfiguration -InterfaceIndex $a.ifIndex
      $routes = @(Get-NetRoute -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric)
      $metric = (Get-NetIPInterface -InterfaceIndex $a.ifIndex -AddressFamily IPv4).InterfaceMetric
      foreach ($v4 in @(Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 | Where-Object { $_.AddressState -eq 'Preferred' -and -not $_.SkipAsSource })) {
        [PSCustomObject]@{index=[int]$a.ifIndex; name=[string]$a.Name; address=[string]$v4.IPAddress;
          prefix=[int]$v4.PrefixLength; gateway=$(if($routes.Count){[string]$routes[0].NextHop}else{''});
          mac=[string]$a.MacAddress; metric=([int]$metric + $(if($routes.Count){[int]$routes[0].RouteMetric}else{9999}))}
      }
    }); ConvertTo-Json -InputObject $rows -Compress
    """) or []
    if isinstance(rows, dict):
        rows = [rows]
    result = []
    for row in rows:
        obj = Interface(**row)
        if any(ip.IPv4Address(obj.address) in n for n in PRIVATE_NETWORKS):
            result.append(obj)
    return sorted(result, key=lambda a: (not bool(a.gateway), a.metric, a.index, a.address))


def subnet_info(value: str) -> dict[str, str]:
    net = ip.IPv4Network(value.strip(), strict=False)
    first = net.network_address if net.prefixlen >= 31 else net.network_address + 1
    last = net.broadcast_address if net.prefixlen >= 31 else net.broadcast_address - 1
    return {"Network address": str(net.network_address), "Broadcast address": str(net.broadcast_address),
            "Subnet mask": str(net.netmask), "CIDR": f"/{net.prefixlen}",
            "Kullanılabilir IP aralığı": f"{first} – {last}",
            "Kullanılabilir adres sayısı": str(int(last) - int(first) + 1)}


def validate_targets(iface: Interface, start: str, end: str) -> list[str]:
    net = iface.network
    if not any(net.subnet_of(n) for n in PRIVATE_NETWORKS):
        raise ValueError("Keşif yalnızca fiziksel arayüzün özel IPv4 subnet'inde yapılabilir.")
    a, b = ip.IPv4Address(start.strip()), ip.IPv4Address(end.strip())
    count = int(b) - int(a) + 1
    if count < 1 or count > MAX_TARGETS:
        raise ValueError(f"Tek keşifte 1–{MAX_TARGETS} hedef seçin.")
    if a not in net or b not in net:
        raise ValueError("Hedeflerin tamamı seçili arayüzün yerel subnet'inde olmalı.")
    if net.prefixlen < 31 and (a == net.network_address or b == net.broadcast_address):
        raise ValueError("Network ve broadcast adresleri hedef olamaz.")
    return [str(ip.IPv4Address(n)) for n in range(int(a), int(b) + 1)]


@dataclass
class Device:
    ip: str
    mac: str = ""
    hostname: str = ""
    icmp: str = "Kontrol edilmedi"
    neighbor: str = ""
    role: str = "Cihaz"
    name: str = ""


def neighbors(iface: Interface) -> dict[str, tuple[str, str]]:
    rows = powershell(f"ConvertTo-Json -InputObject @(Get-NetNeighbor -InterfaceIndex {int(iface.index)} -AddressFamily IPv4 | Select-Object IPAddress,LinkLayerAddress,@{{n='State';e={{[string]$_.State}}}}) -Compress") or []
    result = {}
    for row in rows:
        address = ip.IPv4Address(row["IPAddress"])
        mac = row.get("LinkLayerAddress", "")
        if (address in iface.network and address not in (iface.network.network_address, iface.network.broadcast_address)
                and re.fullmatch(r"[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}", mac)
                and mac.replace(":", "").replace("-", "").upper() not in ("000000000000", "FFFFFFFFFFFF")):
            result[str(address)] = (mac, row["State"])
    return result


def probe(iface: Interface, address: str) -> tuple[str, str]:
    # .NET Ping checks the actual reply status (localized ping.exe output is unreliable).
    # Hostnames come only from Windows' existing DNS cache; no external DNS query.
    data = powershell(f"""
    $p = [Net.NetworkInformation.Ping]::new()
    try {{
      $r = $p.Send('{ip.IPv4Address(address)}', 700)
      $hostName = ''
      try {{ $hostName = [string](Get-DnsClientCache -ErrorAction SilentlyContinue | Where-Object {{ $_.Data -eq '{ip.IPv4Address(address)}' -and $_.Type -eq 1 }} | Select-Object -First 1 -ExpandProperty Entry) }} catch {{}}
      @{{ok=($r.Status -eq 'Success'); hostname=$hostName}} | ConvertTo-Json -Compress
    }} finally {{ $p.Dispose() }}
    """, timeout=8)
    return ("Yanıt var" if data["ok"] else "Yanıt yok / belirsiz", data["hostname"])


def discover(iface: Interface, targets: list[str], stop: threading.Event,
             progress: Callable[[int, int], None] = lambda *_: None,
             interval: float = MIN_INTERVAL) -> tuple[list[Device], list[str]]:
    if not targets or len(targets) > MAX_TARGETS or interval < MIN_INTERVAL:
        raise ValueError("Hedef veya hız sınırı geçersiz.")
    if len(set(targets)) != len(targets):
        raise ValueError("Tekrarlanan hedefler kabul edilmez.")
    for target in targets:
        validate_targets(iface, target, target)
    # Re-read just before discovery; a changed/disconnected interface cannot reuse consent.
    if iface not in interfaces():
        raise ValueError("Arayüz değişti. Ağ bilgilerini yenileyip yeniden onaylayın.")
    warnings = []
    devices: dict[str, Device] = {}
    last = 0.0
    for n, address in enumerate(targets, 1):
        if stop.wait(max(0.0, interval - (time.monotonic() - last))):
            break
        # Check Windows' selected route before every request; reject VPN/remote next hops.
        route = powershell(f"Find-NetRoute -RemoteIPAddress '{ip.IPv4Address(address)}' | Where-Object {{ $null -ne $_.NextHop }} | Select-Object -First 1 InterfaceIndex,NextHop | ConvertTo-Json -Compress")
        if not route or int(route["InterfaceIndex"]) != iface.index or route["NextHop"] != "0.0.0.0":
            raise ValueError("Hedefe doğrudan yerel arayüzden ulaşılamıyor; keşif durduruldu.")
        if stop.is_set():
            break
        last = time.monotonic()
        dev = Device(address, role="Bu bilgisayar" if address == iface.address else "Modem / gateway" if address == iface.gateway else "Cihaz")
        try:
            dev.icmp, dev.hostname = probe(iface, address)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
            dev.icmp = "Kontrol hatası / belirsiz"
            warnings.append(f"{address}: {exc}")
        devices[address] = dev
        progress(n, len(targets))
    try:
        for address, (mac, state) in neighbors(iface).items():
            # Do not turn the entire cached neighbor table into an unbounded inventory.
            if address in devices:
                devices[address].mac = mac
                devices[address].neighbor = state
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        warnings.append(f"Komşu tablosu okunamadı: {exc}")
    for dev in devices.values():
        if dev.ip == iface.address:
            dev.mac = iface.mac
    return sorted(devices.values(), key=lambda d: ip.IPv4Address(d.ip)), warnings


def load_names(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise ValueError("Cihaz adı dosyası geçersiz.")
    return data


def device_key(iface: Interface, device: Device) -> str:
    return ("mac:" + device.mac.upper().replace(":", "-")) if device.mac else f"ip:{iface.network}:{device.ip}"


def save_names(path: Path, names: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def export_csv(path: Path, devices: list[Device]) -> None:
    # Prevent spreadsheet formula interpretation of untrusted hostnames / custom names.
    def safe(value: str) -> str:
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["IP", "MAC", "Hostname", "ICMP", "Komşu durumu", "Rol", "Cihaz adı"])
        for device in devices:
            writer.writerow([safe(str(v)) for v in asdict(device).values()])
