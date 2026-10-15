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
    def test_revision_cannot_expand_metadata_into_an_article(self):
        with self.assertRaisesRegex(ValueError,'metadata_length'):
            self.apply([{'id':'description','text':'x'*181}])
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

class IsolatedEvidenceTests(unittest.TestCase):
    def test_other_blocks_evidence_and_feedback_are_not_exposed(self):
        from guide_revision import revision_packets
        blocks=[{'id':'a','text':'A','evidence':['f1']},{'id':'b','text':'B','evidence':['f2']}]
        facts=[{'id':'f1','quote':'first source'},{'id':'f2','quote':'second source'}]
        review={'issues':[{'id':'a','issue':'first issue'},{'id':'b','issue':'second issue'}]}
        packets=revision_packets(blocks,facts,review)
        self.assertEqual(len(packets),2)
        for packet,block,fact in zip(packets,blocks,facts):
            self.assertEqual([x['id'] for x in packet['evidence']],[fact['id']])
            self.assertEqual([x['id'] for x in packet['issues']],[block['id']])
            self.assertEqual(len(packet['failedBlocks']),1)
    def test_missing_referenced_evidence_blocks_revision(self):
        from guide_revision import revision_packets
        with self.assertRaisesRegex(ValueError,'missing_evidence'):
            revision_packets([{'id':'a','evidence':['absent']}],[],{'issues':[{'id':'a'}]})
    def test_excessive_revision_is_held_before_model_calls(self):
        from guide_revision import revision_packets
        with self.assertRaisesRegex(ValueError,'block_budget'):
            revision_packets([],[],{'issues':[{'id':str(i)} for i in range(9)]})

class BoundedFormatRepairTests(unittest.TestCase):
    def setUp(self):
        self.packet={'failedBlocks':[{'id':'description','maximumCharacters':180,'evidence':['f1']}], 'evidence':[{'id':'f1','text':'Museum fact'}]}
    def run_case(self,texts,allow=True):
        from guide_revision import correct_block
        calls=[]
        def invoke(messages,*args,**kwargs):
            calls.append(copy.deepcopy(messages))
            return {'changes':[{'id':'description','text':texts[len(calls)-1]}]},{}
        return correct_block(self.packet,'Instructions','',invoke,allow),calls
    def test_overlong_response_is_repaired_without_changing_evidence(self):
        (change,attempts),calls=self.run_case(['x'*245,'Une description courte et documentée.'])
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][:2],calls[1][:2])
        self.assertEqual(len(attempts),2)
        self.assertEqual(change['text'],'Une description courte et documentée.')
        self.assertIn('245',calls[1][-1]['content'])
    def test_valid_response_needs_no_extra_call(self):
        (_,attempts),calls=self.run_case(['Description documentée'])
        self.assertEqual(len(calls),1)
    def test_second_invalid_response_holds(self):
        with self.assertRaisesRegex(ValueError,'revision_block_length'):
            self.run_case(['x'*245,'x'*181])
    def test_exhausted_shared_repair_budget_holds_immediately(self):
        with self.assertRaisesRegex(ValueError,'revision_block_length'):
            self.run_case(['x'*245],False)
    def test_repair_cannot_change_another_block(self):
        from guide_revision import correct_block
        outputs=iter([{'id':'description','text':'x'*245},{'id':'title','text':'Short'}])
        with self.assertRaisesRegex(ValueError,'revision_cross_block_change'):
            correct_block(self.packet,'Instructions','',lambda *a,**k:({'changes':[next(outputs)]},{}))

class ResumeRevisionTests(unittest.TestCase):
    setUp=RevisionTests.setUp
    def proposal(self):
        self.review['factsSha256']=digest(self.facts)
        return {'status':'revised_guide_held','publicationApproved':False,'article':self.article,'facts':self.facts,'citations':self.citations,'blockReview':self.review,'revisionDepth':1}
    def test_resume_uses_current_bound_review(self):
        from guide_revision import resume_revision
        p=self.proposal();actual,review,depth=resume_revision(p)
        self.assertIs(actual,p);self.assertIs(review,self.review);self.assertEqual(depth,1)
    def test_changed_facts_are_rejected(self):
        from guide_revision import resume_revision
        p=self.proposal();p['facts'][0]['quote']='Different'
        with self.assertRaisesRegex(ValueError,'resume_binding'):resume_revision(p)
    def test_depth_limit_prevents_unbounded_chain(self):
        from guide_revision import resume_revision
        p=self.proposal();p['revisionDepth']=3
        with self.assertRaisesRegex(ValueError,'depth_budget'):resume_revision(p)
    def test_ready_proposal_is_not_rewritten(self):
        from guide_revision import resume_revision
        p=self.proposal();p['status']='revised_guide_ready_for_pilot_review'
        with self.assertRaisesRegex(ValueError,'resume_status'):resume_revision(p)

class EditorialHoldTests(unittest.TestCase):
    setUp=RevisionTests.setUp
    def test_additive_hold_preserves_original_and_existing_rejection(self):
        from guide_revision import add_editorial_holds
        proposal={'article':self.article,'facts':self.facts,'citations':self.citations}
        before=copy.deepcopy(self.review)
        hold={'origin':'editorial_review','articleSha256':digest(self.article),'factsSha256':digest(self.facts),'issues':[{'id':'title','issue':'Ambiguous wording'}]}
        updated=add_editorial_holds(proposal,self.review,hold)
        self.assertEqual(self.review,before)
        self.assertFalse(updated['supported'])
        self.assertEqual({x['id'] for x in updated['issues']},{'description','title'})
        hold['factsSha256']='stale'
        with self.assertRaisesRegex(ValueError,'editorial_binding'):add_editorial_holds(proposal,self.review,hold)
    def test_hold_cannot_invent_a_block(self):
        from guide_revision import add_editorial_holds
        proposal={'article':self.article,'facts':self.facts,'citations':self.citations}
        hold={'origin':'editorial_review','articleSha256':digest(self.article),'factsSha256':digest(self.facts),'issues':[{'id':'missing','issue':'No'}]}
        with self.assertRaisesRegex(ValueError,'editorial_issue'):add_editorial_holds(proposal,self.review,hold)
