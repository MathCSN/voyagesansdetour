import copy
import datetime as dt
import unittest
import editorial_update as u
import editorial_queue as q

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,12,tzinfo=dt.timezone.utc)
        self.url='https://www.cp.pt/info/en/w/left-luggage'
        self.text='Time limit - 24 hours. Node: vmusitecpprd1:8085: Hidden'
        self.articles=[{'slug':'guide','sections':[{'id':'lockers','paragraphs':['Keep the original conditions.']}],'sources':[{'url':self.url}]}]
        self.ledger={'schemaVersion':1,'updates':[]}
        self.patch={'schemaVersion':1,'id':'guide-lockers-v1','slug':'guide','baseArticleSha256':q.digest(self.articles[0]),'sectionId':'lockers','afterParagraphSha256':q.digest('Keep the original conditions.'),'paragraph':'Pour les consignes présentées par CP, la durée de dépôt est limitée à 24 heures.','sources':[{'url':self.url,'sha256':u.source_digest(self.url,self.text),'normalization':'visible-text-cp-node-v1'}],'reviewedAt':'2026-10-12T00:00:00Z','validUntil':'2026-10-13T00:00:00Z','reviewMethod':'agent-source-review-v1'}
        self.patch['approvalSha256']=u.approval_hash(self.patch)
    def apply(self,articles=None,ledger=None):
        return u.apply_update(articles or self.articles,ledger or self.ledger,self.patch,self.now,lambda _: {'text':self.text})
    def test_preserves_original_and_applies_once(self):
        original=copy.deepcopy(self.articles); articles,ledger,changed=self.apply()
        self.assertTrue(changed);self.assertEqual(self.articles,original)
        self.assertEqual(articles[0]['sections'][0]['paragraphs'][0],'Keep the original conditions.')
        self.assertFalse(self.apply(articles,ledger)[2])
    def test_base_conflict_does_not_overwrite(self):
        self.articles[0]['sections'][0]['paragraphs'].append('A newer edit')
        with self.assertRaisesRegex(ValueError,'Base article changed'):self.apply()
    def test_source_condition_change_rejected(self):
        self.text=self.text.replace('24 hours','12 hours')
        with self.assertRaisesRegex(ValueError,'source changed'):self.apply()
    def test_backend_node_change_is_not_a_travel_change(self):
        self.text=self.text.replace('prd1','prd2')
        self.assertTrue(self.apply()[2])
    def test_changed_patch_rejected(self):
        self.patch['paragraph']+=' Extra claim.'
        with self.assertRaisesRegex(ValueError,'changed after review'):self.apply()
    def test_expired_review_rejected(self):
        self.now+=dt.timedelta(days=2)
        with self.assertRaisesRegex(ValueError,'expired'):self.apply()
    def test_untracked_existing_paragraph_is_not_applied_again(self):
        self.articles[0]['sections'][0]['paragraphs'].append(self.patch['paragraph'])
        self.patch['baseArticleSha256']=q.digest(self.articles[0]);self.patch['approvalSha256']=u.approval_hash(self.patch)
        with self.assertRaisesRegex(ValueError,'already exists'):self.apply()

class ReceiptTests(UpdateTests):
    def test_missing_public_paragraph_does_not_confirm(self):
        articles,ledger,_=self.apply()
        with self.assertRaisesRegex(ValueError,'missing or duplicated'):
            u.record_receipt(articles,ledger,self.patch,b'<html>Old page</html>',self.now)
        self.assertIsNone(ledger['updates'][0]['receipt'])
    def test_exact_public_paragraph_confirms_once(self):
        articles,ledger,_=self.apply()
        body=('<p>'+self.patch['paragraph']+'</p>').encode()
        result=u.record_receipt(articles,ledger,self.patch,body,self.now)
        self.assertEqual(result['updates'][0]['receipt']['verification'],'exact-paragraph-presence-v1')
        self.assertEqual(u.record_receipt(articles,result,self.patch,body,self.now),result)
    def test_changed_article_blocks_receipt(self):
        articles,ledger,_=self.apply();articles[0]['updatedOn']='2026-10-13'
        with self.assertRaisesRegex(ValueError,'changed before update confirmation'):
            u.record_receipt(articles,ledger,self.patch,b'',self.now)


class PendingUpdateTests(UpdateTests):
    def test_pending_update_is_recoverable_without_reapplication(self):
        articles,ledger,_=self.apply()
        self.assertEqual(u.pending_patches(articles,ledger,lambda _:self.patch,self.now),[self.patch])

    def test_expired_pending_update_blocks_deployment(self):
        articles,ledger,_=self.apply()
        with self.assertRaisesRegex(ValueError,'expired'):
            u.pending_patches(articles,ledger,lambda _:self.patch,self.now+dt.timedelta(days=1))

    def test_changed_pending_article_blocks_deployment(self):
        articles,ledger,_=self.apply();articles[0]['sections'][0]['paragraphs'].append('Other edit')
        with self.assertRaisesRegex(ValueError,'article changed'):
            u.pending_patches(articles,ledger,lambda _:self.patch,self.now)

    def test_confirmed_history_does_not_need_old_approval(self):
        articles,ledger,_=self.apply();ledger['updates'][0]['receipt']={'verified':True}
        def fail(_):raise AssertionError('confirmed history must not be reopened')
        self.assertEqual(u.pending_patches(articles,ledger,fail,self.now+dt.timedelta(days=10)),[])

    def test_pending_patch_tampering_blocks_deployment(self):
        articles,ledger,_=self.apply();self.patch['paragraph']+=' Altered'
        with self.assertRaisesRegex(ValueError,'approval conflict'):
            u.pending_patches(articles,ledger,lambda _:self.patch,self.now)
