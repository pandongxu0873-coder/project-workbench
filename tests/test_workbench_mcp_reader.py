import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('maintenance_reader',Path(__file__).resolve().parents[1]/'tools/workbench_mcp/reader.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)

class MaintenanceReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.reader=m.Reader(self.root)
        (self.root/'server.py').write_text('def main():\n    return 42\n')
        (self.root/'src').mkdir();(self.root/'workbench_data').mkdir();(self.root/'logs').mkdir()
    def tearDown(self):self.temp.cleanup()
    def state(self,name,value):
        p=self.root/'workbench_data'/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(value))
    def test_code_read_and_search_have_line_evidence(self):
        self.assertIn('server.py',self.reader.list_code()['files'])
        self.assertEqual(self.reader.search_code('return')['matches'][0]['line'],2)
        self.assertIn('2:     return 42',self.reader.read_code('server.py',2,1)['content'])
    def test_unknown_files_and_paths_are_rejected(self):
        for p in ['../server.py','/etc/passwd','workbench_data/password.json','auth/token.py','tools/communication_sources.json']:
            with self.assertRaises(ValueError):self.reader.read_code(p)
    def test_leaf_symlink_is_rejected(self):
        (self.root/'src'/'steal.py').symlink_to(self.root/'server.py')
        with self.assertRaises((OSError,ValueError)):self.reader.read('src/steal.py')
        self.assertNotIn('src/steal.py',self.reader.list_code()['files'])
    def test_parent_symlink_is_rejected(self):
        (self.root/'src'/'linked').symlink_to(self.root/'logs',target_is_directory=True)
        (self.root/'logs'/'x.py').write_text('secret')
        with self.assertRaises((OSError,ValueError)):self.reader.read('src/linked/x.py')
    def test_oversized_files_are_rejected(self):
        (self.root/'large.py').write_bytes(b'x'*(m.MAX_FILE+1))
        with self.assertRaises(ValueError):self.reader.read_code('large.py')
    def test_fifo_rejected_without_blocking(self):
        os.mkfifo(self.root/'pipe.py')
        with self.assertRaises(ValueError):self.reader.read('pipe.py')
    def test_parameters_are_bounded(self):
        for count in [0,161,True,1.5]:
            with self.assertRaises(ValueError):self.reader.read_code('server.py',1,count)
        with self.assertRaises(ValueError):self.reader.search_code('a'*101)
    def test_secrets_redacted(self):
        secret='sk-'+('z'*24)
        (self.root/'server.py').write_text('api_key = "privatevalue"\nclient_secret: othersecret\n'+secret+'\nme@example.com\nBearer xyz123\n')
        body=self.reader.read_code('server.py')['content']
        for s in ['privatevalue','othersecret',secret,'me@example.com','xyz123']:self.assertNotIn(s,body)
    def test_sync_only_projects_allowlisted_operational_fields(self):
        self.state('background_operations.json',{'jobs':{'communications':{'status':'ready','error':'SECRET','access_token':'TOKEN','interval_seconds':3600}}})
        self.state('communication_pipeline/latest.json',{'status':'partial','gaps':['PRIVATE MAIL'],'observed':{'mail':3},'task_notes':'PRIVATE CUSTOMER'})
        body=self.reader.sync_status();text=json.dumps(body)
        self.assertEqual(body['jobs']['communications']['interval_seconds'],3600)
        self.assertEqual(body['counts']['gaps'],{'entries':1})
        for s in ['SECRET','TOKEN','PRIVATE MAIL','PRIVATE CUSTOMER']:self.assertNotIn(s,text)
    def test_missing_and_corrupt_state_are_explicit(self):
        self.assertFalse(self.reader.sync_status()['sources'][0]['available'])
        (self.root/'workbench_data'/'background_operations.json').write_text('broken')
        self.assertFalse(self.reader.sync_status()['sources'][0]['available'])
    def test_analysis_payload_never_exposes_business_or_prompt(self):
        self.state('project_analysis/'+'a'*20+'.json',{'correction':'private','result':{'analysis':'private','model':'example','created_at':'today'},'sync':{'input_chars':100,'status':'ready','prompt':'private'},'requests':[{'status':'queued','text':'private'}]})
        result=self.reader.analysis_status();self.assertNotIn('private',json.dumps(result));self.assertEqual(result['items'][0]['sync']['input_chars'],100)
    def test_logs_return_classes_not_messages(self):
        (self.root/'logs'/'salesworkbench-api.err.log').write_text('ValueError: secret message with token\n  File "'+str(self.root)+'/server.py", line 12, in main\n')
        result=self.reader.log_summary();self.assertEqual(result['error_counts_in_sample'],{'ValueError':1});self.assertNotIn('secret',json.dumps(result));self.assertEqual(result['recent_stack_locations'][0]['line'],12)
    def test_reads_leave_business_files_unchanged(self):
        self.state('background_operations.json',{'jobs':{}})
        paths=[p for p in self.root.rglob('*') if p.is_file()];before={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in paths}
        self.reader.overview();self.reader.list_code();self.reader.read_code('server.py');self.reader.sync_status();self.reader.analysis_status();self.reader.log_summary()
        after={str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
