"""Two bounded reviewer comparisons on labelled synthetic regression cases."""
import datetime as dt
import json
import os
from pathlib import Path
from functools import partial
from source_draft import call,HARD_STOP,MODEL,require
from guide_review import assess_blocks,assess_article
import editorial_queue as q

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
    report={'observedAt':now.isoformat(),'status':'not_started','callsAttempted':0,'maxCalls':4,'maxOutputTokensTotal':10400,'publicationAttempted':False,'models':[]}
    try:
        require(now<HARD_STOP,'authorization_period_ended')
        token=os.environ.get('CLOUDFLARE_WORKERS_AI_TOKEN','');require(bool(token),'missing_secret')
        # Opaque IDs and mixed ordering prevent expected answers leaking
        # through labels such as good/bad or alternating case positions.
        mixed=[CASES[i] for i in (7,2,9,4,0,6,3,8,1,5)]
        identity={case[0]:'unit-'+str(i+1) for i,case in enumerate(mixed)}
        blocks=[{'id':identity[i],'text':text,'evidence':[ref]} for i,text,ref,_ in mixed]
        proposal_path=Path(os.environ['PROPOSAL_DIR'])/'guide-proposal.json' if os.environ.get('PROPOSAL_DIR') else None
        proposal=q.read_json(proposal_path) if proposal_path else None
        for model in (MODEL,'@cf/qwen/qwen3-30b-a3b-fp8'):
            report['callsAttempted']+=1
            result,usage=assess_blocks(blocks,FACTS,token,partial(call,model=model))
            observed={c['id']:c['supported'] for c in result['checks']}
            failures=[i for i,_,_,expected in CASES if observed[identity[i]]!=expected]
            report['models'].append({'model':model,'passed':10-len(failures),'total':10,'failures':failures,'review':result,'usage':usage})
            if proposal is not None:
                report['callsAttempted']+=1
                full,full_usage=assess_article(proposal['article'],proposal['citations'],proposal['facts'],token,partial(call,model=model))
                report['models'][-1]['fullGuideReview']=full
                report['models'][-1]['fullGuideUsage']=full_usage
        report['status']='evaluated'
    except Exception as error:report.update(status='held_no_retry',errorType=type(error).__name__)
    (out/'guide-review-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'callsAttempted':report['callsAttempted']}))
    return 1 if report['status']=='held_no_retry' else 0
if __name__=='__main__':raise SystemExit(main())
