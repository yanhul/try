#!/usr/bin/env python3
"""Strict provider router: deterministic discovery population narrows; Gemini translates one selected survivor."""
from __future__ import annotations
import json, math, os, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.autonomous_hypothesis import write_candidate, validate_candidate
from engine.hypotheses import HYPOTHESES
from research.evidence_calibration import verify_with_openai_compatible
OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
SYSTEM=f"""You are an autonomous trading-research translator.
A deterministic population engine has already screened a public-source universe.
You MUST translate the single SELECTED SCREEN SURVIVOR supplied by the controller. You are not a survivor selector.
Do not select by expected performance, stars, OOS, or intuition. Do not replace the selected survivor with another source.
Registered hypothesis_ids are allowed; otherwise use hypothesis_id='discovered_primitive'.
For discovered_primitive, use ONLY operators {OPERATORS}, columns {COLUMNS}, windows {WINDOWS}.
A discovery_spec MUST contain operator,left,numeric threshold,direction ('above'/'below'); difference/ratio also require right; windowed operators require window.
For threshold, output a plain finite JSON number such as 0, 0.5, 1, 1.5, or -0.5. NEVER output ranges, percentages, expressions, null, strings, or prose as threshold.
Threshold and direction are a proposal to be tested, NOT evidence and NOT proof. Do not use OOS to select or tune.
Do not invent evidence. Exactly one conceptual change. Return JSON only with keys:
hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used,discovery_spec.
"""
def config(name):
 n=name.upper(); defaults={"GEMINI":("https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),"GEMINI_API_KEY"),"DEEPSEEK":("https://api.deepseek.com",os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"),"DEEPSEEK_API_KEY")}
 if n in defaults: base,model,keyvar=defaults[n]
 else: base=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL",""); model=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL",""); keyvar=f"RESEARCH_PROVIDER_{n}_API_KEY"
 return base.rstrip("/"),model,os.getenv(keyvar,"")
def call(name,prompt):
 base,model,key=config(name)
 if not base or not model or not key: raise RuntimeError(f"provider_not_configured:{name}")
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":1400,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 last=None
 for attempt in range(3):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as exc:
   last=exc
   if exc.code not in {429,500,502,503,504} or attempt == 2: raise
   retry_after=exc.headers.get("Retry-After") if exc.headers else None
   try: delay=max(1,int(float(retry_after))) if retry_after else 2 ** attempt
   except ValueError: delay=2 ** attempt
   time.sleep(min(delay,15))
 if last: raise last
 raise RuntimeError(f"provider_request_failed:{name}")
def normalize_structural_types(candidate):
 spec=candidate.get("discovery_spec")
 if not isinstance(spec,dict): return
 if "threshold" in spec and isinstance(spec["threshold"],str):
  text=spec["threshold"].strip()
  try: value=float(text)
  except ValueError: return
  if not math.isfinite(value): return
  spec["threshold"]=int(value) if value.is_integer() else value
 if "window" in spec and isinstance(spec["window"],str) and spec["window"].strip().isdigit(): spec["window"]=int(spec["window"].strip())
def discovery_fingerprint(candidate):
 spec=candidate.get("discovery_spec") or {}
 if not isinstance(spec,dict): return None
 return tuple(spec.get(k) for k in ("operator","left","right","window","threshold","direction"))
def prior_discovery_fingerprints():
 fingerprints=set(); directory=ROOT/'research'/'autonomous_candidates'
 if not directory.exists(): return fingerprints
 for path in sorted(directory.glob('BC*.json')):
  try:
   candidate=json.loads(path.read_text(encoding='utf-8')); fp=discovery_fingerprint(candidate)
   if fp is not None: fingerprints.add(fp)
  except (OSError,ValueError,TypeError): continue
 return fingerprints
def request_candidate(name,prompt,forbidden_fingerprints):
 feedback=""; last_reason="unknown"
 for _ in range(3):
  raw=call(name,prompt+feedback)
  try: candidate=json.loads(raw)
  except Exception:
   last_reason="invalid_json"; feedback="\nVALIDATOR_FEEDBACK: invalid JSON; regenerate one JSON object only.\n"; continue
  if candidate.get("status")=="HOLD": return candidate
  normalize_structural_types(candidate); hypothesis_id=candidate.get("hypothesis_id")
  if not isinstance(hypothesis_id,str): reason="invalid_hypothesis_id_type"
  elif hypothesis_id not in HYPOTHESES and hypothesis_id!="discovered_primitive": reason="unregistered_hypothesis_id"
  else:
   candidate["bc"],candidate["parent_bc"]=bc,parent; fp=discovery_fingerprint(candidate)
   if fp is not None and fp in forbidden_fingerprints: reason="duplicate_discovery_fingerprint"
   else:
    ok,reason=validate_candidate(candidate,bc,parent)
    if ok:return candidate
  last_reason=reason
  if reason=="duplicate_discovery_fingerprint": feedback="\nVALIDATOR_FEEDBACK: duplicate_discovery_fingerprint. Regenerate a genuinely distinct executable discovery_spec. Do not reuse any prior operator/left/right/window/threshold/direction tuple. Preserve the selected source lineage.\n"
  elif reason=="invalid_discovery_threshold": feedback="\nVALIDATOR_FEEDBACK: invalid_discovery_threshold. discovery_spec.threshold MUST be a finite JSON NUMBER, not a string or range. Valid examples: 0, 0.5, 1, 1.5, -0.5.\n"
  else: feedback=f"\nVALIDATOR_FEEDBACK: {reason}. Regenerate without changing policy or inventing evidence.\n"
 raise ValueError(f"provider_candidate_contract_failed:{last_reason}")
def calibration_feedback(issues):
 return ("\nCALIBRATION_FEEDBACK: strict evidence calibration rejected the candidate. Revise and try again. "
 "Do NOT bypass, reinterpret, or weaken calibration. Evidence sources are provenance, not proof; rationale claims must be directly grounded in the supplied failure analysis. "
 "Hypothesis parameters are proposals to test, not factual claims. Keep the same selected screen-survivor lineage, one conceptual change, executable discovery_spec, and no OOS tuning. "
 f"Verifier diagnostics: {json.dumps(issues,sort_keys=True)}\n")
def main():
 global bc,parent
 failure=Path(os.environ["RESEARCH_FAILURE_ANALYSIS"]); output=Path(os.environ["RESEARCH_CANDIDATE_OUTPUT"]); bc=int(os.environ["RESEARCH_NEXT_BC"]); parent=int(os.environ["RESEARCH_PARENT_BC"])
 prior=os.getenv("RESEARCH_PRIOR_HYPOTHESES","") or os.getenv("RESEARCH_USED_HYPOTHESIS_IDS",""); evidence_text=failure.read_text(encoding="utf-8"); queue=ROOT/'research'/'discovery'/'research_queue.json'
 if not queue.exists(): print("PROVIDER_ROUTER_HOLD missing_screen_queue"); return 0
 try:
  q=json.loads(queue.read_text(encoding='utf-8')); survivors=q.get('candidates',[]) if isinstance(q,dict) else q
  if not isinstance(survivors,list) or not survivors: print("PROVIDER_ROUTER_HOLD empty_screen_queue"); return 0
  selected=survivors[(parent-1)%len(survivors)]
 except Exception as exc: print(f"PROVIDER_ROUTER_HOLD malformed_screen_queue:{exc}"); return 0
 forbidden=prior_discovery_fingerprints()
 prompt=(f"Parent BC: {parent}\nNext BC: {bc}\nREGISTERED_HYPOTHESES: {json.dumps(sorted(HYPOTHESES))}\nPRIOR_HYPOTHESIS_IDS: {prior}\nFORBIDDEN_DISCOVERY_FINGERPRINTS: {json.dumps([list(x) for x in sorted(forbidden,key=str)])}\n\nFAILURE ANALYSIS:\n{evidence_text}\n\nSELECTED SCREEN SURVIVOR (authoritative; translate this one only):\n{json.dumps(selected,sort_keys=True)}\n\nDo not select a different survivor. Preserve the source lineage in evidence_sources and translate only what this survivor supports. The executable discovery_spec must be novel relative to prior campaign candidates.")
 order=[x.strip().lower() for x in os.getenv("RESEARCH_PROVIDER_ORDER","gemini").split(",") if x.strip()]
 for name in order:
  try:
   candidate=request_candidate(name,prompt,forbidden)
   if candidate.get("status")=="HOLD": print(f"PROVIDER_{name.upper()}_HOLD"); continue
   base,model,key=config(name)
   for calibration_attempt in range(3):
    calibrated,issues=verify_with_openai_compatible(base,model,key,candidate,evidence_text)
    if calibrated:
     write_candidate(output,candidate); print(f"PROVIDER_SELECTED {name} model={model} hash={candidate['candidate_hash']} calibration_attempt={calibration_attempt+1}"); return 0
    print(f"PROVIDER_CALIBRATION_FAIL {name} attempt={calibration_attempt+1} issues={json.dumps(issues,sort_keys=True)}",flush=True)
    if calibration_attempt==2: break
    revision_prompt=prompt+"\n\nPREVIOUS CANDIDATE REJECTED BY STRICT CALIBRATION:\n"+json.dumps(candidate,sort_keys=True)+calibration_feedback(issues)
    revision_forbidden=set(forbidden); fp=discovery_fingerprint(candidate)
    if fp is not None: revision_forbidden.add(fp)
    candidate=request_candidate(name,revision_prompt,revision_forbidden)
    if candidate.get("status")=="HOLD": break
  except Exception as exc: print(f"PROVIDER_FAIL {name}: {exc}")
 print("PROVIDER_ROUTER_HOLD"); return 0
if __name__=="__main__":raise SystemExit(main())
