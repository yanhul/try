#!/usr/bin/env python3
"""Broad public-source scout. Discovery is advisory; it cannot promote or execute a strategy."""
from __future__ import annotations
import json, urllib.parse, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research'/'discovery'/'latest.json'
QUERIES=[
 'crypto market microstructure trading strategy',
 'prediction market trading strategy order book',
 'Solana on-chain trading alpha liquidity',
 'crypto execution adverse selection maker',
 'funding basis options prediction market arbitrage',
]
def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'try-research-scout/1.0','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
def main():
 results=[]
 for q in QUERIES:
  try:
   u='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':10,'sort':'updated'})
   data=get(u)
   for x in data.get('items',[]): results.append({'source':'github','query':q,'title':x.get('full_name'),'url':x.get('html_url'),'description':x.get('description'),'updated_at':x.get('updated_at'),'stars':x.get('stargazers_count')})
  except Exception as e: results.append({'source':'github','query':q,'error':str(e)})
 # arXiv Atom is XML, so use export API and retain raw text for the LLM extractor.
 for q in QUERIES:
  try:
   u='http://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':'all:'+q,'start':0,'max_results':10})
   req=urllib.request.Request(u,headers={'User-Agent':'try-research-scout/1.0'})
   with urllib.request.urlopen(req,timeout=20) as r: raw=r.read().decode(errors='replace')
   results.append({'source':'arxiv','query':q,'raw':raw[:30000]})
  except Exception as e: results.append({'source':'arxiv','query':q,'error':str(e)})
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps({'schema_version':1,'queries':QUERIES,'results':results},indent=2),encoding='utf-8')
 print(f'DISCOVERY_SCOUT_DONE results={len(results)} output={OUT}')
if __name__=='__main__':main()
