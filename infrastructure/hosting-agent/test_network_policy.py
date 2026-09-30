import ipaddress
import unittest

from network_policy import choose_project_subnet, parse_existing_subnets, parse_pool


class NetworkPolicyTests(unittest.TestCase):
    def test_parse_pool_requires_private_ipv4(self):
        self.assertEqual(str(parse_pool("10.240.0.0/12", 28)), "10.240.0.0/12")
        with self.assertRaises(RuntimeError):
            parse_pool("8.8.8.0/24", 28)
        with self.assertRaises(RuntimeError):
            parse_pool("10.240.0.1/12", 28)
        with self.assertRaises(RuntimeError):
            parse_pool("10.240.0.0/12", 29)

    def test_same_project_is_deterministic(self):
        pool = parse_pool("10.240.0.0/16", 28)
        first = choose_project_subnet(pool, 28, "11111111-1111-1111-1111-111111111111", [])
        second = choose_project_subnet(pool, 28, "11111111-1111-1111-1111-111111111111", [])
        self.assertEqual(first, second)
        self.assertTrue(first.subnet_of(pool))
        self.assertEqual(first.prefixlen, 28)

    def test_collision_probes_to_another_free_subnet(self):
        pool = parse_pool("10.240.0.0/24", 28)
        project = "22222222-2222-2222-2222-222222222222"
        first = choose_project_subnet(pool, 28, project, [])
        second = choose_project_subnet(pool, 28, project, [first])
        self.assertNotEqual(first, second)
        self.assertFalse(first.overlaps(second))
        self.assertTrue(second.subnet_of(pool))

    def test_pool_exhaustion_fails_closed(self):
        pool = parse_pool("10.240.0.0/28", 28)
        with self.assertRaises(RuntimeError):
            choose_project_subnet(pool, 28, "project", [pool])

    def test_existing_subnet_parser_ignores_non_ipv4_noise(self):
        rows = parse_existing_subnets(["10.240.1.0/28", "", "garbage", "2001:db8::/64"])
        self.assertEqual(rows, [ipaddress.ip_network("10.240.1.0/28")])


if __name__ == "__main__":
    unittest.main()
