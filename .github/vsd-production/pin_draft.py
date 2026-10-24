"""Create one unpublished typographic Pin from a published article catalogue."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from PIL import Image,ImageDraw,ImageFont

HERE=Path(__file__).resolve().parent
ORIGIN='https://voyagesansdetour.fr'

def article_path(article):
    # Same rule as the site: guides live under their country, Portugal by default.
    country=article.get('country','portugal')
    if not isinstance(country,str) or not re.fullmatch(r'[a-z]+(?:-[a-z]+)*',country):raise ValueError('invalid_country')
    return '/'+country+'/'+article['slug']+'/'

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

SITE=HERE.parents[1]/'site-src'
FREE_LICENSES=('CC BY 2.0','CC BY 3.0','CC BY 4.0','CC BY-SA 2.0','CC BY-SA 3.0','CC BY-SA 4.0','CC0','CC0 1.0','Public domain')
COUNTRY_LABELS={'portugal':'PORTUGAL','espagne':'ESPAGNE','italie':'ITALIE'}

def font(name,size):return ImageFont.truetype(str(HERE/'assets'/name),size)

def cover_photo(article,site):
    # The guide's own cover, only when its catalogue entry carries a free licence and an author.
    cover=article.get('cover')
    if not cover:return None
    entries=[p for p in json.loads((Path(site)/'image-sources.json').read_text())['photos'] if p['id']==cover]
    if len(entries)!=1:raise ValueError('photo_missing_from_catalogue')
    photo=entries[0]
    if photo.get('license') not in FREE_LICENSES or not photo.get('author') or not photo.get('source_page'):raise ValueError('photo_license')
    path=Path(site)/'dist/assets'/photo['file']
    if not path.is_file():raise ValueError('photo_file_missing')
    return photo,path

def key_fact(article):
    facts=article.get('keyFacts') or []
    return facts[0] if facts and facts[0].get('value') and facts[0].get('label') else None

def fit(draw,text,sizes,width,height,gap):
    for size in sizes:
        heading=font('playfair.ttf',size);lines=wrap(draw,text,heading,width)
        if len(lines)*(size+gap)<=height:return heading,size,lines
    raise ValueError('title_overflow')

def draw_photo_pin(article,photo,path):
    with Image.open(path) as source:
        source=source.convert('RGB');scale=max(1000/source.width,1500/source.height)
        resized=source.resize((round(source.width*scale),round(source.height*scale)),Image.LANCZOS)
    left,top=(resized.width-1000)//2,(resized.height-1500)//2
    image=resized.crop((left,top,left+1000,top+1500))
    # Dark gradient over the lower two thirds so the text stays readable on any photo.
    shade=Image.new('L',(1,1500))
    for y in range(1500):shade.putpixel((0,y),0 if y<450 else min(235,int((y-450)/1050*300)))
    image=Image.composite(Image.new('RGB',(1000,1500),'#0E1B2B'),image,shade.resize((1000,1500)))
    draw=ImageDraw.Draw(image);small=font('dmsans-bold.ttf',26)
    label=COUNTRY_LABELS.get(article.get('country','portugal'),'VOYAGE')+' · SANS VOITURE'
    draw.rounded_rectangle((70,70,110+draw.textbbox((0,0),label,font=small)[2],126),radius=28,fill='#F5D547')
    draw.text((90,82),label,font=small,fill='#142A43')
    heading,size,lines=fit(draw,article.get('shortTitle') or article['title'],(96,88,80,72,64),860,420,16)
    fact=key_fact(article);y=1010-len(lines)*(size+16)-(0 if fact else -150)
    for line in lines:draw.text((70,y),line,font=heading,fill='white');y+=size+16
    if fact:
        draw.text((70,y+30),fact['value'],font=font('dmsans-bold.ttf',84),fill='#F5D547')
        for i,line in enumerate(wrap(draw,fact['label'],font('dmsans-regular.ttf',34),860)[:2]):
            draw.text((70,y+135+i*46),line,font=font('dmsans-regular.ttf',34),fill='white')
    draw.text((70,1385),'voyagesansdetour.fr',font=font('dmsans-bold.ttf',38),fill='white')
    draw.text((70,1440),'Photo : '+photo['author']+' — '+photo['license'],font=font('dmsans-regular.ttf',22),fill='#D8DEE8')
    return image

def draw_typographic_pin(article):
    image=Image.new('RGB',(1000,1500),'#F7F4EC');draw=ImageDraw.Draw(image)
    small=font('dmsans-bold.ttf',25);regular=font('dmsans-regular.ttf',32)
    draw.rectangle((0,0,1000,20),fill='#234CDD')
    draw.text((80,85),'VOYAGE SANS DÉTOUR',font=small,fill='#234CDD')
    draw.rounded_rectangle((80,205,410,260),radius=27,fill='#E6EE77')
    draw.text((104,215),'LE GUIDE À GARDER',font=small,fill='#142A43')
    heading,size,lines=fit(draw,article['title'],(86,80,74,68,62),840,630,22)
    y=340
    for line in lines:
        draw.text((80,y),line,font=heading,fill='#142A43');y+=size+22
    draw.line((80,1090,920,1090),fill='#234CDD',width=3)
    fact=key_fact(article)
    if fact:
        draw.text((80,1115),fact['value'],font=font('dmsans-bold.ttf',60),fill='#234CDD')
        draw.text((80,1195),wrap(draw,fact['label'],regular,840)[0],font=regular,fill='#142A43')
    else:
        draw.text((80,1160),'Le guide complet, prix et trajets vérifiés.',font=regular,fill='#142A43')
    draw.rounded_rectangle((80,1320,920,1410),radius=20,fill='#234CDD')
    draw.text((135,1347),'voyagesansdetour.fr',font=font('dmsans-bold.ttf',40),fill='white')
    return image

def credits(photo):
    fonts='Polices DM Sans et Playfair Display : licences OFL jointes.'
    if not photo:return 'Composition typographique Voyage Sans Détour, assistée par IA. '+fonts+'\n'
    return ('Photo : '+photo['author']+', '+photo['source_page']+' — '+photo['license']+' ('+photo['license_url']+').\n'
            'Recadrage, dégradé et texte ajoutés par Voyage Sans Détour ; épingle diffusée sous la même licence. '+fonts+'\n')

def render(article,output,site=SITE):
    slug=article['slug']
    if not isinstance(slug,str) or not slug or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in slug):raise ValueError('invalid_slug')
    title=article['title']
    if not isinstance(title,str) or not 1<=len(title)<=200:raise ValueError('invalid_title')
    target_url=ORIGIN+article_path(article)
    target=Path(output)/('pin-'+slug)
    if target.exists():raise ValueError('existing_draft_preserved')
    found=cover_photo(article,site);photo=found[0] if found else None
    image=draw_photo_pin(article,*found) if found else draw_typographic_pin(article)
    target.mkdir(parents=True)
    image.save(target/'pin.jpg',quality=92)
    raw=json.dumps(article,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    manifest={'schemaVersion':1,'id':'pin-'+slug,'status':'draft_requires_review','publicationApproved':False,
              'title':title,'targetUrl':target_url,
              'articleSha256':hashlib.sha256(raw).hexdigest(),'imageSha256':hashlib.sha256((target/'pin.jpg').read_bytes()).hexdigest(),
              'width':1000,'height':1500,'templateVersion':2 if photo else 1,'rendererSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'originalComposition':True,'externalPhotographs':bool(photo),
              'limitations':['Draft only; target publication, board, caption, duplicate registry and rendered layout require review.']}
    if photo:manifest['photo']={k:photo[k] for k in ('id','author','source_page','license','license_url')}
    (target/'draft.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    for name in ('dmsans-OFL.txt','playfairdisplay-OFL.txt'):
        (target/name).write_bytes((HERE/'assets'/name).read_bytes())
    (target/'credits.txt').write_text(credits(photo))
    return target

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--articles',type=Path,required=True);parser.add_argument('--slug',required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    articles=json.loads(args.articles.read_text());matches=[a for a in articles if a['slug']==args.slug]
    if len(matches)!=1:raise ValueError('article_missing_or_ambiguous')
    print(render(matches[0],args.output))
