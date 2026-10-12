"""Persist at most one eligible voice selection, without promotion or publication."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import auto_select
import stock
import transcribe_review as asr


def write_once(path,raw):
    if path.is_symlink():raise ValueError('symlink')
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('existing_decision_conflict')
        return
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.voice-decision-',delete=False) as f:
        temporary=Path(f.name);f.write(raw);f.flush();os.fsync(f.fileno())
    try:os.link(temporary,path)
    finally:temporary.unlink()


def run(root,now,evaluator=auto_select.evaluate):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','changed':False}
    root=Path(root);original=root/'voice-stock';revisions=root/'voice-revisions';reports=root/'voice-reviews'
    for p in (root,original,revisions,reports,reports/'revisions'):
        if p.is_symlink():raise ValueError('symlink')
    families=sorted(revisions.iterdir()) if revisions.exists() else []
    if len(families)>16:raise ValueError('revision_bound')
    for p in families:
        if p.is_symlink() or not p.is_dir() or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',p.name):raise ValueError('revision_path')
    entries=[];counts={v:0 for v in asr.VOICES};pending=[];skipped=[]
    for source,destination in [(original,reports)]+[(p,reports/'revisions'/p.name) for p in families]:
        if not source.exists():continue
        if destination.is_symlink():raise ValueError('symlink')
        for candidate in sorted(source.iterdir()):
            if candidate.is_symlink() or not candidate.is_dir() or not re.fullmatch(r'reel-article-[a-z0-9-]+',candidate.name):raise ValueError('stock_path')
            entries.append(candidate)
            if len(entries)>64:raise ValueError('stock_bound')
            hold=candidate/'selection-hold.json'
            record_path=candidate/'stock.json';selection=candidate/'selection.json';transcription=candidate/'transcription.json';report=destination/(candidate.name+'.json')
            for path in (record_path,selection,transcription,report,hold):
                if path.is_symlink():raise ValueError('symlink')
            record=json.loads(record_path.read_text())
            if record['id']!=candidate.name:raise ValueError('identity_changed')
            if selection.exists():
                selected=json.loads(selection.read_text())
                if (selected['contentId']!=record['id'] or selected['stockSha256']!=stock.sha(record_path.read_bytes()) or selected['transcriptionSha256']!=stock.sha(transcription.read_bytes()) or selected['validUntil']!=record['validUntil'] or selected['status']!='selected_for_promotion_qualification' or selected['voice'] not in counts):raise ValueError('existing_selection_conflict')
                counts[selected['voice']]+=1;skipped.append({'id':candidate.name,'reason':'already_selected'});continue
            if now>=dt.datetime.fromisoformat(record['validUntil']):continue
            if not report.exists():continue
            if asr.recorded_model(candidate,record)!=(asr.MEDIUM_MODEL,asr.MEDIUM_REVISION):continue
            if hold.exists():
                held=json.loads(hold.read_text())
                if held['stockSha256']!=stock.sha(record_path.read_bytes()) or held['transcriptionSha256']!=stock.sha(report.read_bytes()):raise ValueError('existing_hold_conflict')
                skipped.append({'id':candidate.name,'reason':'held_unchanged'});continue
            pending.append((candidate,report))
    if not pending:return {'status':'no_unselected_qualified_stock','changed':False,'skipped':skipped}
    candidate,report=pending[0]
    preferred=min(counts,key=lambda voice:(counts[voice],voice))
    selected=evaluator(candidate,report,now,preferred=preferred)
    if selected['status']!='selected_for_promotion_qualification':
        if selected['status']!='held_transcription_ambiguities':raise ValueError('unexpected_evaluation_status')
        held={'status':selected['status'],'id':candidate.name,'checkedAt':now.isoformat(),'stockSha256':stock.sha((candidate/'stock.json').read_bytes()),'transcriptionSha256':stock.sha(report.read_bytes()),'publicationApproved':False}
        write_once(candidate/'selection-hold.json',(json.dumps(held,indent=2)+'\n').encode())
        return {'status':selected['status'],'id':candidate.name,'changed':True,'publicationAttempted':False}
    if dt.datetime.now(dt.timezone.utc)>=min(stock.STOP,dt.datetime.fromisoformat(selected['validUntil'])):raise ValueError('expired_during_selection')
    # Transcript first: an interrupted write resumes only with identical bytes.
    # The selection is the commit marker, published atomically and exclusively.
    write_once(candidate/'transcription.json',report.read_bytes())
    write_once(candidate/'selection.json',(json.dumps(selected,ensure_ascii=False,indent=2)+'\n').encode())
    return {'status':'selection_preserved_not_published','changed':True,'id':candidate.name,'voice':selected['voice'],'publicationAttempted':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(run(args.root,dt.datetime.now(dt.timezone.utc)),ensure_ascii=False))
