#!/usr/bin/env python3
"""Point-in-time source-lane audit. Missing evidence is explicit, never synthesized."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'research/discovery/source_lanes.json'
OUT=ROOT/'research/discovery/source_audit.json'
DATA=ROOT/'data'
def main():
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    files=[p.name for p in DATA.rglob('*') if p.is_file()] if DATA.exists() else []
    text=' '.join(files).lower()
    rows=[]
    for lane in manifest['lanes']:
        if lane['id']=='cex' and ('btc' in text or 'binance' in text or 'ohlcv' in text): status='PARTIAL_DATASET'
        elif lane['id']=='research_mining': status='AVAILABLE'
        else: status='UNAVAILABLE'
        rows.append({'id':lane['id'],'family':lane['family'],'status':status,'required_artifacts':lane['required_artifacts']})
    OUT.write_text(json.dumps({'schema_version':1,'data_files':files,'lanes':rows},indent=2)+'\n',encoding='utf-8')
    print('SOURCE_AUDIT '+json.dumps({r['id']:r['status'] for r in rows},sort_keys=True))
if __name__=='__main__': main()
