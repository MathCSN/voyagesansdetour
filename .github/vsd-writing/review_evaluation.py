"""Live, labelled critic evaluation. No publication and no automatic retry."""
import datetime as dt
import json
import os
from pathlib import Path
from source_draft import call, check_review, REVIEW_INSTRUCTION, HARD_STOP, require

CASES = [
 {'id':'car_ban_does_not_prove_walking','expected':False,
  'fact':'L’accès à Pena depuis le centre historique n’est pas possible en voiture privée.',
  'quote':'access to Pena from the Historic Center of Sintra is not possible by private car',
  'paragraph':'Vous pouvez rejoindre le palais de Pena à pied depuis le centre historique en vingt minutes, sur un trajet accessible aux poussettes.'},
 {'id':'palace_time_not_park_time','expected':True,
  'fact':'Le créneau du billet est celui de l’entrée au palais, pas au parc.',
  'quote':'The time indicated on your ticket corresponds to the time of entry in the Palace and not to the time of entry in the Park.',
  'paragraph':'Le créneau indiqué sur votre billet correspond à l’entrée au palais. Il ne correspond pas à votre heure d’arrivée à l’entrée du parc.'},
]

def main():
    out=Path(os.environ['REPORT_DIR']);out.mkdir(parents=True,exist_ok=True)
    report={'observedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'cases':[],
            'publicationAttempted':False,'callsAttempted':0,'maxCalls':2,'status':'not_started'}
    try:
        require(dt.datetime.now(dt.timezone.utc)<HARD_STOP,'authorization_period_ended')
        token=os.environ.get('CLOUDFLARE_WORKERS_AI_TOKEN','');require(bool(token),'missing_secret')
        for case in CASES:
            facts=[{'id':'c1','fact':case['fact'],'quote':case['quote'],'source':0}]
            draft={'title':'Préparer sa visite à Pena','claims':facts,'sections':[{'title':'Accès','paragraph':case['paragraph'],'claims':['c1']}]}
            report['callsAttempted']+=1
            review,usage=call([{'role':'system','content':REVIEW_INSTRUCTION},
                {'role':'user','content':json.dumps({'verifiedFacts':facts,'draft':draft},ensure_ascii=False)}],650,token)
            check_review(review,draft)
            passed=review['supported']==case['expected']
            if not case['expected']: passed=passed and bool(review['issues'])
            report['cases'].append({'id':case['id'],'expectedSupported':case['expected'],
                                    'review':review,'usage':usage,'passed':passed})
        report['status']='evaluation_passed' if all(c['passed'] for c in report['cases']) else 'evaluation_failed'
    except Exception as error:
        report.update(status='evaluation_incomplete',errorType=type(error).__name__)
    report['limitation']='Two targeted cases only; not a guarantee of universal factual accuracy.'
    (out/'critic-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'callsAttempted':report['callsAttempted']}))
    return 0 if report['status']=='evaluation_passed' else 1
if __name__=='__main__':raise SystemExit(main())
