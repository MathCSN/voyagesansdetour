"""Two bounded reviewer comparisons on labelled synthetic regression cases."""
import datetime as dt
import json
import os
from pathlib import Path
from functools import partial
from source_draft import call,HARD_STOP,MODEL,require
from guide_review import assess_blocks

# Synthetic minimal evidence, not new travel claims or publication material.
FACTS=[
 {'id':'f1','quote':'Para aceder aos pisos superiores o visitante é convidado a subir a escada em espiral.'},
 {'id':'f2','quote':'Le musée présente un piano mécanique du XIXe siècle.'},
 {'id':'f3','quote':'Une galerie d’images présente plusieurs artistes.'},
 {'id':'f4','quote':'Le billet donne accès au parc uniquement, sans visite intérieure du palais.'},
 {'id':'f5','quote':'Des excursions sont proposées certains samedis de juillet et août.'},
]
CASES=[
 ('stair_bad','Les étages sont accessibles par une échelle en spirale.','f1',False),
 ('stair_good','Un escalier en spirale permet de rejoindre les étages.','f1',True),
 ('unique_bad','Découvrez un piano mécanique unique.','f2',False),
 ('piano_good','Le musée présente un piano mécanique du XIXe siècle.','f2',True),
 ('portraits_bad','Une galerie de portraits présente plusieurs artistes.','f3',False),
 ('images_good','Une galerie d’images présente plusieurs artistes.','f3',True),
 ('access_bad','Le billet comprend la visite intérieure du palais.','f4',False),
 ('access_good','Le billet concerne le parc et exclut l’intérieur du palais.','f4',True),
 ('frequency_bad','Les excursions ont lieu tous les samedis en été.','f5',False),
 ('frequency_good','Des excursions sont proposées certains samedis de juillet et août.','f5',True),
]

def main():
    now=dt.datetime.now(dt.timezone.utc);out=Path(os.environ['REPORT_DIR']);out.mkdir(parents=True,exist_ok=True)
    report={'observedAt':now.isoformat(),'status':'not_started','callsAttempted':0,'maxCalls':2,'maxOutputTokensTotal':5200,'publicationAttempted':False,'models':[]}
    try:
        require(now<HARD_STOP,'authorization_period_ended')
        token=os.environ.get('CLOUDFLARE_WORKERS_AI_TOKEN','');require(bool(token),'missing_secret')
        blocks=[{'id':i,'text':text,'evidence':[ref]} for i,text,ref,_ in CASES]
        for model in (MODEL,'@cf/qwen/qwen3-30b-a3b-fp8'):
            report['callsAttempted']+=1
            result,usage=assess_blocks(blocks,FACTS,token,partial(call,model=model))
            observed={c['id']:c['supported'] for c in result['checks']}
            failures=[i for i,_,_,expected in CASES if observed[i]!=expected]
            report['models'].append({'model':model,'passed':10-len(failures),'total':10,'failures':failures,'review':result,'usage':usage})
        report['status']='evaluated'
    except Exception as error:report.update(status='held_no_retry',errorType=type(error).__name__)
    (out/'guide-review-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'callsAttempted':report['callsAttempted']}))
    return 1 if report['status']=='held_no_retry' else 0
if __name__=='__main__':raise SystemExit(main())
