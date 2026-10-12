import unittest
from guide_review import public_blocks,validate_checks,assess_blocks

class GuideReviewTests(unittest.TestCase):
    def setUp(self):
        self.blocks=[{'id':'title','text':'A description','evidence':['f1']},{'id':'paragraph','text':'A paragraph','evidence':['f1']}]
        self.accept={'checks':[{'id':b['id'],'supported':True,'issues':[]} for b in self.blocks]}
    def test_missing_public_block_is_not_approval(self):
        self.accept['checks'].pop()
        with self.assertRaisesRegex(ValueError,'incomplete_coverage'):validate_checks(self.accept,self.blocks)
    def test_duplicate_vote_cannot_replace_missing_block(self):
        self.accept['checks'][1]=self.accept['checks'][0]
        with self.assertRaisesRegex(ValueError,'identity'):validate_checks(self.accept,self.blocks)
    def test_one_unsupported_block_holds_whole_article(self):
        self.accept['checks'][0].update(supported=False,issues=['Unsupported uniqueness'])
        self.assertFalse(validate_checks(self.accept,self.blocks)['supported'])
    def test_acceptance_with_objection_is_rejected(self):
        self.accept['checks'][0]['issues']=['Still uncertain']
        with self.assertRaisesRegex(ValueError,'contradiction'):validate_checks(self.accept,self.blocks)
    def test_unknown_evidence_stops_before_provider(self):
        def fail(*args):raise AssertionError('Unexpected inference')
        with self.assertRaisesRegex(ValueError,'unknown_evidence'):assess_blocks(self.blocks,[],'',fail)
    def test_all_public_fields_are_covered(self):
        article={'title':'T','shortTitle':'S','description':'D','summary':'R','sections':[{'id':'a','title':'A','paragraphs':['P','Q']}],'faq':[{'question':'?','answer':'!'}]}
        blocks=public_blocks(article,{'a':['f1'],'faq-0':['f1']},[{'id':'f1'}])
        self.assertEqual(len(blocks),9)
        self.assertEqual({b['text'] for b in blocks},{'T','S','D','R','A','P','Q','?','!'})

    def test_batched_review_preserves_complete_coverage(self):
        import json
        blocks=[{'id':'p'+str(i),'text':'A paragraph','evidence':['f1']} for i in range(11)]
        sizes=[]
        def invoke(messages,*args):
            packet=json.loads(messages[1]['content']);sizes.append(len(packet['blocks']))
            return {'checks':[{'id':b['id'],'supported':True,'issues':[]} for b in packet['blocks']]},{}
        result,usage=assess_blocks(blocks,[{'id':'f1','quote':'Evidence'}],'',invoke)
        self.assertEqual(sizes,[5,5,1]);self.assertEqual(usage['calls'],3)
        self.assertEqual(len(result['checks']),11)

    def test_primary_context_is_sent_without_shortened_paraphrase(self):
        import json
        def invoke(messages,*args):
            packet=json.loads(messages[1]['content'])
            self.assertEqual(packet['evidence'],[{'id':'f1','text':'Full source excerpt with the museum address.'}])
            return self.accept,{}
        assess_blocks(self.blocks,[{'id':'f1','fact':'Short paraphrase','quote':'Short quote','sourceContext':{'excerpt':'Full source excerpt with the museum address.'}}],'',invoke)

    def test_editorial_policy_holds_unsupported_uniqueness_even_if_model_accepts(self):
        self.blocks[0]['text']='Un piano mécanique unique.'
        result,_=assess_blocks(self.blocks,[{'id':'f1','quote':'Un piano mécanique.'}],'',lambda *args:(self.accept,{}))
        self.assertTrue(result['modelSupported'])
        self.assertFalse(result['supported'])
        self.assertEqual(result['policyIssues'][0]['id'],'title')
