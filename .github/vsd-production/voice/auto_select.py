"""Select only a source-bound, unambiguous voiced render. Never publish it."""
import datetime as dt
import io
import json
from pathlib import Path
import stock
import pilot
import storyboard
import compose
import transcribe_review as asr

DIGITS=dict(zip('0123456789','zéro un deux trois quatre cinq six sept huit neuf'.split()))

def equivalents(expected,actual):
    accepted=[]
    for difference in asr.compare(expected,actual)['differences']:
        a,b=difference['expected'],difference['transcribed']
        if difference['kind']!='replace' or len(a)!=1 or len(b)!=1 or DIGITS.get(a[0])!=b[0]:return None
        accepted.append({'expected':a[0],'transcribed':b[0],'reason':'Same single-digit French number, numeral versus written word'})
    return accepted


def evaluate(candidate,report_path,now,preferred='fr_FR-upmc-medium',fetcher=storyboard.fetch_public):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=stock.STOP:return {'status':'period_ended'}
    candidate,report_path=Path(candidate),Path(report_path)
    if candidate.is_symlink() or report_path.is_symlink() or (candidate/'stock.json').is_symlink():raise ValueError('symlink')
    record=json.loads((candidate/'stock.json').read_text())
    identity,receipt,files=stock.validate(candidate/'media',record['cloud'],now)
    if record['files']!=files or record['id']!=identity:raise ValueError('stock_changed')
    if receipt.get('synthesisProfile')!='clear-v1':return {'status':'legacy_profile_held'}
    report=json.loads(report_path.read_text())
    if (report['id']!=identity or report['stockSha256']!=stock.sha((candidate/'stock.json').read_bytes())
        or report['model']!=asr.MEDIUM_MODEL or report['modelRevision']!=asr.MEDIUM_REVISION
        or report['sourceTextPromptProvided'] is not False or report['publicationApproved'] is not False
        or not dt.datetime.fromisoformat(report['checkedAt'])<=now<dt.datetime.fromisoformat(report['validUntil'])
        or report['validUntil']!=receipt['validUntil']):raise ValueError('unqualified_report')
    draft,sentences,headings,badges,draft_hash,public_hash=storyboard.prepare(pilot.HERE.parent/'reel-drafts'/identity,now,fetcher,sentence_flow=True)
    if draft_hash!=receipt['storyboardSha256'] or receipt['narrationSegmentation']!='complete_sentences':raise ValueError('source_changed')
    expected=' '.join(sentences)
    if report['expectedText']!=expected:raise ValueError('expected_text_changed')
    audio=json.loads((candidate/'media/audio/receipt.json').read_text())
    video=json.loads((candidate/'media/videos/receipt.json').read_text())
    if (audio['modelsManifestSha256']!=pilot.sha((pilot.HERE/'models.json').read_bytes())
        or audio['synthesisProfile']!='clear-v1' or audio['synthesisArguments']!=pilot.synthesis_args('clear-v1')
        or video['rendererSha256']!=pilot.sha(Path(compose.__file__).read_bytes())
        or video['audioReceiptSha256']!=pilot.sha((candidate/'media/audio/receipt.json').read_bytes())):raise ValueError('render_contract_changed')
    eligible=[]
    for index,voice in enumerate(asr.VOICES):
        rows=[r for r in report['voices'] if r['voice']==voice]
        if len(rows)!=1:raise ValueError('voice_report_count')
        row=rows[0];folder=candidate/'media/videos'/voice
        if row['mediaSha256']!=stock.sha((folder/'reel.mp4').read_bytes()):raise ValueError('transcription_media_changed')
        if row['comparison']!=asr.compare(expected,row['transcript']):raise ValueError('comparison_changed')
        accepted=equivalents(expected,row['transcript'])
        if accepted is None:continue
        spec=next(v['specification'] for v in video['videos'] if v['voice']==voice)
        if not (spec['width']==1080 and spec['height']==1920 and spec['fps']==30 and 15<=spec['durationSeconds']<=45 and spec['videoCodec']=='h264' and spec['audioCodec']=='aac' and spec['fullDecodePassed'] is True and -22<=spec['loudness']['integratedLufs']<=-14 and spec['loudness']['truePeakDbfs']<=-1):continue
        assets=compose.load_json(compose.ROOT/'scenarios'/['porto-aeroport-trois-reflexes.json','sintra-pena-trois-temps.json'][index])['assets']
        for key in ('regular','bold','serif','music'):compose.verified_file(compose.ROOT,assets[key])
        for key in ('regular','bold','serif'):
            if assets[key]['license']!='OFL-1.1':raise ValueError('font_license_changed')
            compose.verified_file(compose.ROOT,assets[key]['licenseFile'])
        music=assets['music'];provenance=compose.load_json(compose.verified_file(compose.ROOT,music['provenance']))
        if music['license']!='CC-BY-4.0' or music['commercialUseAllowed'] is not True or provenance['download']['sha256']!=music['sha256']:raise ValueError('music_rights_changed')
        credits=(pilot.HERE/'CREDITS.md').read_text()+f"\nMusique : {music['title']} — {music['author']}. {music['sourceUrl']}\nLicence : {music['licenseUrl']}\nModifications : extrait, réduction du niveau sous la voix, fondus et synchronisation. Aucune approbation de l’auteur revendiquée.\nPolices DM Sans et Playfair Display, SIL OFL 1.1, notices jointes.\n"
        if (folder/'credits.md').read_text()!=credits:raise ValueError('credits_changed')
        fonts={name:compose.ImageFont.truetype(str(compose.ROOT/assets[key]['file']),size) for name,key,size in [('title','serif',85),('caption','bold',45),('small','bold',29),('tiny','regular',23)]}
        for i,text in enumerate(sentences):
            rendered=io.BytesIO();compose.scene(i,index,fonts,text,headings,badges).save(rendered,format='JPEG',quality=92)
            if rendered.getvalue()!=(folder/f'scene-{i+1}.jpg').read_bytes():raise ValueError('scene_layout_changed')
        eligible.append((voice,row['mediaSha256'],accepted))
    if not eligible:return {'status':'held_transcription_ambiguities','publicationApproved':False}
    voice,media_hash,accepted=next((r for r in eligible if r[0]==preferred),eligible[0])
    return {'schemaVersion':1,'contentId':identity,'status':'selected_for_promotion_qualification','selectedAt':now.isoformat(),'validUntil':receipt['validUntil'],'voice':voice,'mediaSha256':media_hash,'stockSha256':report['stockSha256'],'transcriptionSha256':stock.sha(report_path.read_bytes()),'reviewMethod':'Automatic exact source comparison; pinned independent ASR; single-digit equivalence only; exact regenerated scene bytes; measured media specification; unchanged licensed assets and credits','humanListeningPerformed':False,'publicationApproved':False,'publicationAttempted':False,'acceptedTranscriptionDifferences':accepted,'publicHtmlSha256':public_hash,'eligibleVoices':[r[0] for r in eligible],'remaining':['public_media_promotion','cloud_admission','native_publication_receipt']}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():raise ValueError('existing_output_preserved')
    result=evaluate(args.candidate,args.report,dt.datetime.now(dt.timezone.utc))
    with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps({'status':result['status'],'voice':result.get('voice'),'publicationAttempted':False}))
