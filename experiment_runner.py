#!/usr/bin/env python3
import argparse,json,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timezone
def sha256(p):
 h=hashlib.sha256();
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--config',required=True);p.add_argument('--command',required=True,nargs='+');p.add_argument('--out',required=True);a=p.parse_args()
 r=subprocess.run(a.command,text=True,capture_output=True);out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 payload={'experiment_time':datetime.now(timezone.utc).isoformat(),'data_file':str(Path(a.data).resolve()),'data_sha256':sha256(a.data),'config_file':str(Path(a.config).resolve()),'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
 out.write_text(json.dumps(payload,indent=2));print(json.dumps(payload,indent=2));raise SystemExit(r.returncode)
if __name__=='__main__':main()
