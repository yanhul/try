#!/usr/bin/env python3
"""Broad public-source scout feeding a deterministic multi-round population engine.

Discovery expands the candidate universe; it never promotes or executes a strategy.
Successful observations are retained across runs so rate-limit/provider failures
cannot erase previously discovered research sources.
"""
from __future__ import annotations
import json, os, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research'/'discovery'/'latest.json'
ARCHIVE=ROOT/'research'/'discovery'/'source_archive.json'
QUERIES=[
 'crypto momentum trend following strategy bitcoin','crypto mean reversion statistical arbitrage strategy','crypto volatility breakout strategy','smart money concepts ICT liquidity sweep trading strategy crypto','fair value gap imbalance FVG crypto trading','Wyckoff VSA VPA volume price analysis crypto','VWAP volume profile crypto trading strategy','funding rate basis carry crypto trading','crypto order flow order book imbalance microprice','cross sectional crypto factors momentum reversal','crypto regime switching hidden Markov trading','bitcoin seasonality calendar effect trading','Solana on chain alpha liquidity trading','crypto options volatility skew gamma trading','prediction market order book trading strategy','maker adverse selection execution crypto','MEV execution alpha crypto','systematic crypto trading machine learning alpha','symbolic regression alpha mining trading','evolutionary alpha discovery trading strategy','LLM alpha mining quantitative trading','autonomous trading strategy research backtest','多因子 加密货币 量化 交易 策略','因子挖掘 加密货币 量化 交易','量化 交易 alpha 挖掘 遗传 算法','强化学习 加密货币 交易 策略','订单流 加密货币 交易 策略','资金费率 基差 套利 加密货币','SMC ICT 流动性 扫损 加密货币','威科夫 VSA VPA 量价 加密货币',
]
def get(url, *, github=False):
    headers={'User-Agent':'try-research-scout/3.0','Accept':'application/json'}
    token=os.getenv('GITHUB_TOKEN')
    if github and token: headers['Authorization']=f'Bearer {token}'
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
def github(q):
    try:
        u='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':20,'sort':'updated'})
        return [{'source':'github','query':q,'title':x.get('full_name'),'url':x.get('html_url'),'description':x.get('description'),'updated_at':x.get('updated_at'),'stars':x.get('stargazers_count')} for x in get(u,github=True).get('items',[])]
    except Exception as e:return [{'source':'github','query':q,'error':str(e)}]
def arxiv(q):
    try:
        u='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':'all:'+q,'start':0,'max_results':20})
        req=urllib.request.Request(u,headers={'User-Agent':'try-research-scout/3.0'})
        with urllib.request.urlopen(req,timeout=20) as r: raw=r.read().decode(errors='replace')
        return [{'source':'arxiv','query':q,'raw':raw[:30000]}]
    except Exception as e:return [{'source':'arxiv','query':q,'error':str(e)}]
def merge_success(previous,fresh):
    by_key={}
    def key(x): return (x.get('source'),x.get('url') or x.get('title') or x.get('raw') or x.get('query'))
    for item in previous:
        if isinstance(item,dict) and not item.get('error'): by_key[key(item)]=item
    for item in fresh:
        if isinstance(item,dict) and not item.get('error'): by_key[key(item)]=item
    return sorted(by_key.values(),key=lambda x:(x.get('source',''),x.get('query',''),x.get('title',''),x.get('url','')))
def main():
    previous=[]
    if OUT.exists():
        try: previous=json.loads(OUT.read_text(encoding='utf-8')).get('results',[])
        except Exception: previous=[]
    results=[]; jobs=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for q in QUERIES: jobs += [pool.submit(github,q),pool.submit(arxiv,q)]
        for f in as_completed(jobs): results.extend(f.result())
    merged=merge_success(previous,results)
    payload={'schema_version':4,'fanout':'github+arxiv_parallel_bounded','query_families':len(QUERIES),'queries':QUERIES,'fresh_results':results,'results':merged}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    ARCHIVE.write_text(json.dumps({'schema_version':1,'sources':merged},indent=2),encoding='utf-8')
    print(f'DISCOVERY_SCOUT_DONE fresh={len(results)} retained_success={len(merged)} output={OUT}')
    engine=ROOT/'research'/'discovery'/'population_engine.py'
    proc=subprocess.run([sys.executable,str(engine)],cwd=str(ROOT),text=True,capture_output=True)
    print(proc.stdout,end='')
    if proc.returncode: print(proc.stderr,end=''); raise SystemExit(proc.returncode)
    print('DISCOVERY_POPULATION_READY')
if __name__=='__main__':main()
