#!/usr/bin/env python3
"""Broad public-source scout feeding a deterministic multi-round population engine.

Discovery expands the candidate universe; it never promotes or executes a strategy.
Successful observations are retained across runs so rate-limit/provider failures
cannot erase previously discovered research sources.

Source coverage is intentionally bounded and explicit: GitHub, arXiv, OpenAlex and
Crossref public APIs. This is broad public-source coverage, not an exhaustive
crawl of the Internet.
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
 'crypto momentum trend following strategy bitcoin','crypto mean reversion statistical arbitrage strategy','crypto volatility breakout strategy','smart money concepts ICT liquidity sweep trading strategy crypto','fair value gap imbalance FVG crypto trading','Wyckoff VSA VPA volume price analysis crypto','VWAP volume profile crypto trading strategy','funding rate basis carry crypto trading','crypto order flow order book imbalance microprice','cross sectional crypto factors momentum reversal','crypto regime switching hidden Markov trading','bitcoin seasonality calendar effect trading','Solana on chain alpha liquidity trading','crypto options volatility skew gamma trading','prediction market order book trading strategy','maker adverse selection execution crypto','MEV execution alpha crypto','systematic crypto trading machine learning alpha','symbolic regression alpha mining trading','evolutionary alpha discovery trading strategy','LLM alpha mining quantitative trading','autonomous trading strategy research backtest','A-share quantitative trading factor strategy China','China stock limit-up quantitative strategy','China A-share order flow high frequency factors','China A-share T+1 transaction cost backtest','China A-share cross-sectional factor mining','China A-share point-in-time survivorship backtest','China A-share pairs statistical arbitrage','China A-share machine learning alpha','中国 A股 量化 交易 策略 因子','因子挖掘 A股 量化 交易','涨停 连板 A股 量化 策略','订单流 A股 高频 因子','T+1 涨跌停 交易成本 回测','多因子 加密货币 量化 交易 策略','因子挖掘 加密货币 量化 交易','量化 交易 alpha 挖掘 遗传 算法','强化学习 加密货币 交易 策略','订单流 加密货币 交易 策略','资金费率 基差 套利 加密货币','SMC ICT 流动性 扫损 加密货币','威科夫 VSA VPA 量价 加密货币',
 'equity factor investing cross sectional alpha backtest','statistical arbitrage pairs trading equities','futures trend following systematic strategy','options volatility trading systematic strategy','market microstructure order book strategy','alternative data quantitative alpha research','reinforcement learning trading systematic review','genetic programming symbolic regression trading alpha','portfolio optimization risk parity systematic trading','event driven quantitative trading earnings news','prediction markets automated trading research','decentralized exchange arbitrage MEV research','on chain wallet flow trading signal research',
]

def get_json(url, *, github=False):
    headers={'User-Agent':'try-research-scout/5.0','Accept':'application/json'}
    token=os.getenv('GITHUB_TOKEN')
    if github and token: headers['Authorization']=f'Bearer {token}'
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode(errors='replace'))

def github(q):
    try:
        u='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q,'per_page':20,'sort':'updated'})
        return [{'source':'github','query':q,'title':x.get('full_name'),'url':x.get('html_url'),'description':x.get('description'),'updated_at':x.get('updated_at'),'stars':x.get('stargazers_count')} for x in get_json(u,github=True).get('items',[])]
    except Exception as e:return [{'source':'github','query':q,'error':str(e)}]

def arxiv(q):
    try:
        u='https://export.arxiv.org/api/query?'+urllib.parse.urlencode({'search_query':'all:'+q,'start':0,'max_results':20})
        req=urllib.request.Request(u,headers={'User-Agent':'try-research-scout/5.0'})
        with urllib.request.urlopen(req,timeout=20) as r: raw=r.read().decode(errors='replace')
        return [{'source':'arxiv','query':q,'raw':raw[:30000]}]
    except Exception as e:return [{'source':'arxiv','query':q,'error':str(e)}]

def openalex(q):
    try:
        u='https://api.openalex.org/works?'+urllib.parse.urlencode({'search':q,'per-page':10,'select':'id,title,doi,publication_year,primary_location,type'})
        data=get_json(u)
        out=[]
        for x in data.get('results',[]):
            title=x.get('title') or ''
            url=x.get('doi') or x.get('id')
            out.append({'source':'openalex','query':q,'title':title,'url':url,'description':f"OpenAlex work type={x.get('type')} year={x.get('publication_year')}",'updated_at':str(x.get('publication_year') or '')})
        return out
    except Exception as e:return [{'source':'openalex','query':q,'error':str(e)}]

def crossref(q):
    try:
        u='https://api.crossref.org/works?'+urllib.parse.urlencode({'query.bibliographic':q,'rows':10,'select':'DOI,title,published,URL,type'})
        data=get_json(u)
        out=[]
        for x in data.get('message',{}).get('items',[]):
            titles=x.get('title') or []
            title=titles[0] if titles else ''
            out.append({'source':'crossref','query':q,'title':title,'url':x.get('URL') or (('https://doi.org/'+x['DOI']) if x.get('DOI') else None),'description':f"Crossref work type={x.get('type')}",'updated_at':str((x.get('published') or {}).get('date-parts',[['']])[0][0])})
        return out
    except Exception as e:return [{'source':'crossref','query':q,'error':str(e)}]

def load_success(path, key_name):
    if not path.exists(): return []
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        items=data.get(key_name,[]) if isinstance(data,dict) else []
        return [x for x in items if isinstance(x,dict) and not x.get('error')]
    except Exception:
        return []

def merge_success(previous,fresh):
    by_key={}
    def key(x): return (x.get('source'),x.get('url') or x.get('title') or x.get('raw') or x.get('query'))
    for item in previous: by_key[key(item)]=item
    for item in fresh:
        if isinstance(item,dict) and not item.get('error'): by_key[key(item)]=item
    return sorted(by_key.values(),key=lambda x:(x.get('source',''),x.get('query',''),x.get('title',''),x.get('url','')))

def main():
    previous=load_success(ARCHIVE,'sources')
    if not previous: previous=load_success(OUT,'results')
    results=[]; jobs=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for q in QUERIES:
            jobs += [pool.submit(github,q),pool.submit(arxiv,q),pool.submit(openalex,q),pool.submit(crossref,q)]
        for f in as_completed(jobs): results.extend(f.result())
    merged=merge_success(previous,results)
    payload={'schema_version':6,'fanout':'github+arxiv+openalex+crossref_parallel_bounded','query_families':len(QUERIES),'queries':QUERIES,'fresh_results':results,'results':merged}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    ARCHIVE.write_text(json.dumps({'schema_version':3,'sources':merged},indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'DISCOVERY_SCOUT_DONE fresh={len(results)} retained_success={len(merged)} output={OUT}')
    engine=ROOT/'research'/'discovery'/'population_engine.py'
    proc=subprocess.run([sys.executable,str(engine)],cwd=str(ROOT),text=True,capture_output=True)
    print(proc.stdout,end='')
    if proc.returncode: print(proc.stderr,end=''); raise SystemExit(proc.returncode)
    print('DISCOVERY_POPULATION_READY')

if __name__=='__main__':main()
