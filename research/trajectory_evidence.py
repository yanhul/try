"""TRY research-side trajectory evidence and diagnostic attribution.

Separates immutable raw provider output from normalized tool-call views and from
evaluation/credit. Diagnostic interventions are recorded as experiments, not
treated as fixes or success signals.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

def _canon(v:Any)->str:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def _digest(v:Any)->str:
    return sha256(_canon(v).encode()).hexdigest()

@dataclass(frozen=True)
class StepEvidence:
    trajectory_id:str
    step_id:str
    attempt_id:str
    raw_output:str
    normalized_tool_calls:tuple[Mapping[str,Any],...]
    outcome_class:str
    intervention_id:str|None=None
    def __post_init__(self):
        for v,n in ((self.trajectory_id,"trajectory_id"),(self.step_id,"step_id"),
                    (self.attempt_id,"attempt_id"),(self.outcome_class,"outcome_class")):
            if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty")
        if not isinstance(self.raw_output,str): raise ValueError("raw_output must be a string")
        for c in self.normalized_tool_calls:
            if not isinstance(c,Mapping) or not c.get("name"): raise ValueError("tool call name required")
    @property
    def raw_digest(self): return _digest(self.raw_output)
    @property
    def normalized_digest(self): return _digest(list(self.normalized_tool_calls))
    @property
    def evidence_digest(self): return _digest(self.as_record(False))
    def as_record(self,include_digest=True):
        r={"trajectory_id":self.trajectory_id,"step_id":self.step_id,"attempt_id":self.attempt_id,
           "raw_output":self.raw_output,"raw_output_digest":self.raw_digest,
           "normalized_tool_calls":[dict(x) for x in self.normalized_tool_calls],
           "normalized_digest":self.normalized_digest,"outcome_class":self.outcome_class,
           "intervention_id":self.intervention_id}
        if include_digest:r["evidence_digest"]=self.evidence_digest
        return r

@dataclass(frozen=True)
class DiagnosticIntervention:
    intervention_id:str
    hypothesis:str
    parameter_changes:Mapping[str,Any]
    def as_record(self):
        if not self.intervention_id or not self.hypothesis: raise ValueError("intervention identity required")
        return {"intervention_id":self.intervention_id,"hypothesis":self.hypothesis,
                "parameter_changes":dict(self.parameter_changes)}

def validate_step(record:Mapping[str,Any])->StepEvidence:
    obj=StepEvidence(record["trajectory_id"],record["step_id"],record["attempt_id"],
        record["raw_output"],tuple(record.get("normalized_tool_calls",())),
        record["outcome_class"],record.get("intervention_id"))
    if record.get("raw_output_digest")!=obj.raw_digest: raise ValueError("raw output digest mismatch")
    if record.get("normalized_digest")!=obj.normalized_digest: raise ValueError("normalized digest mismatch")
    if record.get("evidence_digest")!=obj.evidence_digest: raise ValueError("evidence digest mismatch")
    return obj

def require_credit_inputs(record:Mapping[str,Any])->StepEvidence:
    obj=validate_step(record)
    if obj.outcome_class.endswith("FAILURE") or obj.outcome_class=="UNKNOWN":
        raise ValueError("step outcome is not creditable")
    return obj
