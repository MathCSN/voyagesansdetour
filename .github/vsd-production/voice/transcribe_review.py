"""Independent local ASR check of immutable voice stock, never publication approval."""
import argparse
import datetime as dt
import difflib
import json
from pathlib import Path
import re
import unicodedata

import stock

MODEL='Systran/faster-whisper-small'
REVISION='536b0662742c02347bc0e980a01041f333bce120'
VOICES=('fr_FR-siwis-medium','fr_FR-upmc-medium')
MEDIUM_MODEL='Systran/faster-whisper-medium'
MEDIUM_REVISION='08e178d48790749d25932bbc082711ddcfdfbc4f'


def model_for_receipt(receipt):
    profile=receipt.get('synthesisProfile','original')
    if profile=='original':return MODEL,REVISION
    if profile=='clear-v1':return MEDIUM_MODEL,MEDIUM_REVISION
    raise ValueError('unqualified_synthesis_profile')


def recorded_model(folder,record):
    path=folder/'media/receipt.json'
    if path.is_symlink():raise ValueError('symlink')
    raw=path.read_bytes()
    matches=[r for r in record['files'] if r['file']=='receipt.json']
    if len(matches)!=1 or matches[0]['sha256']!=stock.sha(raw):raise ValueError('receipt_changed')
    return model_for_receipt(json.loads(raw))


def words(text):
    return re.findall(r'[^\W_]+',unicodedata.normalize('NFC',text).casefold(),re.UNICODE)


def compare(expected, actual):
    reference,hypothesis=words(expected),words(actual)
    if not reference:raise ValueError('empty_reference')
    # Preserve every discrepancy, including numbers and names. This is an
    # inspection aid, not a speech-quality or factual correctness verdict.
    differences=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(None,reference,hypothesis,autojunk=False).get_opcodes():
        if tag!='equal':differences.append({'kind':tag,'expected':reference[a:b],'transcribed':hypothesis[c:d]})
    return {'exactNormalizedMatch':reference==hypothesis,'expectedWords':len(reference),
            'transcribedWords':len(hypothesis),'differences':differences}


def review_next(root, output, now, transcriber=None):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','publicationApproved':False}
    root,output=Path(root),Path(output)
    if root.is_symlink() or output.is_symlink():raise ValueError('symlink')
    folders=sorted(root.iterdir())
    if len(folders)>64:raise ValueError('stock_bound')
    for folder in folders:
        if folder.is_symlink() or not folder.is_dir() or not re.fullmatch(r'reel-article-[a-z0-9-]+',folder.name):raise ValueError('stock_path')
        manifest=folder/'stock.json'
        if manifest.is_symlink():raise ValueError('symlink')
        record=json.loads(manifest.read_text())
        if record['id']!=folder.name:raise ValueError('stock_identity')
        report=output/(folder.name+'.json')
        if report.is_symlink():raise ValueError('symlink')
        if report.exists():
            expected_model,expected_revision=recorded_model(folder,record)
            old=json.loads(report.read_text())
            if (old['id']!=folder.name or old['stockSha256']!=stock.sha(manifest.read_bytes())
                    or old['modelRevision']!=expected_revision or old['model']!=expected_model or old['publicationApproved'] is not False):raise ValueError('review_conflict')
            continue
        if now>=dt.datetime.fromisoformat(record['validUntil']):continue
        return review(folder,report,now,transcriber)
    return {'status':'no_unreviewed_valid_stock','publicationApproved':False}


def review_catalogue(root, revisions, output, now, transcriber=None):
    """Inspect at most one item across originals and immutable revision families."""
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','publicationApproved':False}
    revisions,output=Path(revisions),Path(output)
    if revisions.is_symlink() or output.is_symlink() or (output/'revisions').is_symlink():raise ValueError('symlink')
    families=sorted(revisions.iterdir()) if revisions.exists() else []
    if len(families)>16:raise ValueError('revision_bound')
    for family in families:
        if family.is_symlink() or not family.is_dir() or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',family.name):raise ValueError('revision_path')
    # Keep original report paths intact; revision families have separate reports
    # even when their storyboard identity is unchanged.
    sources=[(Path(root),output)]+[(f,output/'revisions'/f.name) for f in families]
    for source,destination in sources:
        result=review_next(source,destination,now,transcriber)
        if result['status']!='no_unreviewed_valid_stock':return result
    return {'status':'no_unreviewed_valid_stock','publicationApproved':False}


def review(folder,output,now,transcriber=None):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','publicationApproved':False}
    folder,output=Path(folder),Path(output)
    if folder.is_symlink() or (folder/'stock.json').is_symlink():raise ValueError('symlink')
    if output.exists() or output.is_symlink():raise ValueError('existing_review_preserved')
    record=json.loads((folder/'stock.json').read_text())
    identity,receipt,files=stock.validate(folder/'media',record['cloud'],now)
    if record['id']!=identity or record['files']!=files or record['publicationApproved'] is not False:raise ValueError('stock_changed')
    draft=json.loads((folder/'media/storyboard.json').read_text())
    narration=draft['narration']
    expected=' '.join([narration['hook']]+[e['text'] for e in narration['excerpts']]+[narration['closing']])
    # Validate all inputs before downloading a model or decoding any audio.
    filenames={r['file'] for r in files}
    for voice in VOICES:
        if f'videos/{voice}/reel.mp4' not in filenames:raise ValueError('missing_final_mix')
    model_name,model_revision=model_for_receipt(receipt)
    if transcriber is None:
        from huggingface_hub import snapshot_download
        from faster_whisper import WhisperModel
        model_path=snapshot_download(model_name,revision=model_revision,token=False,
            allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*'],max_workers=2)
        model=WhisperModel(model_path,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,local_files_only=True)
        def transcriber(path):
            segments,info=model.transcribe(str(path),language='fr',beam_size=5,temperature=0,
                condition_on_previous_text=False,initial_prompt=None,vad_filter=False)
            return [{'start':s.start,'end':s.end,'text':s.text,'averageLogProbability':s.avg_logprob,
                     'noSpeechProbability':s.no_speech_prob} for s in segments]
    reports=[]
    for voice in VOICES:
        path=folder/'media/videos'/voice/'reel.mp4'
        segments=transcriber(path)
        transcript=' '.join(s['text'].strip() for s in segments)
        reports.append({'voice':voice,'mediaSha256':stock.sha(path.read_bytes()),'segments':segments,
                        'transcript':transcript,'comparison':compare(expected,transcript)})
    result={'schemaVersion':1,'id':identity,'checkedAt':now.isoformat(),'validUntil':receipt['validUntil'],
            'status':'machine_transcription_requires_editorial_review','stockSha256':stock.sha((folder/'stock.json').read_bytes()),
            'model':model_name,'modelRevision':model_revision,'language':'fr','sourceTextPromptProvided':False,
            'compute':'local_cpu_int8','paidInferenceCalls':0,'publicationApproved':False,'publicationAttempted':False,
            'humanListeningPerformed':False,'expectedText':expected,'voices':reports,
            'limitation':'ASR differences may come from recognition or synthesis. This does not establish naturalness, pronunciation quality or editorial approval.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stock',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--next',action='store_true');parser.add_argument('--revisions',type=Path)
    args=parser.parse_args();now=dt.datetime.now(dt.timezone.utc)
    if args.revisions and not args.next:parser.error('--revisions requires --next')
    result=review_catalogue(args.stock,args.revisions,args.output,now) if args.revisions else (review_next if args.next else review)(args.stock,args.output,now)
    print(json.dumps({'status':result['status'],'publicationApproved':False,'voices':[
        {'voice':v['voice'],'comparison':v['comparison']} for v in result.get('voices',[])]},ensure_ascii=False))
