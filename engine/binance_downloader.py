#!/usr/bin/env python3
import argparse,csv,time,json,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
BASE='https://api.binance.com/api/v3/klines'; LIMIT=1000
def dt(s): return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(timezone.utc)
def fetch(symbol,interval,start,end):
 q=urllib.parse.urlencode({'symbol':symbol.upper(),'interval':interval,'startTime':int(start.timestamp()*1000),'endTime':int(end.timestamp()*1000),'limit':LIMIT})
 with urllib.request.urlopen(BASE+'?'+q,timeout=30) as r:return json.load(r)
def main():
 p=argparse.ArgumentParser();p.add_argument('--symbol',required=True);p.add_argument('--interval',required=True);p.add_argument('--start',required=True);p.add_argument('--end',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 start,end=dt(a.start),dt(a.end); out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True);n=0
 with out.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['timestamp','open','high','low','close','volume'])
  while start<end:
   rows=fetch(a.symbol,a.interval,start,end)
   if not rows:break
   for r in rows:
    ts=datetime.fromtimestamp(r[0]/1000,tz=timezone.utc)
    if ts>=end:break
    w.writerow([ts.isoformat(),r[1],r[2],r[3],r[4],r[5]]);n+=1
   nxt=datetime.fromtimestamp(rows[-1][0]/1000,tz=timezone.utc)
   if nxt<=start:raise RuntimeError('pagination stalled')
   start=nxt.replace(microsecond=0)+__import__('datetime').timedelta(milliseconds=1);time.sleep(.15)
 print(f'Downloaded {n} candles -> {out}')
if __name__=='__main__':main()
