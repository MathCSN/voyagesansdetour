import copy
import datetime as dt
import unittest
from unittest.mock import Mock
import guide_admission as gate
import guide_review
import test_guide_draft

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        test_guide_draft.GuideTests.setUp(self)
        article,citations=__import__('guide_draft').validate_article_output(self.value,self.topic,self.facts,[],self.now)
        self.document='Description documentée de la collection du musée.'
        for fact in self.facts:
            fact.update(quote=self.document,sourceContext={'url':article['sources'][0]['url'],'excerpt':self.document})
        blocks=guide_review.public_blocks(article,citations,self.facts)
        review=guide_review.validate_checks({'checks':[{'id':b['id'],'supported':True,'issues':[]} for b in blocks]},blocks)
        review['articleSha256']=gate.digest(article)
        review['factsSha256']=gate.digest(self.facts)
        self.proposal={'status':'guide_ready_for_pilot_review','publicationApproved':False,'article':article,'facts':self.facts,'citations':citations,'blockReview':review,'sourceManifest':[{'url':s['url'],'sha256':'a'*64} for s in article['sources']]}
        self.fetch=Mock(return_value={'sha256':'a'*64,'text':self.document})
    def test_acceptance_is_not_publication_or_admission(self):
        result=gate.qualify(self.proposal,[],self.now,self.fetch)
        self.assertEqual(result['status'],'evidence_revalidated_not_admitted')
        self.assertFalse(result['publicationApproved'])
    def test_changed_text_or_partial_review_stops_before_fetch(self):
        for mutate in (lambda p:p['article'].update(title='Autre titre'),lambda p:p['blockReview']['checks'].pop()):
            p=copy.deepcopy(self.proposal);mutate(p)
            with self.assertRaises(ValueError):gate.qualify(p,[],self.now,self.fetch)
        self.fetch.assert_not_called()
    def test_changed_source_or_fabricated_context_stops(self):
        with self.assertRaises(ValueError):gate.qualify(self.proposal,[],self.now,lambda u:{'sha256':'b'*64,'text':self.document})
        self.proposal['facts'][0]['sourceContext']['excerpt']='Inventé'
        with self.assertRaises(ValueError):gate.qualify(self.proposal,[],self.now,self.fetch)
    def test_duplicate_and_expired_review_stop_before_fetch(self):
        with self.assertRaises(ValueError):gate.qualify(self.proposal,[self.proposal['article']],self.now,self.fetch)
        with self.assertRaises(ValueError):gate.qualify(self.proposal,[],self.now+dt.timedelta(days=2),self.fetch)
        self.fetch.assert_not_called()

    def test_modified_fact_invalidates_review_before_source_fetch(self):
        self.proposal['facts'][0]['fact']='Un fait différent et non contrôlé'
        with self.assertRaisesRegex(ValueError,'changed_evidence'):
            gate.qualify(self.proposal,[],self.now,self.fetch)
        self.fetch.assert_not_called()
    def test_only_accepted_bound_evidence_is_persisted(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            held=copy.deepcopy(self.proposal);held['status']='guide_held_by_review'
            self.assertEqual(gate.persist_qualification(held,[],self.now,output,self.fetch),'review_held')
            self.assertEqual(list(output.iterdir()),[])
            self.fetch.assert_not_called()
            gate.persist_qualification(self.proposal,[],self.now,output,self.fetch)
            before=(output/'guide-admission-evidence.json').read_bytes()
            with self.assertRaises(ValueError):gate.persist_qualification(self.proposal,[],self.now,output,self.fetch)
            self.assertEqual(before,(output/'guide-admission-evidence.json').read_bytes())
