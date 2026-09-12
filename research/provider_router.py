#!/usr/bin/env python3
"""Strict provider router: deterministic discovery population narrows; Gemini translates one selected survivor."""
from __future__ import annotations
import json, math, os, random, sys, time, urllib.error, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from research.autonomous_hypothesis import write_candidate, validate_candidate
from engine.hypotheses import HYPOTHESES
from research.evidence_calibration import verify_with_openai_compatible
OPERATORS=["identity","difference","ratio","zscore","rolling_mean","rolling_std","lag","delta","rank"]
COLUMNS=["open","high","low","close","volume","volume_ratio","range_ratio","close_location","vwap_distance"]
WINDOWS=[3,5,10,20,50,100]
ALLOWED_THRESHOLDS=[-0.5,0,0.5,1,1.5]
SYSTEM=f"""You are an autonomous trading-research translator.
A deterministic population engine has already screened a public-source universe.
You MUST translate the single SELECTED SCREEN SURVIVOR supplied by the controller. You are not a survivor selector.
Do not select by expected performance, stars, OOS, or intuition. Do not replace the selected survivor with another source.
Registered hypothesis_ids are allowed; otherwise use hypothesis_id='discovered_primitive'.
For discovered_primitive, use ONLY operators {OPERATORS}, columns {COLUMNS}, windows {WINDOWS}.
A discovery_spec MUST contain operator,left,numeric threshold,direction ('above'/'below'); difference/ratio also require right.
For difference/ratio, right MUST be exactly one of the allowed columns {COLUMNS}. Do not use aliases such as price, return, pct_change, typical_price, or other invented column names. left and right are schema column identifiers, not natural-language labels.
For threshold, output a plain finite JSON number. Prefer one of {ALLOWED_THRESHOLDS}. NEVER output ranges, percentages, expressions, null, objects, arrays, strings, or prose as threshold.
If the selected survivor does not itself determine a numeric threshold, use threshold 0; threshold is a test parameter, not evidence.
Threshold and direction are a proposal to be tested, NOT evidence and NOT proof. Do not use OOS to select or tune.
Do not invent evidence. Exactly one conceptual change. Return JSON only with keys:
hypothesis_id,conceptual_change,evidence_sources,rationale,is_testable,oos_selection_used,discovery_spec.
"""
def config(name):
 n=name.upper(); defaults={"GEMINI":("https://generativelanguage.googleapis.com/v1beta/openai/",os.getenv("GEMINI_MODEL","gemini-3.1-flash-lite"),"GEMINI_API_KEY"),"DEEPSEEK":("https://api.deepseek.com",os.getenv("DEEPSEEK_MODEL","deepseek-v4-flash"),"DEEPSEEK_API_KEY")}
 if n in defaults: base,model,keyvar=defaults[n]
 else: base=os.getenv(f"RESEARCH_PROVIDER_{n}_BASE_URL",""); model=os.getenv(f"RESEARCH_PROVIDER_{n}_MODEL",""); keyvar=f"RESEARCH_PROVIDER_{n}_API_KEY"
 return base.rstrip("/"),model,os.getenv(keyvar,"")

_PROVIDER_LAST_CALL=0.0

def _min_interval():
 try: return max(0.0,float(os.getenv("RESEARCH_PROVIDER_MIN_INTERVAL_SECONDS","3")))
 except ValueError: return 3.0

def _sleep_for_rate_limit(seconds):
 delay=max(0.0,float(seconds))
 if delay: time.sleep(min(delay,float(os.getenv("RESEARCH_PROVIDER_BACKOFF_CAP_SECONDS","120"))))

def _retry_after(exc,attempt):
 headers=exc.headers or {}
 value=headers.get("Retry-After") or headers.get("retry-after")
 if value:
  try: return max(1.0,float(value))
  except ValueError: pass
 # Some OpenAI-compatible gateways expose a reset epoch instead of Retry-After.
 for key in ("X-RateLimit-Reset","x-ratelimit-reset","X-RateLimit-Reset-Requests","x-ratelimit-reset-requests"):
  value=headers.get(key)
  if value:
   try:
    reset=float(value)
    if reset > time.time(): return max(1.0,reset-time.time())
   except ValueError: pass
 # Last resort: bounded exponential backoff with small jitter.
 return min(float(os.getenv("RESEARCH_PROVIDER_BACKOFF_CAP_SECONDS","120")),2.0 ** attempt + random.uniform(0,1))

def _rate_error_detail(exc):
 try:
  raw=exc.read().decode("utf-8","replace")
  try:
   payload=json.loads(raw)
   text=json.dumps(payload,sort_keys=True)
  except Exception: text=raw
  return text[:1000]
 except Exception: return ""

def call(name,prompt):
 global _PROVIDER_LAST_CALL
 base,model,key=config(name)
 if not base or not model or not key: raise RuntimeError(f"provider_not_configured:{name}")
 body={"model":model,"messages":[{"role":"system","content":SYSTEM},{"role":"user","content":prompt}],"max_tokens":1400,"response_format":{"type":"json_object"}}
 req=urllib.request.Request(base+"/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},method="POST")
 # Rate-limit protection is deliberately outside the agent's policy: it only slows calls.
 interval=_min_interval()
 gap=interval-(time.monotonic()-_PROVIDER_LAST_CALL)
 if gap>0: time.sleep(gap)
 _PROVIDER_LAST_CALL=time.monotonic()
 max_rate_retries=max(0,int(os.getenv("RESEARCH_PROVIDER_RATE_RETRIES","1")))
 for attempt in range(max_rate_retries+1):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:return json.loads(r.read().decode())["choices"][0]["message"]["content"]
  except urllib.error.HTTPError as exc:
   if exc.code in {429,500,502,503,504}:
    detail=_rate_error_detail(exc)
    if exc.code==429 and attempt < max_rate_retries:
     delay=_retry_after(exc,attempt)
     print(f"PROVIDER_RATE_LIMIT name={name} attempt={attempt+1}/{max_rate_retries+1} backoff={delay:.1f}s detail={detail}",flush=True)
     _sleep_for_rate_limit(delay)
     _PROVIDER_LAST_CALL=time.monotonic()
     continue
    if exc.code==429:
     raise RuntimeError(f"provider_rate_limited:{name}:retry_exhausted:{detail}") from exc
    if attempt < max_rate_retries:
     delay=_retry_after(exc,attempt)
     _sleep_for_rate_limit(delay)
     _PROVIDER_LAST_CALL=time.monotonic()
     continue
   raise
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
 for attempt in range(3):
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
  elif reason=="invalid_discovery_threshold":
   bad_spec=candidate.get("discovery_spec"); feedback=("\nVALIDATOR_FEEDBACK: invalid_discovery_threshold. The exact rejected discovery_spec was: "+json.dumps(bad_spec,sort_keys=True)+". Replace discovery_spec.threshold with a plain finite JSON NUMBER, preferably exactly 0. Do not emit a string, range, percentage, expression, null, object, or array. Also ensure direction is exactly 'above' or 'below'. If the source does not determine a threshold, use 0.\n")
  elif reason=="invalid_discovery_right_column":
   bad_spec=candidate.get("discovery_spec"); bad_right=bad_spec.get("right") if isinstance(bad_spec,dict) else None; feedback=("\nVALIDATOR_FEEDBACK: invalid_discovery_right_column. The rejected discovery_spec.right was "+json.dumps(bad_right)+". For difference/ratio, right MUST be exactly one of these schema columns: "+json.dumps(COLUMNS)+". Do not use aliases or natural-language names. Regenerate the same selected-survivor lineage with a schema-valid right column, or choose a non-binary operator only if that is the faithful executable translation of the selected survivor. Do not invent evidence or change policy.\n")
  else: feedback=f"\nVALIDATOR_FEEDBACK: {reason}. Regenerate without changing policy or inventing evidence.\n"
 raise ValueError(f"provider_candidate_contract_failed:{last_reason}")
def calibration_feedback(issues):
 return ("\nCALIBRATION_FEEDBACK: strict evidence calibration rejected the candidate. Revise and try again. Do NOT bypass, reinterpret, or weaken calibration. Evidence sources are provenance, not proof; rationale claims must be directly grounded in the supplied failure analysis. Hypothesis parameters are proposals to test, not factual claims. Keep the same selected screen-survivor lineage, one conceptual change, executable discovery_spec, and no OOS tuning. " f"Verifier diagnostics: {json.dumps(issues,sort_keys=True)}\n")
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
