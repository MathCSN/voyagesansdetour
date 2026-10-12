import datetime as dt
import json
import os
from pathlib import Path
from source_draft import HARD_STOP, require
from entailment import assess

# Labels are not sent to the model. These cover observed false positives and
# two positive controls; passing this small set is not a universal guarantee.
CASES=[
 {'id':'shops','fact':'Chiado comprend des studios, des magasins originaux et des cafés.',
  'quote':'Chiado, with their eclectic mix of contemporary and traditional stores','expected':False},
 {'id':'districts','fact':'Le site propose des informations sur Alfama, Chiado et la Baixa.',
  'quote':'The oldest and most traditional neighbourhood in Lisbon, with cobbled lanes and alleys and steep, gruelling inclines','expected':False},
 {'id':'luggage','fact':'Il est recommandé de vérifier le trajet à pied avant de réserver un logement, surtout avec un bagage lourd.',
  'quote':'the tangle of streets punctuated by rails below and flower boxes above has to be discovered on foot','expected':False},
 {'id':'ticket','fact':'Le créneau du billet correspond à l’entrée au palais, pas au parc.',
  'quote':'The time indicated on your ticket corresponds to the time of entry in the Palace and not to the time of entry in the Park.','expected':True},
 {'id':'train','fact':'La ligne CP Lisbonne–Sintra part notamment de Rossio, Oriente et Entrecampos.',
  'quote':'Lisbon > Sintra: Train (CP) – Sintra Line (Departure stations: Oriente; Rossio; Entrecampos)','expected':True},
 {'id':'frequency','fact':'Les trains pour Sintra partent de Rossio toutes les quinze minutes.',
  'quote':'Lisbon > Sintra: Train (CP) – Sintra Line (Departure stations: Oriente; Rossio; Entrecampos)','expected':False},
 {'id':'included','fact':'Un billet pour le parc inclut automatiquement l’entrée au palais.',
  'quote':'The time indicated on your ticket corresponds to the time of entry in the Palace and not to the time of entry in the Park.','expected':False},
 {'id':'exact_duration','fact':'Le trajet de l’entrée du parc au palais dure toujours exactement trente minutes.',
  'quote':'the journey from the entrance to the park to the entrance of the palace interior route takes about 30 minutes','expected':False},
 {'id':'approx_duration','fact':'L’exploitant indique un trajet d’environ trente minutes de l’entrée du parc à l’entrée du parcours intérieur du palais.',
  'quote':'the journey from the entrance to the park to the entrance of the palace interior route takes about 30 minutes','expected':True},

]

def main():
    out=Path(os.environ['REPORT_DIR']);out.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(dt.timezone.utc)
    report={'observedAt':now.isoformat(),'publicationAttempted':False,'callsAttempted':0,'maxCalls':1,'status':'not_started'}
    try:
        require(now<HARD_STOP,'authorization_period_ended')
        token=os.environ.get('CLOUDFLARE_WORKERS_AI_TOKEN','');require(bool(token),'missing_secret')
        report['callsAttempted']=1
        result,usage,accepted=assess(CASES,token)
        report.update(result=result,usage=usage)
        report['cases']=[{'id':c['id'],'expected':c['expected'],'passed':(c['id'] in accepted)==c['expected']} for c in CASES]
        report['status']='evaluation_passed' if all(c['passed'] for c in report['cases']) else 'evaluation_failed'
    except Exception as error:
        report.update(status='evaluation_incomplete',errorType=type(error).__name__)
    report['limitation']='Nine cases including four additional generalization controls; not unrestricted publication approval.'
    (out/'entailment-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status']}))
    return 0 if report['status']=='evaluation_passed' else 1
if __name__=='__main__':raise SystemExit(main())
