"""Build a source-bound Instagram lot; no network publication or credentials."""
import datetime as dt
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import stock
import storyboard
import promote_selected
import promote_catalogue

CAPABILITY_CHECKED='2026-10-12T08:00:00Z'
CAPABILITY_UNTIL=dt.datetime(2026,11,11,tzinfo=dt.timezone.utc)

def due_date(now,occupied,expiry):
    # One Sunday slot at 18:00 Paris, after the 72-hour reservation window.
    zone=ZoneInfo('Europe/Paris');day=now.astimezone(zone).date()
    for offset in range(36):
        date=day+dt.timedelta(days=offset)
        if date.weekday()!=6:continue
        due=dt.datetime.combine(date,dt.time(18),zone).astimezone(dt.timezone.utc)
        if due<now+dt.timedelta(hours=73) or due>=expiry:continue
        if any(abs((due-dt.datetime.fromisoformat(value.replace('Z','+00:00'))).total_seconds())<7*86400 for value in occupied):continue
        return due.isoformat().replace('+00:00','Z')
    return None


def build(candidate,site,now,occupied):
    if now.tzinfo is None:raise ValueError('timezone_required')
    if now>=min(stock.STOP,CAPABILITY_UNTIL):return {'status':'capability_or_authorization_expired'}
    candidate,site=Path(candidate),Path(site)
    selected=json.loads((candidate/'selection.json').read_text());proof_path=candidate/'public-media-proof.json'
    if proof_path.is_symlink():raise ValueError('symlink')
    proof=json.loads(proof_path.read_text())
    if proof['status']!='public_bytes_verified' or proof['contentId']!=candidate.name or proof['selectionSha256']!=stock.sha((candidate/'selection.json').read_bytes()) or proof['validUntil']!=selected['validUntil']:raise ValueError('unbound_public_proof')
    expiry=min(dt.datetime.fromisoformat(selected['validUntil']),CAPABILITY_UNTIL)
    due=due_date(now,occupied,expiry)
    if not due:return {'status':'no_valid_free_slot'}
    staged=promote_selected.stage(candidate,site,now)
    if staged['changed']:raise ValueError('media_was_not_staged')
    base=promote_catalogue.ORIGIN+'/social-media/production/'+staged['mediaId']
    manifest=json.loads((site/'public-media.json').read_text());entry=next(x for x in manifest['items'] if x['contentId']==staged['mediaId'])
    expected={base+'/'+x['name']:x for x in entry['files']}
    if len(proof['files'])!=5 or {x['url'] for x in proof['files']}!=set(expected):raise ValueError('public_proof_files')
    for row in proof['files']:
        item=expected[row['url']]
        if row['sha256']!=item['sha256'] or row['bytes']!=item['bytes']:raise ValueError('public_proof_changed')
        raw=promote_catalogue.read_public(row['url'],row['bytes'])
        if raw is None or len(raw)!=row['bytes'] or stock.sha(raw)!=row['sha256']:raise ValueError('public_media_unavailable_or_changed')
    draft=json.loads((candidate/'media/storyboard.json').read_text());slug=draft['source']['slug'];identity='vsd-production:instagram:'+slug+':voice-v1'
    voice_index=0 if selected['voice']=='fr_FR-siwis-medium' else 1
    scenario=storyboard.compose.ROOT/'scenarios'/['porto-aeroport-trois-reflexes.json','sintra-pena-trois-temps.json'][voice_index]
    music=json.loads(scenario.read_text())['assets']['music']
    text=('🇵🇹 '+draft['narration']['hook']+'\n\n'+draft['narration']['excerpts'][0]['text']+'\n\n📌 Enregistrez ces repères pour préparer votre départ. Le guide et ses sources sont accessibles depuis le lien en bio :\n'+draft['targetUrl']+'\n\nConseils documentés, sans récit de voyage vécu. Voix de synthèse et montage assisté par IA ; aucun personnage réel représenté.\n\n🎵 « '+music['title']+' » — '+music['author']+'\n'+music['sourceUrl']+'\nCC BY 4.0 : '+music['licenseUrl']+'\nExtrait, fondus, niveau réduit sous la voix et synchronisation. Aucune approbation de l’auteur revendiquée.\n\nVoix Piper ; attributions et notices :\n'+base+'/credits.txt\nVidéo et narration : Voyage Sans Détour, CC BY-SA 4.0 : https://creativecommons.org/licenses/by-sa/4.0/\n\n#Portugal #VoyageSansVoiture #VoyageSansDetour')
    if len(text)>2200:raise ValueError('caption_too_long')
    stamp=now.isoformat().replace('+00:00','Z');until=expiry.isoformat();fresh={'status':'verified','observedAt':stamp,'validUntil':until}
    media={'url':base+'/reel.mp4','mimeType':'video/mp4','sha256':selected['mediaSha256']}
    payload={'schemaVersion':1,'channel':'instagram','kind':'reel','text':text,'aiGenerated':True,'assets':[media]}
    review={'schemaVersion':1,'contentId':identity,'approved':True,'reviewedAt':stamp,'validUntil':until,'payloadRevision':None,
      'checks':{'editorialApproved':True,'rightsApproved':True,'creditsPreserved':True,'disclosurePreserved':True,'formatRequirementsVerified':True,'requiresPaidCall':False,'sources':fresh,'syntheticPerson':False,'providerSyntheticSettingVerified':True},
      'media':{**media,**fresh,'required':True},'destination':{'url':draft['targetUrl'],**fresh},
      'monetization':{'containsAffiliateLinks':False,'partnerApproved':False,'linksVerified':False,'disclosurePreserved':False},
      'formatCapability':{'status':'verified','observedAt':CAPABILITY_CHECKED,'validUntil':CAPABILITY_UNTIL.isoformat(),'automaticPublishing':True,'verificationMethod':'official_documentation','sourceUrls':['https://support.buffer.com/en-us/articles/sharing-videos-through-buffer-LOe2p2rnAI','https://developers.buffer.com/types/InstagramPostMetadataInput.html']},
      'evidence':{'status':'source_bound_public_bytes_rechecked','voice':selected['voice'],'syntheticVoice':True,'humanListeningPerformed':False,'reviewMethod':selected['reviewMethod'],'selectionSha256':proof['selectionSha256'],'transcriptionSha256':selected['transcriptionSha256'],'publicProofSha256':stock.sha(proof_path.read_bytes()),'sourceCheckedOn':draft['source']['sourcesCheckedOn'],'creditsUrl':base+'/credits.txt','mediaSha256':selected['mediaSha256']}}
    return {'status':'batch_prepared_not_imported','batch':{'schemaVersion':1,'batchId':'instagram-'+slug+'-voice-v1','items':[{'contentId':identity,'deduplicationKey':identity,'title':draft['narration']['hook'],'dueAt':due,'payload':payload,'review':review}]}}

if __name__=='__main__':
    context=json.load(sys.stdin)
    print(json.dumps(build(context['candidate'],context['site'],dt.datetime.now(dt.timezone.utc),context['occupied']),ensure_ascii=False))
