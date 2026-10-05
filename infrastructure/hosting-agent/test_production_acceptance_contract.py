from __future__ import annotations

import subprocess
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "infrastructure" / "hosting-node"
ACCEPTANCE = NODE / "production-acceptance.sh"
VALIDATOR = NODE / "validate-host.sh"
FIREWALL_UNIT = NODE / "ithute-hosting-egress.service"


class ProductionAcceptanceContractTests(unittest.TestCase):
    def test_acceptance_script_is_valid_bash(self) -> None:
        subprocess.run(["bash", "-n", str(ACCEPTANCE)], check=True)

    def test_acceptance_is_strict_and_non_destructive(self) -> None:
        text = ACCEPTANCE.read_text()
        self.assertIn("ITHUTE_HOSTING_REQUIRE_AGENT_ACTIVE=true", text)
        self.assertIn("systemctl is-enabled --quiet ithute-hosting-egress.service", text)
        self.assertIn("systemctl is-active --quiet ithute-hosting-egress.service", text)
        self.assertIn("systemctl is-enabled --quiet ithute-hosting-agent.service", text)
        self.assertIn("systemctl is-active --quiet ithute-hosting-agent.service", text)
        self.assertIn("iptables -C DOCKER-USER", text)
        self.assertIn("ITHUTE_HOSTING_SMOKE_DOMAIN", text)
        self.assertIn("ITHUTE_HOSTING_BACKUP_REMOTE", text)
        self.assertIn("rclone", text)
        self.assertNotIn("systemctl reboot", text)
        self.assertNotIn("shutdown -r", text)
        self.assertNotIn("docker system prune", text)
        self.assertNotIn("docker volume prune", text)

    def test_validator_requires_persistent_firewall_service(self) -> None:
        text = VALIDATOR.read_text()
        self.assertIn("systemctl is-enabled --quiet ithute-hosting-egress.service", text)
        self.assertIn("systemctl is-active --quiet ithute-hosting-egress.service", text)
        self.assertIn("ITHUTE_HOSTING_REQUIRE_AGENT_ACTIVE", text)

    def test_postgres_replication_is_fail_closed_and_fenced(self) -> None:
        text = (ROOT / "infrastructure" / "hosting-agent" / "agent_v4.py").read_text()
        self.assertIn('ITHUTE_HOSTING_POSTGRES_REPLICATION_MODE", "disabled"', text)
        self.assertIn("POSTGRES_REPLICATION_DEDICATED", text)
        self.assertIn('"--wal-method=stream"', text)
        self.assertIn('"--write-recovery-conf"', text)
        self.assertIn("pg_is_in_recovery()", text)
        self.assertIn("pg_promote(wait_seconds => 60)", text)
        self.assertIn("source_fencing_confirmed", text)
        self.assertIn("Refusing PostgreSQL promotion without confirmed old-primary fencing", text)
        self.assertNotIn("shell=True", text)

    def test_firewall_unit_orders_after_docker_before_agent(self) -> None:
        text = FIREWALL_UNIT.read_text()
        self.assertIn("After=network-online.target docker.service", text)
        self.assertIn("Before=ithute-hosting-agent.service", text)
        self.assertIn("ExecStart=/opt/ithute-hosting-node/apply-egress-firewall.sh", text)
        self.assertIn("WantedBy=multi-user.target", text)


if __name__ == "__main__":
    unittest.main()
