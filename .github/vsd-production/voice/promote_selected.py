"""Stage selected, source-bound voiced media; no social API or stock admission."""
import argparse
import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import stock
import storyboard
from transcribe_review import words

NAMES={'reel.mp4':'reel.mp4','poster.jpg':'scene-1.jpg','credits.txt':'credits.md',
       'dmsans-OFL.txt':'dmsans-OFL.txt','playfairdisplay-OFL.txt':'playfairdisplay-OFL.txt'}


def stage(candidate,site,now,fetcher=storyboard.fetch_public):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended','changed':False}
    candidate,site=Path(candidate),Path(site)
    for p in [candidate,site,candidate/'stock.json',candidate/'selection.json',candidate/'transcription.json',site/'public-media.json']:
        if p.is_symlink():raise ValueError('symlink')
    record=json.loads((candidate/'stock.json').read_text())
    identity,receipt,inventory=stock.validate(candidate/'media',record['cloud'],now)
    if identity!=record['id'] or inventory!=record['files']:raise ValueError('stock_changed')
    selected=json.loads((candidate/'selection.json').read_text())
    asr=json.loads((candidate/'transcription.json').read_text())
    if (selected['status']!='selected_for_promotion_qualification' or selected['contentId']!=identity
        or selected['stockSha256']!=stock.sha((candidate/'stock.json').read_bytes())
        or selected['transcriptionSha256']!=stock.sha((candidate/'transcription.json').read_bytes())
        or selected['validUntil']!=receipt['validUntil'] or selected['publicationApproved'] is not False):raise ValueError('selection_changed')
    voice=selected['voice']
    if voice not in ('fr_FR-siwis-medium','fr_FR-upmc-medium'):raise ValueError('voice_not_qualified')
    folder=candidate/'media/videos'/voice
    media_hash=stock.sha((folder/'reel.mp4').read_bytes())
    if media_hash!=selected['mediaSha256']:raise ValueError('selected_media_changed')
    rows=[v for v in asr['voices'] if v['voice']==voice]
    if len(rows)!=1 or rows[0]['mediaSha256']!=media_hash or asr['stockSha256']!=selected['stockSha256']:raise ValueError('transcription_not_bound')
    accepted=[(words(x['expected']),words(x['transcribed'])) for x in selected['acceptedTranscriptionDifferences']]
    differences=[(x['expected'],x['transcribed']) for x in rows[0]['comparison']['differences']]
    if differences!=accepted:raise ValueError('unreviewed_transcription_difference')
    if not dt.datetime.fromisoformat(asr['checkedAt'])<=dt.datetime.fromisoformat(selected['selectedAt'])<=now:raise ValueError('review_chronology')
    draft,_,_,_,draft_hash,public_hash=storyboard.prepare(storyboard.pilot.HERE.parent/'reel-drafts'/identity,now,fetcher=fetcher,sentence_flow=True)
    if draft_hash!=receipt['storyboardSha256'] or receipt['narrationSegmentation']!='complete_sentences':raise ValueError('source_or_flow_changed')
    video=json.loads((candidate/'media/videos/receipt.json').read_text())
    specs=[v['specification'] for v in video['videos'] if v['voice']==voice]
    if len(specs)!=1:raise ValueError('missing_video_spec')
    s=specs[0]
    if not (s['width']==1080 and s['height']==1920 and s['fps']==30 and 15<=s['durationSeconds']<=45
            and s['videoCodec']=='h264' and s['audioCodec']=='aac' and s['fullDecodePassed'] is True
            and -22<=s['loudness']['integratedLufs']<=-14 and s['loudness']['truePeakDbfs']<=-1):raise ValueError('video_spec_unqualified')
    media_id=identity+'-voice'
    destination=site/'social-media/production'/media_id
    for p in [site/'social-media',site/'social-media/production',destination]:
        if p.is_symlink():raise ValueError('symlink')
    files=[{'name':name,'bytes':(folder/origin).stat().st_size,'sha256':stock.sha((folder/origin).read_bytes())} for name,origin in NAMES.items()]
    item={'contentId':media_id,'approved':True,'files':files}
    manifest_path=site/'public-media.json';manifest=json.loads(manifest_path.read_text())
    matches=[i for i in manifest['items'] if i['contentId']==media_id]
    if matches and matches!=[item]:raise ValueError('existing_media_conflict')
    if destination.exists():
        if set(p.name for p in destination.iterdir())!=set(NAMES):raise ValueError('existing_files_conflict')
        for name,origin in NAMES.items():
            if (destination/name).is_symlink() or (destination/name).read_bytes()!=(folder/origin).read_bytes():raise ValueError('existing_files_conflict')
    elif matches:raise ValueError('manifest_files_missing')
    else:
        destination.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent,prefix='.voice-stage-') as tmp:
            out=Path(tmp)/media_id;out.mkdir()
            for name,origin in NAMES.items():shutil.copyfile(folder/origin,out/name)
            out.rename(destination)
    if not matches:
        manifest['items'].append(item)
        with tempfile.NamedTemporaryFile(mode='w',dir=site,prefix='.public-media-',delete=False) as f:
            json.dump(manifest,f,ensure_ascii=False,indent=2);f.write('\n');temp=Path(f.name)
        temp.replace(manifest_path)
    return {'status':'already_staged' if matches else 'staged_not_deployed','changed':not bool(matches),'id':identity,
            'mediaId':media_id,'voice':voice,'mediaSha256':media_hash,'publicHtmlSha256':public_hash,
            'validUntil':receipt['validUntil'],'socialPublicationAttempted':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--site',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(stage(args.candidate,args.site,dt.datetime.now(dt.timezone.utc))))
