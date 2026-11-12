"""Explicitly authorized, two-target real LAN smoke test; prints counts only."""
import argparse
import threading
import network


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-local", action="store_true", help="Ağın size ait olduğunu ve iki hedeflik kontrolü onaylayın")
    args = parser.parse_args()
    if not args.confirm_local:
        parser.error("Aktif kontrol için --confirm-local gerekir.")
    adapters = network.interfaces()
    if not adapters:
        raise SystemExit("Uygun yerel fiziksel IPv4 arayüzü bulunamadı.")
    iface = adapters[0]
    targets = list(dict.fromkeys([iface.gateway, iface.address]))
    targets = [t for t in targets if t]
    devices, warnings = network.discover(iface, targets, threading.Event())
    replies = sum(d.icmp == "Yanıt var" for d in devices)
    macs = sum(bool(d.mac) for d in devices)
    print(f"Yerel test: {len(devices)} hedef, {replies} ICMP yanıtı, {macs} MAC, {len(warnings)} uyarı.")
    print("Kişisel adresler kaydedilmedi. Toplu subnet keşfi yapılmadı.")
    if len(devices) != len(targets) or replies == 0 or warnings:
        raise SystemExit("Yerel test kısmen doğrulanabildi; uygulamada ağ durumunu inceleyin.")


if __name__ == "__main__":
    main()
