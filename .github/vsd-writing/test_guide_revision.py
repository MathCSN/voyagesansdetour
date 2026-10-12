import copy
import unittest
from guide_revision import apply_corrections
from guide_review import public_blocks
from update_draft import digest

class RevisionTests(unittest.TestCase):
    def setUp(self):
        paragraph=' '.join(['Une phrase de test documentée pour préserver un corps éditorial complet.']*8)
        self.article={'title':'Titre','shortTitle':'Titre court','description':'Unique description','summary':'Résumé','sections':[{'id':'a','title':'A','paragraphs':[paragraph,paragraph]}],'faq':[],'readMinutes':2}
        self.citations={'a':['f1']};self.facts=[{'id':'f1','quote':'Preuve'}]
        blocks=public_blocks(self.article,self.citations,self.facts)
        self.review={'articleSha256':digest(self.article),'blocksSha256':digest(blocks),'supported':False,'issues':[{'id':'description','issue':'Unsupported uniqueness'}],'checks':[{'id':b['id'],'supported':b['id']!='description','issues':[] if b['id']!='description' else ['Unsupported uniqueness']} for b in blocks]}
    def apply(self,changes):return apply_corrections(self.article,self.citations,self.facts,self.review,{'changes':changes})
    def test_only_failed_block_changes_and_original_survives(self):
        before=copy.deepcopy(self.article);updated=self.apply([{'id':'description','text':'Description documentée'}])
        self.assertEqual(self.article,before);self.assertEqual(updated['sections'],before['sections'])
        self.assertEqual(updated['description'],'Description documentée')
    def test_unflagged_block_cannot_be_rewritten(self):
        with self.assertRaisesRegex(ValueError,'unapproved_block'):self.apply([{'id':'title','text':'Autre titre'}])
    def test_missing_correction_cannot_advance(self):
        with self.assertRaisesRegex(ValueError,'missing_failed_block'):self.apply([])
    def test_stale_review_does_not_apply(self):
        self.article['title']='Changed'
        with self.assertRaisesRegex(ValueError,'stale_review'):self.apply([{'id':'description','text':'Correction'}])
    def test_metadata_cannot_be_deleted(self):
        with self.assertRaisesRegex(ValueError,'revision_text'):self.apply([{'id':'description','text':None}])

    def test_source_change_blocks_before_inference(self):
        import datetime as dt
        from guide_revision import revise
        self.article['sources']=[{'url':'https://official.example/page','label':'Official'}]
        self.review['articleSha256']=digest(self.article)
        proposal={'article':self.article,'facts':self.facts,'citations':self.citations,'sourceManifest':[{'url':'https://official.example/page','sha256':'expected'}]}
        def fail(*args,**kwargs):raise AssertionError('Inference must not run')
        with self.assertRaisesRegex(ValueError,'source_changed'):
            revise(proposal,self.review,'',[],dt.datetime(2026,10,12,tzinfo=dt.timezone.utc),fail,lambda url:{'sha256':'changed'})
