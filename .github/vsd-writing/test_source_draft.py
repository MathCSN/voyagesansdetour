import copy
import unittest
from source_draft import validate

class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.sources=[{'text':'The palace requires a timed entry ticket. Take the train to Sintra.'}]
        self.draft={'title':'Préparer une visite à Sintra','claims':[
            {'id':'c1','fact':'Le palais demande un billet avec créneau.','source':0,'quote':'The palace requires a timed entry ticket.'},
            {'id':'c2','fact':'Il est possible de prendre le train vers Sintra.','source':0,'quote':'Take the train to Sintra.'}],
            'sections':[{'title':'Préparer son trajet','paragraph':'Une proposition de paragraphe pour la visite. '*4,'claims':['c1','c2']} for _ in range(3)]}
    def test_valid_exact_evidence(self):
        validate(self.draft,self.sources)
    def test_fabricated_quote_rejected(self):
        self.draft['claims'][0]['quote']='The palace is always free for everyone.'
        with self.assertRaisesRegex(ValueError,'quote_not_in_source'):validate(self.draft,self.sources)
    def test_unknown_claim_rejected(self):
        self.draft['sections'][0]['claims']=['invented']
        with self.assertRaisesRegex(ValueError,'section_claims'):validate(self.draft,self.sources)
    def test_unapproved_source_rejected(self):
        self.draft['claims'][0]['source']=-1
        with self.assertRaisesRegex(ValueError,'source_index'):validate(self.draft,self.sources)
    def test_duplicate_claim_rejected(self):
        self.draft['claims'][1]['id']='c1'
        with self.assertRaisesRegex(ValueError,'claim_id'):validate(self.draft,self.sources)

if __name__=='__main__': unittest.main()
