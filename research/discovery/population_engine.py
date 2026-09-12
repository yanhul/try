#!/usr/bin/env python3
"""Multi-round research population engine with market-specific source lanes."""
from __future__ import annotations
import hashlib,json,re,xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[2]; DISCOVERY=ROOT/'research'/'discovery'
LANES=DISCOVERY/'source_lanes.json'; LATEST=DISCOVERY/'latest.json'; ARCHIVE=DISCOVERY/'source_archive.json'; SEEDS=DISCOVERY/'china_a_share_sources.json'
POPULATION=DISCOVERY/'population.json'; SURVIVORS=DISCOVERY/'survivors.json'; QUEUE=DISCOVERY/'research_queue.json'
FAMILY_TERMS={
'momentum_trend':('momentum','trend','breakout','moving average'),'mean_reversion':('mean reversion','mean-reversion','reversion','statistical arbitrage'),'volatility':('volatility','variance','volatility breakout'),'smc_ict':('smart money','smc','ict','liquidity sweep','market structure','order block'),'fvg_imbalance':('fair value gap','fvg','imbalance'),'wyckoff_vsa_vpa':('wyckoff','vsa','volume spread','volume price analysis'),'vwap_volume_profile':('vwap','volume profile','anchored vwap'),'funding_basis_carry':('funding','basis','carry','perpetual'),'order_flow':('order flow','orderflow','order book','lob imbalance','microprice'),'cross_sectional':('cross-sectional','factor','rankic','icir','cross sectional'),'regime':('regime','hidden markov','hmm','state switching'),'seasonality':('seasonality','seasonal','day of week','calendar effect'),'onchain':('on-chain','onchain','wallet','blockchain','solana'),'options':('options','implied volatility','skew','gamma'),'prediction_market':('prediction market','polymarket','kalshi','clob'),'execution_mev':('execution','adverse selection','maker','taker','mev','slippage'),
'china_a_share':('china a-share','a-share','ashare','a share','chinese stock','chinese stocks','limit-up','limit up','连板','涨停','t+1','qlib','eastmoney','akshare','alpha158','factor mining','a股')}
EXECUTABLE_FAMILIES={'momentum_trend','mean_reversion','volatility','smc_ict','fvg_imbalance','wyckoff_vsa_vpa','vwap_volume_profile','regime','seasonality','cross_sectional','china_a_share'}
def _text(item): return ' '.join(str(item.get(k,'')) for k in ('title','description','raw','query')).lower()
def classify(item):
 text=_text(item)
 china=sum(text.count(t) for t in FAMILY_TERMS['china_a_share'])
 if china: return 'china_a_share'
 scores={f:sum(text.count(t) for t in terms) for f,terms in FAMILY_TERMS.items() if f!='china_a_share'}
 best,score=max(scores.items(),key=lambda x:x[1]); return best if score else 'unknown'
def source_id(item):
 canonical=str(item.get('url') or item.get('title') or item.get('raw') or item.get('query')); return hashlib.sha256(canonical.encode()).hexdigest()[:16]
def _xml_text(node): return '' if node is None else ' '.join(''.join(node.itertext()).split())
def expand_source(item):
 if item.get('source')!='arxiv' or not item.get('raw'): return [item]
 try:
  root=ET.fromstring(item['raw']); ns={'a':'http://www.w3.org/2005/Atom'}; out=[]
  for e in root.findall('a:entry',ns):
   pid=_xml_text(e.find('a:id',ns)); title=_xml_text(e.find('a:title',ns)) or item.get('query'); summary=_xml_text(e.find('a:summary',ns)); pub=_xml_text(e.find('a:published',ns)); link=next((x.attrib.get('href') for x in e.findall('a:link',ns) if x.attrib.get('href')),pid); out.append({'source':'arxiv','query':item.get('query'),'title':title,'url':link or pid,'description':summary,'updated_at':pub})
  return out or [{k:v for k,v in item.items() if k!='raw'}]
 except ET.ParseError: return []
def normalize(raw):
 family=classify(raw); market='CN_A_SHARE' if family=='china_a_share' else raw.get('market')
 return {'candidate_id':source_id(raw),'source':raw.get('source','unknown'),'source_url':raw.get('url'),'title':raw.get('title') or raw.get('query'),'description':raw.get('description'),'family':family,'market':market,'query':raw.get('query'),'source_timestamp':raw.get('updated_at'),'lineage':{'source':source_id(raw),'family':family,'rounds':[]}}
def round1_source_quality(items):
 out=[]; seen=set()
 for item in items:
  key=item.get('source_url') or re.sub(r'\s+',' ',str(item.get('title','')).lower()).strip()
  if not key or key in seen: continue
  seen.add(key)
  if item.get('source') in {'github','arxiv'}: item['lineage']['rounds'].append({'round':1,'decision':'PASS_SOURCE'}); out.append(item)
 return out
def round2_feasibility(items):
 executable=[]; deferred=[]
 for item in items:
  family=item['family']
  if family in EXECUTABLE_FAMILIES: item['lineage']['rounds'].append({'round':2,'decision':'PASS_EXECUTABLE_DATA_LANE'}); executable.append(item)
  else: item['lineage']['rounds'].append({'round':2,'decision':'DEFER_DATA_LANE','family':family}); deferred.append(item)
 return executable,deferred
def round3_diversity(items):
 groups={}; seen=set()
 for item in sorted(items,key=lambda x:(x['family'],x['title'] or '')):
  key=(item['family'],re.sub(r'[^a-z0-9]+',' ',str(item['title']).lower()).strip())
  if key in seen: continue
  seen.add(key); groups.setdefault(item['family'],[]).append(item)
 out=[]; families=sorted(groups); depth=0
 while True:
  added=False
  for family in families:
   if depth<len(groups[family]):
    item=groups[family][depth]; item['lineage']['rounds'].append({'round':3,'decision':'PASS_DIVERSITY_DEDUP','family_order':'round_robin'}); out.append(item); added=True
  if not added: break
  depth+=1
 return out
def _load_discovery_sources():
 sources=[]; store='empty'
 if ARCHIVE.exists():
  try:
   p=json.loads(ARCHIVE.read_text()); sources=[x for x in p.get('sources',[]) if isinstance(x,dict) and not x.get('error')]; store='archive'
  except (OSError,json.JSONDecodeError,TypeError): pass
 if not sources and LATEST.exists():
  try:
   p=json.loads(LATEST.read_text()); sources=[x for x in p.get('results',[]) if isinstance(x,dict) and not x.get('error')]; store='latest_fallback'
  except (OSError,json.JSONDecodeError,TypeError): pass
 if SEEDS.exists():
  try:
   seed=json.loads(SEEDS.read_text()); seed_items=seed.get('sources',[]) if isinstance(seed,dict) else []
   sources.extend(x for x in seed_items if isinstance(x,dict)); store += '+china_seed'
  except (OSError,json.JSONDecodeError,TypeError): pass
 return sources,store
def build():
 raw,store=_load_discovery_sources(); expanded=[]
 for x in raw: expanded.extend(expand_source(x))
 normalized=[normalize(x) for x in expanded]; r1=round1_source_quality(normalized); executable,deferred=round2_feasibility(r1); survivors=round3_diversity(executable)
 payload={'schema_version':4,'architecture':'durable_source_archive + market_seed -> expand -> normalize_dedup -> feasibility -> diversity -> survivor_registry -> executable_translation','source_store':store,'policy_authority':'research/campaign_policy.json','counts':{'raw':len(raw),'expanded':len(expanded),'normalized':len(normalized),'round1':len(r1),'deferred':len(deferred),'survivors':len(survivors),'china_a_share_survivors':sum(x['family']=='china_a_share' for x in survivors)},'population':normalized,'deferred':deferred}
 POPULATION.write_text(json.dumps(payload,indent=2),encoding='utf-8'); SURVIVORS.write_text(json.dumps({'schema_version':4,'status':'SCREEN_SURVIVORS_NOT_PERFORMANCE_PROMOTION','survivors':survivors},indent=2),encoding='utf-8'); QUEUE.write_text(json.dumps({'schema_version':4,'status':'READY_FOR_EXECUTABLE_TRANSLATION','candidates':survivors},indent=2),encoding='utf-8'); return payload
if __name__=='__main__': print('POPULATION_ENGINE_DONE',json.dumps(build()['counts'],sort_keys=True))
