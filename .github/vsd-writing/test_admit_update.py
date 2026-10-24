import copy
import datetime as dt
import unittest
import admit_update as a
import editorial_queue as q
import editorial_update as u

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,12,10,tzinfo=q.UTC)
        self.url='https://www.cp.pt/info/en/w/left-luggage'
        self.text='Time limit - 24 hours. Opening hours vary by station.'
        self.article={'slug':'guide','publishedOn':'2026-10-12','sources':[{'url':self.url,'label':'CP'}],'sections':[{'id':'bagages','paragraphs':['Existing opening conditions.']}]}
        self.fact={'id':'c1','fact':'La durée maximale est de 24 heures.','quote':'Time limit - 24 hours.','source':0,'sourceContext':{'url':self.url,'label':'CP','excerpt':self.text}}
        self.proposal={'schemaVersion':2,'status':'update_ready_for_pilot_review','publicationApproved':False,'guideSlug':'guide','baseArticleSha256':q.digest(self.article),'facts':[self.fact],'factsSha256':q.digest([self.fact]),'additions':[{'targetSectionId':'bagages','title':'Consignes CP','claims':['c1'],'paragraph':'Pour les consignes présentées par CP, la durée de dépôt est limitée à 24 heures.'}],'sourceManifest':[{'url':self.url,'normalizedSha256':u.source_digest(self.url,self.text)}],'review':{'supported':True,'issues':[],'checkedClaimIds':['c1']}}
        self.entailment={'checks':[{'id':'c1','entailed':True,'unsupportedDetails':[]}]}
        self.novelty={'decisions':[{'id':'c1','supported':True,'newInformation':True,'useful':True}]}
        self.queue={'drafts':[],'promotions':[]};self.ledger={'schemaVersion':1,'updates':[]}
    def fetch(self,url):return {'text':self.text}
    def prepare(self):return a.prepare(self.proposal,self.entailment,self.novelty,q.iso(self.now),self.article,self.now,self.fetch)
    def test_grounded_proposal_applies_once_and_keeps_evidence(self):
        patch=self.prepare()
        articles,ledger,changed=u.apply_update([self.article],self.ledger,patch,self.now,self.fetch)
        self.assertTrue(changed);self.assertEqual(patch['reviewMethod'],'source-grounded-model-review-v1')
        self.assertEqual(articles[0]['sections'][0]['paragraphs'][0],'Existing opening conditions.')
        self.assertFalse(u.apply_update(articles,ledger,patch,self.now,self.fetch)[2])
    def test_changed_source_blocks_admission(self):
        self.text+=' Changed condition.'
        with self.assertRaisesRegex(ValueError,'source changed'):self.prepare()
    def test_rejected_entailment_blocks_admission(self):
        self.entailment['checks'][0]['entailed']=False
        with self.assertRaisesRegex(ValueError,'not approved'):self.prepare()
    def test_non_novel_fact_blocks_admission(self):
        self.novelty['decisions'][0]['newInformation']=False
        with self.assertRaisesRegex(ValueError,'not novel'):self.prepare()
    def test_changed_quote_cannot_use_old_reviews(self):
        self.proposal['facts'][0]['quote']='This quotation is not in the source.'
        self.proposal['factsSha256']=q.digest(self.proposal['facts'])
        patch=self.prepare()
        with self.assertRaisesRegex(ValueError,'quote absent'):
            u.apply_update([self.article],self.ledger,patch,self.now,self.fetch)
    def test_stale_review_rejected(self):
        with self.assertRaisesRegex(ValueError,'stale'):
            a.prepare(self.proposal,self.entailment,self.novelty,q.iso(self.now-dt.timedelta(hours=3)),self.article,self.now,self.fetch)
    def test_recent_publication_prevents_update(self):
        self.article['publishedOn']='2026-12-09'
        self.assertFalse(a.cadence_open([self.article],self.queue,self.ledger,self.now))
    def test_reserved_guide_takes_priority(self):
        self.queue['drafts']=[{'releaseAt':'2026-12-15T08:00:00Z'}]
        self.assertFalse(a.cadence_open([self.article],self.queue,self.ledger,self.now))
    def test_weekly_cadence_reopens_after_seven_days(self):
        self.article['publishedOn']='2026-12-02'
        self.assertTrue(a.cadence_open([self.article],self.queue,self.ledger,self.now))
        self.queue['drafts']=[{'releaseAt':'2026-12-20T08:00:00Z'}]
        self.assertTrue(a.cadence_open([self.article],self.queue,self.ledger,self.now))
    def test_uncertain_previous_update_prevents_new_one(self):
        self.ledger['updates']=[{'receipt':None}]
        self.assertFalse(a.cadence_open([self.article],self.queue,self.ledger,self.now))
    def test_free_slot_can_accept_update(self):
        self.assertTrue(a.cadence_open([self.article],self.queue,self.ledger,self.now))
    def test_authorization_end_stops_admission(self):
        self.assertFalse(a.cadence_open([self.article],self.queue,self.ledger,dt.datetime(2027,9,15,tzinfo=q.UTC)))

    def test_legacy_launch_article_without_date_is_supported(self):
        del self.article['publishedOn']
        self.assertTrue(a.cadence_open([self.article],self.queue,self.ledger,self.now))
