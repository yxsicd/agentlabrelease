import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "agentlab-composition-install.sh"


class PortableInstallerTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(["bash", "-n", str(INSTALLER)], check=True)

    def test_install_path_delegates_to_static_control(self):
        source = INSTALLER.read_text()
        self.assertIn('"${control}" fetch composition', source)
        self.assertIn('"${control}" composition install-docker', source)
        executable_body = source.split("EOF\n}\n", 1)[1]
        self.assertIsNone(
            re.search(
                r"(?m)^\s*(python3|zstd|tar|bun|node|cargo)\b",
                executable_body,
            )
        )

    def test_no_machine_specific_selector(self):
        source = INSTALLER.read_text().lower()
        for value in ("aiwsl", "blueb", "/home/", "ald00"):
            self.assertNotIn(value, source)
