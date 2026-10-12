"""Create one unpublished typographic Pin from a published article catalogue."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent

def wrap(draw,text,font,width):
    lines=[];line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if draw.textbbox((0,0),word,font=font)[2]>width:raise ValueError('word_overflow')
        if draw.textbbox((0,0),candidate,font=font)[2]>width:
            lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines

def render(article,output):
    slug=article['slug']
    if not isinstance(slug,str) or not slug or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in slug):raise ValueError('invalid_slug')
    title=article['title']
    if not isinstance(title,str) or not 1<=len(title)<=200:raise ValueError('invalid_title')
    target=Path(output)/('pin-'+slug)
    if target.exists():raise ValueError('existing_draft_preserved')
    image=Image.new('RGB',(1000,1500),'#F7F4EC');draw=ImageDraw.Draw(image)
    font=lambda name,size:ImageFont.truetype(str(HERE/'assets'/name),size)
    small=font('dmsans-bold.ttf',25);regular=font('dmsans-regular.ttf',32)
    draw.rectangle((0,0,1000,20),fill='#234CDD')
    draw.text((80,85),'VOYAGE SANS DÉTOUR',font=small,fill='#234CDD')
    draw.rounded_rectangle((80,205,410,260),radius=27,fill='#E6EE77')
    draw.text((104,215),'LE GUIDE À GARDER',font=small,fill='#142A43')
    for size in (86,80,74,68,62):
        heading=font('playfair.ttf',size);lines=wrap(draw,title,heading,840)
        if len(lines)*(size+22)<=630:break
    else:raise ValueError('title_overflow')
    y=340
    for line in lines:
        draw.text((80,y),line,font=heading,fill='#142A43');y+=size+22
    draw.line((80,1090,920,1090),fill='#234CDD',width=3)
    for i,line in enumerate(['Des repères pour préparer votre voyage.', 'Retrouvez le guide et ses sources sur le blog.']):
        draw.text((80,1140+i*50),line,font=regular,fill='#142A43')
    draw.rounded_rectangle((80,1320,920,1410),radius=20,fill='#234CDD')
    draw.text((135,1347),'voyagesansdetour.fr',font=font('dmsans-bold.ttf',40),fill='white')
    target.mkdir(parents=True)
    image.save(target/'pin.jpg',quality=94)
    raw=json.dumps(article,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    manifest={'schemaVersion':1,'id':'pin-'+slug,'status':'draft_requires_review','publicationApproved':False,
              'title':title,'targetUrl':'https://voyagesansdetour.fr/portugal/'+slug+'/',
              'articleSha256':hashlib.sha256(raw).hexdigest(),'imageSha256':hashlib.sha256((target/'pin.jpg').read_bytes()).hexdigest(),
              'width':1000,'height':1500,'templateVersion':1,'rendererSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'originalComposition':True,'externalPhotographs':False,
              'limitations':['Draft only; target publication, board, caption, duplicate registry and rendered layout require review.']}
    (target/'draft.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name in ('dmsans-OFL.txt','playfairdisplay-OFL.txt'):
        (target/name).write_bytes((HERE/'assets'/name).read_bytes())
    (target/'credits.txt').write_text('Composition typographique Voyage Sans Détour, assistée par IA. Polices DM Sans et Playfair Display : licences OFL jointes. Aucun récit de voyage vécu.\n')
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--articles',type=Path,required=True);parser.add_argument('--slug',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    articles=json.loads(args.articles.read_text());matches=[a for a in articles if a['slug']==args.slug]
    if len(matches)!=1:raise ValueError('article_missing_or_ambiguous')
    print(render(matches[0],args.output))
