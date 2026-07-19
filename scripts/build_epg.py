#!/usr/bin/env python3
import gzip,html,json,re,shutil,sys,tempfile,unicodedata,urllib.request,xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from rapidfuzz import fuzz,process
BASE='https://epgshare01.online/epgshare01'; OUT=Path('output'); DATA=Path('data'); OUT.mkdir(exist_ok=True)
FEEDS=['MY1','SG1','ID1','IN1','UK1','US2','CA2','AU1','HK1','JP1','KR1','TH1','PH1','PH2','PK1','SA2','DE1','TW1','VN1','BD1','CN1','ES1','EC1','KZ1','NZ1','AE1','FR1','IT1','NL1','PT1','BR1','MX1']
ACCTS=['m240730254672129','m240730582462128']; UA='SKAsia-Xtream-ID-EPG/5.0'
NOISE={'hd','fhd','uhd','4k','8k','sd','hevc','h265','h264','live','backup','test','channel','ch','tv','my','sg','id','malaysia','singapore','indonesia','official','vip','raw'}
def norm(s):
 s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower(); s=re.sub(r'\b(?:1080p|720p|576p|50fps|60fps|line\s*\d+|server\s*\d+)\b',' ',s); s=re.sub(r'[^a-z0-9]+',' ',s)
 return ' '.join(t for t in s.split() if t not in NOISE)
def hint(g,n):
 s=(g+' '+n).lower(); rules=[('MY1',['malaysia','astro','rtm','tv3','8tv','ntv7','bernama']),('SG1',['singapore','mediacorp','suria','vasantham','cna']),('ID1',['indonesia','rcti','sctv','indosiar','antv','trans7','mnctv']),('UK1',['bbc','itv','sky uk']),('US2',['usa','fox news','cnn us']),('AU1',['australia','sbs']),('IN1',['india','zee','sony sab']),('HK1',['hong kong','tvb','viutv']),('JP1',['japan','nhk']),('KR1',['korea','kbs','mbc korea']),('TH1',['thailand','thai']),('PH1',['philippines','abs-cbn','gma'])]
 for c,ws in rules:
  if any(w in s for w in ws): return c
 return ''
def dl(url,p):
 r=urllib.request.Request(url,headers={'User-Agent':UA});
 with urllib.request.urlopen(r,timeout=120) as q,p.open('wb') as f: shutil.copyfileobj(q,f)
def chans(p,code):
 out=[]
 with gzip.open(p,'rb') as f:
  for _,e in ET.iterparse(f,events=('end',)):
   if e.tag=='channel':
    sid=e.get('id',''); names=[(c.text or '').strip() for c in e.findall('display-name') if (c.text or '').strip()]
    if sid and names: out.append({'id':sid,'feed':code,'names':names,'norms':[norm(x) for x in names if norm(x)]})
   e.clear()
 return out
def score(n,g,c):
 t=norm(n); best=0
 for x in c['norms']:
  v=100 if t==x else max(fuzz.WRatio(t,x),fuzz.token_set_ratio(t,x),fuzz.ratio(t,x));
  if t and x and (t in x or x in t): v=max(v,92)
  best=max(best,v)
 h=hint(g,n); best += 4 if h and c['feed']==h else (-4 if h else 0)
 return min(best,100)
def mappings(sk,src):
 choices={}
 for i,c in enumerate(src):
  for x in c['norms']:
   if x and x not in choices: choices[x]=i
 out=[]
 for s in sk:
  t=norm(s['name']); inds=set([choices[t]]) if t in choices else set()
  if t:
   for _,_,i in process.extract(t,choices,scorer=fuzz.WRatio,limit=15,score_cutoff=45): inds.add(i)
  bi=None; bs=0
  for i in inds:
   q=score(s['name'],s['group'],src[i])
   if q>bs: bi,bs=i,q
  if bi is not None and bs>=78 and s.get('stream_id'):
   c=src[bi]; out.append({**s,'source_id':c['id'],'source_feed':c['feed'],'source_name':c['names'][0],'score':round(bs,2)})
  else: out.append({**s,'source_id':'','source_feed':'','source_name':'','score':round(bs,2)})
 return out
def write(acct,ms,files):
 ok=[m for m in ms if m['source_id'] and m['stream_id']]; by=defaultdict(list)
 for m in ok: by[(m['source_feed'],m['source_id'])].append(m)
 count=0
 with gzip.open(OUT/f'skasia-{acct}-epg.xml.gz','wt',encoding='utf-8',compresslevel=9) as o:
  o.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="SKAsia Xtream Stream-ID EPG v5">\n')
  for m in ok:
   cid=html.escape(str(m['stream_id']),quote=True); o.write(f'  <channel id="{cid}"><display-name>{html.escape(m["name"])}</display-name>')
   if m.get('logo'): o.write(f'<icon src="{html.escape(m["logo"],quote=True)}"/>')
   o.write('</channel>\n')
  for code,p in files.items():
   wanted={sid for feed,sid in by if feed==code}
   if not wanted: continue
   with gzip.open(p,'rb') as f:
    for _,e in ET.iterparse(f,events=('end',)):
     if e.tag=='programme' and e.get('channel','') in wanted:
      x=ET.tostring(e,encoding='unicode'); sid=e.get('channel','')
      for m in by[(code,sid)]:
       y=re.sub(r'channel="[^"]*"',f'channel="{html.escape(str(m["stream_id"]),quote=True)}"',x,count=1); o.write('  '+y+'\n'); count+=1
     e.clear()
  o.write('</tv>\n')
 return len(ok),count
def main():
 with tempfile.TemporaryDirectory() as td:
  files={}; src=[]; fail=[]
  for code in FEEDS:
   p=Path(td)/f'{code}.xml.gz'
   try: dl(f'{BASE}/epg_ripper_{code}.xml.gz',p); files[code]=p; src+=chans(p,code)
   except Exception as e: fail.append(f'{code}: {e}')
  if not files: raise RuntimeError('No XMLTV feeds downloaded')
  status=['SKAsia Xtream Stream-ID EPG v5',f'Downloaded feeds: {len(files)}',f'Source channels indexed: {len(src)}',f'Failed feeds: {len(fail)}']
  for a in ACCTS:
   sk=json.loads((DATA/f'channels-{a}.json').read_text()); ms=mappings(sk,src); matched,progs=write(a,ms,files)
   with (OUT/f'mapping-{a}.csv').open('w',encoding='utf-8') as f:
    f.write('stream_id,skasia_channel,group,source_feed,source_channel,score,status\n')
    for m in ms:
     vals=[str(m.get('stream_id','')),m['name'],m['group'],m['source_feed'],m['source_name'],str(m['score']),'matched' if m['source_id'] else 'unmatched']; f.write(','.join('"'+v.replace('"','""')+'"' for v in vals)+'\n')
   status += ['',f'Account: {a}',f'Live channels: {len(sk)}',f'Matched channels: {matched}',f'Unmatched channels: {len(sk)-matched}',f'Programme entries written: {progs}']
  if fail: status += ['','Feed errors:']+fail
  (OUT/'build-status.txt').write_text('\n'.join(status)+'\n'); print('\n'.join(status))
if __name__=='__main__': main()
