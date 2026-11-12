import csv
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import network as n


IFACE = n.Interface(7, "Test Ethernet", "192.168.50.10", 24, "192.168.50.1", "02-00-00-00-00-01")


class SubnetTests(unittest.TestCase):
    def test_cidr_matrix(self):
        examples = (
            ("10.23.45.67/8", "10.0.0.0", "10.255.255.255", "255.0.0.0", 16777214),
            ("172.20.45.67/16", "172.20.0.0", "172.20.255.255", "255.255.0.0", 65534),
            ("172.20.45.67/20", "172.20.32.0", "172.20.47.255", "255.255.240.0", 4094),
            ("192.0.2.140/25", "192.0.2.128", "192.0.2.255", "255.255.255.128", 126),
            ("192.0.2.5/30", "192.0.2.4", "192.0.2.7", "255.255.255.252", 2),
        )
        for value, address, broadcast, mask, hosts in examples:
            with self.subTest(value=value):
                result = n.subnet_info(value)
                self.assertEqual(result["Network address"], address)
                self.assertEqual(result["Broadcast address"], broadcast)
                self.assertEqual(result["Subnet mask"], mask)
                self.assertEqual(int(result["Kullanılabilir adres sayısı"]), hosts)

    def test_mask_and_cidr_agree(self):
        info = n.subnet_info("192.168.50.42/24")
        self.assertEqual(info, n.subnet_info("192.168.50.42/255.255.255.0"))
        self.assertEqual(info["Network address"], "192.168.50.0")
        self.assertEqual(info["Broadcast address"], "192.168.50.255")
        self.assertEqual(info["Kullanılabilir adres sayısı"], "254")

    def test_point_to_point_and_host(self):
        self.assertEqual(n.subnet_info("10.0.0.0/31")["Kullanılabilir adres sayısı"], "2")
        self.assertEqual(n.subnet_info("10.0.0.8/32")["Kullanılabilir IP aralığı"], "10.0.0.8 – 10.0.0.8")

    def test_invalid_inputs(self):
        for value in ("", "hello", "::1/128", "192.0.2.1/33", "192.0.2.1/255.0.255.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                n.subnet_info(value)


class GuardTests(unittest.TestCase):
    def test_target_cap_and_boundaries(self):
        self.assertEqual(len(n.validate_targets(IFACE, "192.168.50.1", "192.168.50.64")), 64)
        for first, last in (("192.168.50.1", "192.168.50.65"), ("192.168.50.0", "192.168.50.1"),
                            ("192.168.50.254", "192.168.50.255"), ("192.168.50.2", "192.168.50.1"),
                            ("192.168.51.1", "192.168.51.2"), ("8.8.8.8", "8.8.8.8"), ("::1", "::1")):
            with self.subTest(first=first, last=last), self.assertRaises(ValueError):
                n.validate_targets(IFACE, first, last)

    def test_public_interface_rejected(self):
        iface = n.Interface(8, "Test", "8.8.8.8", 24, "8.8.8.1", "")
        with self.assertRaises(ValueError):
            n.validate_targets(iface, "8.8.8.8", "8.8.8.8")

    def test_large_subnet_stays_bounded(self):
        iface = n.Interface(8, "Test", "10.10.1.5", 8, "10.0.0.1", "")
        with self.assertRaises(ValueError):
            n.validate_targets(iface, "10.0.0.1", "10.255.255.254")
        self.assertEqual(len(n.validate_targets(iface, "10.10.1.1", "10.10.1.3")), 3)

    @patch("network.probe")
    def test_unbounded_rate_duplicates_and_external_rejected_before_io(self, probe):
        for targets, interval in ((["192.168.50.1"], .1), (["8.8.8.8"], 1),
                                  (["192.168.50.1"] * 2, 1), ([], 1)):
            with self.assertRaises(ValueError):
                n.discover(IFACE, targets, threading.Event(), interval=interval)
        probe.assert_not_called()

    @patch("network.interfaces", return_value=[])
    @patch("network.probe")
    def test_interface_change_aborts(self, probe, interfaces):
        with self.assertRaises(ValueError):
            n.discover(IFACE, ["192.168.50.1"], threading.Event())
        probe.assert_not_called()

    @patch("network.interfaces", return_value=[IFACE])
    @patch("network.powershell", return_value={"InterfaceIndex": 99, "NextHop": "0.0.0.0"})
    @patch("network.probe")
    def test_vpn_route_aborts(self, probe, ps, interfaces):
        with self.assertRaises(ValueError):
            n.discover(IFACE, ["192.168.50.1"], threading.Event())
        probe.assert_not_called()

    @patch("network.interfaces", return_value=[IFACE])
    @patch("network.powershell", return_value={"InterfaceIndex": 7, "NextHop": "192.168.50.2"})
    @patch("network.probe")
    def test_routed_next_hop_aborts(self, probe, ps, interfaces):
        with self.assertRaises(ValueError):
            n.discover(IFACE, ["192.168.50.1"], threading.Event())
        probe.assert_not_called()


class DiscoveryTests(unittest.TestCase):
    @patch("network.interfaces", return_value=[IFACE])
    @patch("network.powershell", return_value={"InterfaceIndex": 7, "NextHop": "0.0.0.0"})
    @patch("network.neighbors", return_value={})
    def test_one_second_between_probe_starts(self, neighbors, ps, interfaces):
        clock = [1000.0]
        starts = []

        class FakeStop:
            def wait(self, seconds):
                clock[0] += seconds
                return False

            def is_set(self):
                return False

        def probe(*args):
            starts.append(clock[0])
            return "Yanıt var", ""

        with patch("network.time.monotonic", side_effect=lambda: clock[0]), patch("network.probe", side_effect=probe):
            devices, warnings = n.discover(IFACE, ["192.168.50.1", "192.168.50.2", "192.168.50.3"], FakeStop())
        self.assertEqual(starts, [1000.0, 1001.0, 1002.0])
        self.assertEqual(len(devices), 3)
        self.assertEqual(warnings, [])

    @patch("network.interfaces", return_value=[IFACE])
    @patch("network.powershell", return_value={"InterfaceIndex": 7, "NextHop": "0.0.0.0"})
    @patch("network.probe", return_value=("Yanıt yok / belirsiz", ""))
    @patch("network.neighbors", return_value={"192.168.50.1": ("02-00-00-00-00-02", "Stale"), "192.168.50.99": ("02-00-00-00-00-03", "Reachable")})
    def test_no_reply_is_unknown_and_cache_stays_in_scope(self, neighbors, probe, ps, interfaces):
        devices, warnings = n.discover(IFACE, ["192.168.50.1"], threading.Event())
        self.assertFalse(warnings)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].icmp, "Yanıt yok / belirsiz")
        self.assertEqual(devices[0].neighbor, "Stale")
        self.assertEqual(devices[0].role, "Modem / gateway")

    @patch("network.interfaces", return_value=[IFACE])
    @patch("network.neighbors", return_value={})
    @patch("network.probe")
    def test_cancel_before_probe(self, probe, neighbors, interfaces):
        stop = threading.Event()
        stop.set()
        devices, _ = n.discover(IFACE, ["192.168.50.1"], stop)
        self.assertEqual(devices, [])
        probe.assert_not_called()

    @patch("network.powershell", return_value=[
        {"IPAddress": "192.168.50.1", "LinkLayerAddress": "02-00-00-00-00-02", "State": "Stale"},
        {"IPAddress": "192.168.50.2", "LinkLayerAddress": "00-00-00-00-00-00", "State": "Incomplete"},
        {"IPAddress": "224.0.0.1", "LinkLayerAddress": "01-00-5e-00-00-01", "State": "Permanent"},
        {"IPAddress": "192.168.50.255", "LinkLayerAddress": "FF-FF-FF-FF-FF-FF", "State": "Permanent"}])
    def test_neighbor_filter(self, ps):
        self.assertEqual(list(n.neighbors(IFACE)), ["192.168.50.1"])


class StorageTests(unittest.TestCase):
    def test_names_roundtrip_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data" / "names.json"
            self.assertEqual(n.load_names(path), {})
            n.save_names(path, {"mac:02-00-00-00-00-01": "Çalışma bilgisayarı"})
            self.assertEqual(n.load_names(path)["mac:02-00-00-00-00-01"], "Çalışma bilgisayarı")
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                n.load_names(path)

    def test_csv_encoding_columns_and_formula_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "inventory.csv"
            n.export_csv(path, [n.Device("192.168.50.1", hostname="=DANGEROUS()", name="Çalışma odası")])
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(len(rows[0]), 7)
            self.assertEqual(rows[1][2], "'=DANGEROUS()")
            self.assertEqual(rows[1][6], "Çalışma odası")


if __name__ == "__main__":
    unittest.main()
