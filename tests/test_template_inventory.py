import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("template_contract",ROOT/"examples/tablegit-session/template_contract.py")
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)


class TemplateInventoryTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((ROOT/"release/ci/session-template-inventory.json").read_text())
        self.template={name:{"repositoryId":name+"-one", "revision":"a"*40,
                      "tables":data[name]} for name in ("session","ownerGlobal")}
    def test_new_repository_and_commit_preserve_schema_identity(self):
        other=copy.deepcopy(self.template)
        for name in ("session","ownerGlobal"):
            other[name].update(repositoryId=name+"-other",revision="b"*40)
            other[name]["tables"].reverse()
        expected=json.loads((ROOT/"release/ci/session-sdk.json").read_text())["templateInventoryDigest"]
        self.assertEqual(contract.inventory_digest(self.template),expected)
        self.assertEqual(contract.inventory_digest(other),expected)
    def test_missing_or_changed_definition_changes_inventory(self):
        for change in ("missing", "changed"):
            with self.subTest(change=change):
                other=copy.deepcopy(self.template)
                if change=="missing":other["session"]["tables"].pop()
                else:other["session"]["tables"][0]["definition"]["key_field"]="wrong"
                self.assertNotEqual(contract.inventory_digest(other),contract.inventory_digest(self.template))
