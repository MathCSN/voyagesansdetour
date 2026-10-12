import unittest
from entailment import validate_checks
class EntailmentTests(unittest.TestCase):
    def test_missing_claim_rejected(self):
        with self.assertRaisesRegex(ValueError,'entailment_count'):
            validate_checks({'checks':[]},[{'id':'c1'}])
    def test_positive_with_unsupported_detail_rejected(self):
        with self.assertRaisesRegex(ValueError,'entailment_contradiction'):
            validate_checks({'checks':[{'id':'c1','entailed':True,'unsupportedDetails':['cafes absent']} ]},[{'id':'c1'}])
    def test_string_true_is_not_boolean(self):
        with self.assertRaisesRegex(ValueError,'entailment_types'):
            validate_checks({'checks':[{'id':'c1','entailed':'true','unsupportedDetails':[]} ]},[{'id':'c1'}])
    def test_rejected_claim_not_returned(self):
        self.assertEqual(validate_checks({'checks':[{'id':'c1','entailed':False,'unsupportedDetails':['not proven']}]},[{'id':'c1'}]),set())
