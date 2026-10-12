"""Compose verified sentence-timed audio into unpublished vertical video pilots."""
import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont
from pilot import HERE, STOP, SENTENCES, TEXT, sha, inspect_wav

ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from production import verified_file, load_json, verify_video

HEADINGS = [('Et si on', 'préparait la suite ?'), ('Des guides.', 'Des sources.'),
            ('Gardez vos idées.', 'Comparez ensuite.'), ('À vous', 'le prochain départ.')]
BADGES = ['PORTUGAL', 'VOYAGE SANS DÉTOUR', 'VOTRE CARNET', 'LE BLOG VOYAGE']


def validate_timing(sample, sentences=SENTENCES):
    segments = sample.get('segments', [])
    if len(segments) != len(sentences):
        raise ValueError('missing_sentence_timing')
    previous = 0
    for index, (segment, text) in enumerate(zip(segments, sentences)):
        start, end = segment['startSample'], segment['endSample']
        if (type(start) is not int or type(end) is not int or segment['sampleRate'] != 22050
                or start < previous or end <= start or segment['text'] != text
                or (index == 0 and start != 0)):
            raise ValueError('invalid_sentence_timing')
        if index and start - previous != 4410:
            raise ValueError('unexpected_sentence_gap')
        previous = end
    if abs(previous/22050 - sample['durationSeconds']) > 1/22050:
        raise ValueError('timing_does_not_cover_audio')
    return segments


def timecode(samples):
    ms = round(samples/22050*1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{ms:03}'


def line(draw, text, xy, font, fill, width=880):
    if draw.textbbox((0, 0), text, font=font)[2] > width:
        raise ValueError('visual_text_overflow')
    draw.text(xy, text, font=font, fill=fill)


def wrap(draw, text, font, width):
    lines, current = [], ''
    # Keep French separated punctuation attached to its preceding word.
    for word in re.findall(r'\S+(?:[ \u00a0\u202f]+[?!:;](?=\s|$))?', text):
        value = (current+' '+word).strip()
        if draw.textlength(value, font=font) > width:
            if not current:
                raise ValueError('subtitle_word_overflow')
            lines.append(current)
            current = word
        else:
            current = value
    if current:
        lines.append(current)
    if len(lines) > 3:
        raise ValueError('subtitle_line_overflow')
    return lines


def caption_layout(draw,text,font):
    # Preserve whole sentences; bounded resizing keeps the subtitle legible.
    for size in (45,42,40,38):
        candidate=font if font.size==size else font.font_variant(size=size)
        try:return candidate,wrap(draw,text,candidate,820)
        except ValueError as error:
            if str(error)!='subtitle_line_overflow':raise
    raise ValueError('subtitle_line_overflow')


def scene(index, voice_index, fonts, subtitle, headings=HEADINGS, badges=BADGES):
    dark = (index+voice_index) % 2 == 1
    paper, ink, blue, lime = '#F7F4EC', '#142A43', '#234CDD', '#E6EE77'
    bg, fg = (ink, paper) if dark else (paper, ink)
    image = Image.new('RGB', (1080, 1920), bg)
    draw = ImageDraw.Draw(image)
    line(draw, 'VOYAGE SANS DÉTOUR', (86, 175), fonts['small'], fg)
    draw.line((86, 249, 994, 249), fill=fg, width=2)
    draw.rounded_rectangle((86, 328, 994, 398), 35, fill=lime)
    line(draw, badges[index], (115, 344), fonts['small'], ink)
    for n, title in enumerate(headings[index]):
        line(draw, title, (84, 465+n*123), fonts['title'], fg)
    # Abstract itinerary: a graphic metaphor, not a map or a journey claim.
    draw.line((190, 905, 530, 1025, 860, 875), fill=lime if dark else blue, width=9)
    for n, (x, y) in enumerate([(190,905),(530,1025),(860,875)]):
        draw.ellipse((x-37,y-37,x+37,y+37), fill=lime if dark else blue)
        draw.text((x-10,y-21), str(n+1), font=fonts['small'], fill=ink if dark else paper)
    draw.rounded_rectangle((86, 1225, 994, 1535), 32, fill=paper if dark else ink)
    if subtitle:
        caption_font,caption_lines=caption_layout(draw,subtitle,fonts['caption'])
        for n, value in enumerate(caption_lines):
            line(draw, value, (125, 1265+n*68), caption_font, ink if dark else paper, 820)
    line(draw, 'VOIX DE SYNTHÈSE · MONTAGE ASSISTÉ PAR IA', (86, 1600), fonts['tiny'], fg)
    line(draw, 'voyagesansdetour.fr', (86, 1660), fonts['small'], fg)
    return image


def compose(audio_dir, output, now, sentences=SENTENCES, headings=HEADINGS, badges=BADGES):
    if now.tzinfo is None:
        raise ValueError('timezone_required')
    if now >= STOP:
        return {'status':'period_ended', 'generated':0}
    if not len(sentences) == len(headings) == len(badges) or not 1 <= len(sentences) <= 24:
        raise ValueError("scene_count_mismatch")
    audio_dir, output = Path(audio_dir), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('existing_output_preserved')
    receipt = load_json(audio_dir/'receipt.json')
    if receipt.get('schemaVersion') != 2 or receipt['textSha256'] != sha(" ".join(sentences).encode()) or len(receipt['samples']) != 2:
        raise ValueError('unqualified_audio_receipt')
    if receipt['modelsManifestSha256'] != sha((HERE/'models.json').read_bytes()):
        raise ValueError('voice_manifest_changed')
    model_ids = [v['id'] for v in load_json(HERE/'models.json')['voices']]
    if [s['voice'] for s in receipt['samples']] != model_ids:
        raise ValueError('unexpected_voice_order')
    # Reuse the exact already-licensed assets; scenario review dates are not renewed.
    scenario_names = ['porto-aeroport-trois-reflexes.json', 'sintra-pena-trois-temps.json']
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.voice-video-', dir=output.parent) as tmp:
        result = Path(tmp)/'result'
        result.mkdir()
        videos=[]
        for voice_index, sample in enumerate(receipt['samples']):
            segments=validate_timing(sample, sentences)
            wav=verified_file(audio_dir, {'file':sample['voice']+'.wav','sha256':sample['sha256']})
            measured=inspect_wav(wav)
            if measured['durationSeconds'] != sample['durationSeconds']:
                raise ValueError('audio_duration_changed')
            assets=load_json(ROOT/'scenarios'/scenario_names[voice_index])['assets']
            for key in ('regular','bold','serif','music'):
                verified_file(ROOT,assets[key])
            for key in ('regular','bold','serif'):
                if assets[key]['license']!='OFL-1.1': raise ValueError('font_license_changed')
                verified_file(ROOT,assets[key]['licenseFile'])
            music=assets['music']
            provenance=load_json(verified_file(ROOT,music['provenance']))
            if (music['license']!='CC-BY-4.0' or not music['commercialUseAllowed']
                    or provenance['download']['sha256']!=music['sha256']):
                raise ValueError('music_rights_changed')
            fonts={name:ImageFont.truetype(str(ROOT/assets[key]['file']),size) for name,key,size in
                   [('title','serif',85),('caption','bold',45),('small','bold',29),('tiny','regular',23)]}
            folder=result/sample['voice'];folder.mkdir()
            bases=[scene(i,voice_index,fonts,s['text'],headings,badges) for i,s in enumerate(segments)]
            for i,base in enumerate(bases):base.save(folder/f'scene-{i+1}.jpg',quality=92)
            sheet=Image.new('RGB',(720,640*math.ceil(len(bases)/2)),'white')
            for i,base in enumerate(bases):sheet.paste(base.resize((360,640)),((i%2)*360,(i//2)*640))
            sheet.save(folder/'apercu.jpg',quality=92)
            subtitles='\n\n'.join(f"{i+1}\n{timecode(s['startSample'])} --> {timecode(s['endSample'])}\n{s['text']}" for i,s in enumerate(segments))+'\n'
            (folder/'sous-titres.srt').write_text(subtitles)
            duration=math.ceil((sample['durationSeconds']+0.5)*30)/30
            audio_filter=(f'[1:a]aresample=48000,loudnorm=I=-18:TP=-2:LRA=7,apad,atrim=duration={duration},asplit=2[voice][side];'
                          f'[2:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume=0.055,afade=t=in:d=0.4,afade=t=out:st={duration-1}:d=1[music];'
                          '[music][side]sidechaincompress=threshold=0.015:ratio=6:attack=15:release=200[duck];'
                          '[voice][duck]amix=inputs=2:normalize=0,loudnorm=I=-18:TP=-1.5:LRA=7[a]')
            command=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-f','rawvideo','-pixel_format','rgb24','-video_size','1080x1920',
                     '-framerate','30','-i','pipe:0','-i',str(wav),'-i',str(ROOT/music['file']),'-filter_complex',audio_filter,
                     '-map','0:v:0','-map','[a]','-t',str(duration),'-c:v','libx264','-threads','2','-preset','veryfast','-crf','21',
                     '-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-ar','48000','-movflags','+faststart',str(folder/'reel.mp4')]
            with (folder/'encode.log').open('wb') as errors:
                process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
                try:
                    for n in range(round(duration*30)):
                        t=n/30; index=max(i for i,s in enumerate(segments) if s['startSample']/22050<=t)
                        base=bases[index].copy();draw=ImageDraw.Draw(base)
                        # Smooth progress and moving waypoint keep the composition alive.
                        draw.rounded_rectangle((86,1730,994,1740),5,fill='#D8DAD6')
                        draw.rounded_rectangle((86,1730,87+907*n/max(1,round(duration*30)-1),1740),5,fill='#234CDD')
                        x=180+690*(0.5+0.5*math.sin(t*0.7));draw.ellipse((x-9,1140,x+9,1158),fill='#234CDD')
                        process.stdin.write(base.tobytes())
                    process.stdin.close()
                    if process.wait(timeout=120)!=0:raise ValueError('video_encode_failed')
                except BaseException:
                    if process.poll() is None:process.kill();process.wait()
                    raise
            spec=verify_video(folder/'reel.mp4',duration,True)
            credits=(HERE/'CREDITS.md').read_text()+f"\nMusique : {music['title']} — {music['author']}. {music['sourceUrl']}\nLicence : {music['licenseUrl']}\nModifications : extrait, réduction du niveau sous la voix, fondus et synchronisation. Aucune approbation de l’auteur revendiquée.\nPolices DM Sans et Playfair Display, SIL OFL 1.1, notices jointes.\n"
            (folder/'credits.md').write_text(credits)
            for name in ('dmsans-OFL.txt','playfairdisplay-OFL.txt'):(folder/name).write_bytes((ROOT/'assets'/name).read_bytes())
            videos.append({'voice':sample['voice'],'music':music['title'],'specification':spec,
                           'files':[{'file':str(p.relative_to(result)),'sha256':sha(p.read_bytes())} for p in sorted(folder.iterdir()) if p.is_file()]})
        proof={'schemaVersion':1,'status':'voice_video_pilots_not_published','generatedAt':now.isoformat(),
               'audioReceiptSha256':sha((audio_dir/'receipt.json').read_bytes()),'rendererSha256':sha(Path(__file__).read_bytes()),
               'subtitleAlignment':'narration segment boundaries measured in audio samples, not word alignment',
               'videos':videos,'publicationAttempted':False,'listeningReviewComplete':False,
               'automaticProductionIntegration':False}
        (result/'receipt.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        result.rename(output)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--audio',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(compose(args.audio,args.output,dt.datetime.now(dt.timezone.utc))))
