import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('layout_owner', ROOT / 'examples/harmony-emulator/check_layout_owner.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class LayoutOwnerTest(unittest.TestCase):
    def check(self, value):
        return checker.inspect(json.dumps(value).encode(), 'app.settings', 'display.title', 'Display & brightness')

    def test_inherited_owner_matches(self):
        layout = {'attributes': {'bundleName': 'app.settings'}, 'children': [
            {'attributes': {'id': 'display.title', 'text': 'Display & brightness'}}]}
        self.assertTrue(self.check(layout)['matched'])

    def test_same_text_in_other_app_and_sibling_is_not_a_match(self):
        layout = {'children': [{'attributes': {'bundleName': 'app.settings'}},
                               {'attributes': {'bundleName': 'app.other'}, 'children': [
                                   {'attributes': {'id': 'display.title', 'text': 'Display & brightness'}}]}]}
        self.assertFalse(self.check(layout)['matched'])

    def test_explicit_foreign_or_empty_owner_breaks_inheritance(self):
        for owner in ('app.other', '', None):
            with self.subTest(owner=owner):
                layout = {'attributes': {'bundleName': 'app.settings'}, 'children': [
                    {'attributes': {'bundleName': owner, 'id': 'display.title', 'text': 'Display & brightness'}}]}
                self.assertFalse(self.check(layout)['matched'])

    def test_invalid_json_and_missing_target_are_rejected(self):
        with self.assertRaises(ValueError):
            checker.inspect(b'{', 'app.settings', 'display.title', 'Display & brightness')
        with self.assertRaises(ValueError):
            checker.inspect(b'{}', '', 'display.title', 'Display & brightness')


if __name__ == '__main__':
    unittest.main()
