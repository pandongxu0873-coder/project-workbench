import datetime as dt
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tools import tencent_meeting_source as source
from tools.communication_pipeline import Failure

def paragraph(ident,text='客户要求核对范围，未确认签约。'):
    return {'pid':str(ident),'start_time':'00:00:01','speaker_info':{'username':'客户昵称'},'sentences':[{'words':[{'text':text}]}]}

class TencentMeetingSourceTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.state=Path(self.temp.name)
    def pipe(self):
        p=SimpleNamespace(cfg={'tencent_meeting':{'enabled':True}},start=dt.date(2026,9,26),end=dt.date(2026,10,2),gaps=[],staged=[],ledger={'items':{}},state=self.state,run_root=self.state,new=0)
        p.gap=lambda title,reason:p.gaps.append((title,reason))
        p.stage=lambda *a,**k:p.staged.append((a,k))
        return p
    def test_write_commands_rejected_before_invoking_cli(self):
        with patch.object(source.subprocess,'run') as run:
            for cmd in [('meeting','create'),('record','permission-apply-commit'),('auth','login')]:
                with self.assertRaises(Failure):source.call({},cmd)
            run.assert_not_called()
    def test_full_transcript_uses_paragraph_directory_and_keeps_speaker(self):
        pids=[{'pid':str(i)} for i in range(31)]
        replies=[{'total':31,'pids':pids},{'minutes':{'paragraphs':[paragraph(i) for i in range(30)]},'more':True},{'minutes':{'paragraphs':[paragraph(30)]},'more':False}]
        with patch.object(source,'call',side_effect=replies) as call:
            raw,text=source.transcript({}, {'record_file_id':'f','meeting_id':'m'})
        self.assertEqual(len(raw['paragraphs']),31);self.assertEqual(text.count('客户昵称'),31)
        self.assertEqual(call.call_args.kwargs['pid'],'30')
    def test_missing_page_or_conflicting_paragraph_fails_closed(self):
        meta={'total':2,'pids':[{'pid':'0'},{'pid':'1'}]}
        for page in [[paragraph(0)],[paragraph(0),paragraph(0,'另一份版本')]]:
            with patch.object(source,'call',side_effect=[meta,{'minutes':{'paragraphs':page}}]),self.assertRaises(Failure):
                source.transcript({}, {'record_file_id':'f'})
    def test_pagination_and_bad_schema_are_not_zero_results(self):
        with patch.object(source,'call',side_effect=[{'record_meetings':[],'next_page_token':'a'},{'record_meetings':[],'next_page_token':'a'}]),self.assertRaises(Failure):
            source.listed({},('record','list'),'record_meetings')
        with patch.object(source,'call',return_value={'renamed':[]}),self.assertRaises(Failure):
            source.listed({},('record','list'),'record_meetings')
    def test_no_auth_preserves_gap_without_collecting(self):
        p=self.pipe()
        with patch.object(source,'probe',return_value={'available':False}),patch.object(source,'call') as call:
            source.collect(p);call.assert_not_called()
        self.assertTrue(p.gaps);self.assertFalse(p.staged)
        import json
        d=json.loads((p.state/'material_coverage.json').read_text())['channels']['tencent_meeting']
        self.assertEqual(d['status'],'unavailable');self.assertFalse(d['complete_scope'])

    def test_unrelated_source_gap_does_not_make_tencent_scan_partial(self):
        import json
        p=self.pipe();p.gaps.append(('其他来源','未接通'))
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[]]):source.collect(p)
        d=json.loads((p.state/'material_coverage.json').read_text())['channels']['tencent_meeting']
        self.assertEqual(d['status'],'ok');self.assertEqual(d['gaps'],[])
    def test_shared_records_read_only_when_ready_and_permitted(self):
        p=self.pipe();base={'meeting_id':'m','subject':'客户会议','media_start_time':'2026-09-28T10:00:00+08:00'}
        records=[{'record_file_id':'shared','state':'转码完成，可根据录制文件权限进行下一步','permission_status':'can_view'},
                 {'record_file_id':'closed','state':'转码完成','permission_status':'closed'},
                 {'record_file_id':'pending','state':'转码中','permission_status':'can_view'}]
        records=[{**r,'media_start_time':base['media_start_time']} for r in records]
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{**base,'records':records}],[]]),patch.object(source,'transcript',return_value=({'paragraphs':[]},'客户原文')) as transcript:
            source.collect(p)
        self.assertEqual(transcript.call_count,1);self.assertEqual(len(p.staged),1);self.assertEqual(len(p.gaps),2)
        self.assertEqual(p.staged[0][0][4],'tencent_meeting');self.assertEqual(p.staged[0][0][6],'2026-09-28')
    def test_same_file_in_shared_and_own_lists_is_read_once(self):
        p=self.pipe();r={'record_file_id':'f','state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-28T10:00:00+08:00'}
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'records':[r]}],[{**r,'record_files':[r]}]]),patch.object(source,'transcript',return_value=({},'原文')) as transcript:
            source.collect(p)
        self.assertEqual(transcript.call_count,1)
    def test_unknown_date_does_not_use_collection_day(self):
        self.assertEqual(source.business_date('2026-09-28T10:00:00'),'')
        self.assertEqual(source.business_date('2026-09-28T10:00:00+08:00'),'2026-09-28')
    def test_closed_meeting_variant_does_not_hide_readable_shared_file(self):
        p=self.pipe();readable={'record_file_id':'f','state':'转码完成','media_start_time':'2026-09-28T10:00:00+08:00'}
        for closed in [{'record_file_id':'f','permission_status':'closed'}, {**readable,'permission_status':'can_view','media_start_time':''}, {**readable,'permission_status':'can_view','state':'转码中'}]:
            with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'records':[closed]}],[{**readable,'record_files':[readable]}]]),patch.object(source,'transcript',return_value=({},'原话')) as read:
                source.collect(p)
            self.assertEqual(read.call_count,1)
    def test_malformed_speaker_fails_with_explicit_gap_type(self):
        row={**paragraph(0),'speaker_info':['unknown']}
        with patch.object(source,'call',side_effect=[{'total':1,'pids':[{'pid':'0'}]},{'minutes':{'paragraphs':[row]}}]),self.assertRaises(Failure):
            source.transcript({}, {'record_file_id':'f'})

    def test_complete_cli_transcript_keeps_real_cli_speaker_schema(self):
        row=paragraph(0);row.pop('speaker_info');row['speaker']={'user_name':'会议昵称'}
        with patch.object(source,'call',side_effect=[{'total':1,'pids':[{'pid':'0'}]},{'minutes':{'paragraphs':[row]},'more':False}]) as read:
            raw,text=source.transcript({}, {'record_file_id':'f'})
        self.assertIn('会议昵称',text);self.assertEqual(read.call_count,2)

    def test_more_without_cursor_is_an_explicit_gap(self):
        with patch.object(source,'call',return_value={'record_meetings':[],'has_more':True}),self.assertRaises(Failure):
            source.listed({},('record','list'),'record_meetings')

    def test_official_empty_record_directory_omits_nil_slice_but_proves_zero_page(self):
        data={'current_page':1,'current_size':0,'has_more':False,'next_page_token':'','total_page':0}
        with patch.object(source,'call',return_value=data):self.assertEqual(source.listed({},('record','list'),'record_meetings'),[])
        for changed in ({'has_more':True},{'current_size':1},{'total_page':1},{'total_count':1},{'renamed_records':[]},{'current_size':False},{'total_page':False},{'total_count':False},{'current_page':True},{'current_page':2},{'current_page':None}):
            with patch.object(source,'call',return_value={**data,**changed}),self.assertRaises(Failure):source.listed({},('record','list'),'record_meetings')
        with patch.object(source,'call',side_effect=[{'record_meetings':[{'meeting_id':'m'}],'next_page_token':'next'},data]),self.assertRaises(Failure):source.listed({},('record','list'),'record_meetings')

    def test_pinned_record_list_reads_code_without_date_filter(self):
        p=self.pipe();p.cfg['tencent_meeting']['shared_meeting_codes']=['241438862']
        r={'record_file_id':'f','state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-28T10:00:00+08:00'}
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[{'meeting_id':'m','record_files':[r]}],[]]) as listing,patch.object(source,'transcript',return_value=({},'原话')) as read:
            source.collect(p)
        self.assertEqual(read.call_count,1);self.assertFalse(p.gaps)
        self.assertEqual(listing.call_args_list[1].kwargs,{'meeting_code':'241438862'})

    def test_two_recording_versions_are_one_event_with_both_originals(self):
        import json
        p=self.pipe();records=[{'record_file_id':f,'state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-28T10:00:00+08:00'} for f in ('f1','f2')]
        versions=[({'record_file_id':f,'paragraphs':[paragraph(0,text)]},text) for f,text in [('f1','原文甲'),('f2','原文乙')]]
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'m','records':records}],[]]),patch.object(source,'transcript',side_effect=versions):
            source.collect(p)
        self.assertEqual(len(p.staged),1)
        raw=json.loads(p.staged[0][0][2]);self.assertEqual(len(raw['source_versions']),2)
        self.assertIn('原文甲',p.staged[0][1]['text']);self.assertIn('原文乙',p.staged[0][1]['text'])

    def test_delayed_shared_transcript_is_read_beyond_two_day_run_without_redating(self):
        import json
        p=self.pipe();p.start=dt.date(2026,10,1)
        r={'record_file_id':'late','state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-21T10:00:00+08:00'}
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[{'meeting_id':'m',**r,'record_files':[r]}]]) as listing,patch.object(source,'transcript',return_value=({},'晚共享的原文')):
            source.collect(p)
        self.assertEqual(listing.call_args.kwargs['start'],'2026-09-03T00:00:00+08:00')
        self.assertEqual(p.staged[0][0][6],'2026-09-21')
        d=json.loads((p.state/'tencent-read-receipt.json').read_text());self.assertEqual(d['requested_window']['from'],'2026-10-01');self.assertEqual(d['lookback_days'],30)

    def test_pinned_old_meeting_updates_are_read_but_future_and_unpinned_old_are_not(self):
        p=self.pipe();p.cfg['tencent_meeting']['shared_meeting_codes']=['241438862']
        def record(fid,date):return {'record_file_id':fid,'state':'转码完成','permission_status':'can_view','media_start_time':date+'T10:00:00+08:00'}
        old=record('old','2026-07-01');future=record('future','2026-10-03');unrelated=record('other','2026-07-01')
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'other','records':[unrelated]}],[{'meeting_id':'pinned','record_files':[old,future]}],[]]),patch.object(source,'transcript',return_value=({},'既有共享稿的新正文')) as read:
            source.collect(p)
        self.assertEqual(read.call_count,1);self.assertEqual(read.call_args.args[1]['record_file_id'],'old');self.assertEqual(p.staged[0][0][6],'2026-07-01')

    def test_invalid_lookback_or_missing_pinned_identity_is_explicit_gap(self):
        for value in (True,0,91,'30'):
            p=self.pipe();p.cfg['tencent_meeting']['lookback_days']=value
            with patch.object(source,'listed') as listing:source.collect(p);listing.assert_not_called()
            self.assertTrue(p.gaps)
        p=self.pipe();p.cfg['tencent_meeting']['shared_meeting_codes']=['241438862']
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[],[]]):source.collect(p)
        self.assertTrue(p.gaps)

    def test_incomplete_variant_does_not_publish_a_smaller_event(self):
        p=self.pipe();records=[{'record_file_id':f,'state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-28T10:00:00+08:00'} for f in ('f1','f2')]
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'m','records':records}],[]]),patch.object(source,'transcript',side_effect=[({},'完整版甲'),Failure('乙缺页')]):
            source.collect(p)
        self.assertFalse(p.staged);self.assertTrue(any('未发布' in gap[1] for gap in p.gaps))

    def test_missing_record_id_is_not_silent_zero(self):
        p=self.pipe()
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'records':[{}]}],[]]):source.collect(p)
        self.assertTrue(p.gaps);self.assertFalse(p.staged)

    def test_same_words_with_changed_avatar_are_not_reanalyzed_and_missing_version_is_not_retracted(self):
        import tempfile,json
        from pathlib import Path
        from tools.communication_pipeline import Pipeline
        with tempfile.TemporaryDirectory() as folder:
            kb=Path(folder)/'kb';kb.mkdir();p=Pipeline({'tencent_meeting':{'enabled':True}},Path(folder)/'state',kb,dt.date(2026,9,26),dt.date(2026,10,2))
            records=[{'record_file_id':f,'state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-28T10:00:00+08:00'} for f in ('f1','f2')]
            def run(rows,avatar):
                def read(cfg,r):return {'record_file_id':r['record_file_id'],'paragraphs':[paragraph(0)],'avatar_url':avatar},'同一原话'
                with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'m','records':rows}],[]]),patch.object(source,'transcript',side_effect=read):source.collect(p)
            run(records,'old');entry=next(iter(p.ledger['items'].values()));entry['status']='archived';old=Path(entry['original']).read_bytes()
            run(records,'new');self.assertEqual(len(p.ledger['items']),1);self.assertEqual(p.duplicates,1);self.assertEqual(Path(entry['original']).read_bytes(),old)
            run(records[:1],'new');self.assertEqual(len(p.ledger['items']),1);self.assertTrue(any('本轮未全部读回' in r['reason'] for r in p.gaps))

    def test_all_known_versions_missing_is_not_a_successful_empty_scan(self):
        import json
        p=self.pipe();p.ledger['items']['known']={'channel':'tencent_meeting','key':'tencent-event:m','status':'archived','business_date':'2026-09-21','title':'已归档会议'}
        before=json.loads(json.dumps(p.ledger))
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[]]):source.collect(p)
        self.assertEqual(p.ledger,before);self.assertFalse(p.staged);self.assertTrue(any('全部原文版本' in x[1] for x in p.gaps))
        receipt=json.loads((p.state/'tencent-read-receipt.json').read_text());self.assertFalse(receipt['complete_scope'])

    def test_empty_pinned_record_directory_cannot_be_hidden_by_meeting_enrichment(self):
        import json
        p=self.pipe();p.cfg['tencent_meeting']['shared_meeting_codes']=['241438862']
        # The CLI can enrich meeting get with records=[] after an internal error.
        # We independently query record list by code, never trust that zero.
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'m','records':[],'records_total_count':0}],[],[]]) as listing,patch.object(source,'transcript') as transcript:
            source.collect(p);transcript.assert_not_called()
        self.assertEqual(listing.call_args_list[1].kwargs,{'meeting_code':'241438862'});self.assertTrue(p.gaps)
        self.assertFalse(json.loads((p.state/'tencent-read-receipt.json').read_text())['complete_scope'])

    def test_reused_code_keeps_old_event_id_even_when_all_old_versions_are_missing(self):
        import json
        from tools.communication_pipeline import save
        p=self.pipe();p.cfg['tencent_meeting']['shared_meeting_codes']=['241438862']
        save(p.state/'communication_pipeline/tencent_watch.json',{'version':1,'meetings':{'241438862':['old-mid']}})
        old={'channel':'tencent_meeting','key':'tencent-event:old-mid','status':'archived','business_date':'2026-07-01','title':'老会议'}
        p.ledger['items']['old']=old.copy();new={'meeting_id':'new-mid','record_files':[{'record_file_id':'new','state':'转码完成','media_start_time':'2026-07-02T10:00:00+08:00'}]}
        with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[],[new],[],[]]) as listing,patch.object(source,'transcript',return_value=({},'新的独立事件')):
            source.collect(p)
        self.assertEqual(listing.call_args_list[2].kwargs,{'meeting_id':'old-mid'});self.assertEqual(p.ledger['items']['old'],old)
        self.assertEqual(p.staged[0][0][0],'tencent-event:new-mid');self.assertTrue(any('全部原文版本' in x[1] for x in p.gaps))
        self.assertEqual(json.loads((p.state/'communication_pipeline/tencent_watch.json').read_text())['meetings']['241438862'],['new-mid','old-mid'])

    def test_same_file_id_with_revised_words_is_new_version_and_keeps_original(self):
        import tempfile
        from pathlib import Path
        from tools.communication_pipeline import Pipeline
        with tempfile.TemporaryDirectory() as folder:
            kb=Path(folder)/'kb';kb.mkdir();p=Pipeline({'tencent_meeting':{'enabled':True}},Path(folder)/'state',kb,dt.date(2026,10,1),dt.date(2026,10,2))
            r={'record_file_id':'same-id','state':'转码完成','permission_status':'can_view','media_start_time':'2026-09-21T10:00:00+08:00'}
            def run(words):
                with patch.object(source,'probe',return_value={'available':True}),patch.object(source,'listed',side_effect=[[{'meeting_id':'m','records':[r]}],[]]),patch.object(source,'transcript',return_value=({'record_file_id':'same-id','paragraphs':[paragraph(0,words)]},words)):
                    source.collect(p)
            run('客户仍需业务审批');prior=next(iter(p.ledger['items'].values()));prior['status']='archived';before=Path(prior['original']).read_bytes()
            run('客户澄清先试点，仍未正式批准');self.assertEqual(len(p.ledger['items']),2);self.assertEqual(Path(prior['original']).read_bytes(),before);self.assertEqual(prior['status'],'archived')
