import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('swe_seeds',Path(__file__).resolve().parents[1]/'examples/swe-bench/seeds.py')
seeds=importlib.util.module_from_spec(spec);spec.loader.exec_module(seeds)


class CatalogTest(unittest.TestCase):
    def test_explicit_verified_offset_and_hash_are_enforced(self):
        row={'instance_id':'sample','base_commit':'abc','problem_statement':'task','patch':'reference','test_patch':'test'}
        catalog={'dataset':'example/verified','split':'test','offsets':[400],
                 'cases':[{'instanceId':'sample','baseCommit':'abc','sourceRecordSha256':seeds.digest(row)}]}
        urls=[]
        def response(url,timeout):
            urls.append(url)
            return io.BytesIO(json.dumps({'rows':[{'row':row}]}).encode())
        with tempfile.TemporaryDirectory() as tmp, patch.object(seeds.urllib.request,'urlopen',side_effect=response):
            self.assertEqual(seeds.fetch(catalog,['sample'],Path(tmp))['sample'],row)
            self.assertEqual(len(urls),1)
            self.assertIn('offset=400',urls[0])
        catalog['cases'][0]['sourceRecordSha256']='wrong'
        with tempfile.TemporaryDirectory() as tmp, patch.object(seeds.urllib.request,'urlopen',side_effect=response):
            with self.assertRaisesRegex(ValueError,'official seed content differs'):
                seeds.fetch(catalog,['sample'],Path(tmp))


if __name__=='__main__':unittest.main()
