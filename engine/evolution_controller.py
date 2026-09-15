"""Bounded evolutionary search for ASTRA.

ASTRA proposes and ranks candidates. It never owns Research promotion authority.
The authoritative lifecycle/evidence gate remains outside this controller.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json, math
from typing import Any, Callable, Mapping, Sequence
from .experiment_ledger import ExperimentRecord, JsonlExperimentLedger

IMMUTABLE_KEYS=frozenset({"dataset","dataset_identity","evaluator","evaluation_spec","cost_model","oos_policy","promotion_policy","evidence_policy"})
ALLOWED_MUTATIONS=frozenset({"stop_fraction","reward_multiple","pnf_box_fraction","candidate_family","candidate_spec"})
EVALUATION_STATUSES=frozenset({"SUCCEEDED","REJECTED","INVALID","FAILED","CRASHED"})

def _reject_immutable(value: Any, path: str="candidate") -> None:
    if isinstance(value,Mapping):
        for key,nested in value.items():
            if key in IMMUTABLE_KEYS: raise ValueError(f"immutable_candidate_fields:{path}.{key}")
            _reject_immutable(nested,f"{path}.{key}")
    elif isinstance(value,(list,tuple)):
        for i,nested in enumerate(value): _reject_immutable(nested,f"{path}[{i}]")

def canonical_candidate(config: Mapping[str,Any])->dict[str,Any]:
    _reject_immutable(config); return json.loads(json.dumps(dict(config),sort_keys=True,ensure_ascii=False))

def candidate_id(config: Mapping[str,Any])->str:
    payload=json.dumps(canonical_candidate(config),sort_keys=True,separators=(",",":"),ensure_ascii=False); return hashlib.sha256(payload.encode()).hexdigest()

def mutate(parent: Mapping[str,Any],field:str,value:Any)->dict[str,Any]:
    if field not in ALLOWED_MUTATIONS: raise ValueError(f"mutation_not_allowed:{field}")
    child=canonical_candidate(parent); child[field]=value; return canonical_candidate(child)

@dataclass(frozen=True)
class Candidate:
    config: Mapping[str,Any]; parent_id: str|None=None
    @property
    def id(self)->str:return candidate_id(self.config)

@dataclass(frozen=True)
class Evaluation:
    status:str; score:float|None; result:Mapping[str,Any]; failure_class:str|None=None

def _mutation_field(parent:Mapping[str,Any],candidate:Mapping[str,Any])->str|None:
    changed=[k for k in set(parent)|set(candidate) if parent.get(k)!=candidate.get(k)]; allowed=[k for k in changed if k in ALLOWED_MUTATIONS]
    return allowed[0] if len(allowed)==1 else None

def rank_mutations(parent:Mapping[str,Any],mutations:Sequence[tuple[str,Any]],ledger:JsonlExperimentLedger,failure_class:str|None=None)->list[tuple[str,Any]]:
    unique=[];seen=set()
    for field,value in mutations:
        if field not in ALLOWED_MUTATIONS:continue
        key=json.dumps([field,value],sort_keys=True,ensure_ascii=False,separators=(",",":"))
        if key not in seen:seen.add(key);unique.append((field,value))
    if len(unique)<2:return unique
    stats={field:[0.0,0.0] for field,_ in unique};context={field:[0.0,0.0] for field,_ in unique}
    for record in ledger.unique_terminal_evaluations().values():
        result=record.get("result") or {};config=result.get("candidate")
        if not isinstance(config,Mapping):continue
        field=_mutation_field(parent,config)
        if field not in stats:continue
        good=record.get("status")=="SUCCEEDED";stats[field][0 if good else 1]+=1
        if failure_class and str(record.get("failure_class") or "")==failure_class:context[field][0 if good else 1]+=1
    total=sum(g+b for g,b in stats.values());priorities={}
    for field,(good,bad) in stats.items():
        trials=good+bad
        if not trials:priorities[field]=float("inf");continue
        mean=(good+1.0)/(trials+2.0);bonus=math.sqrt(2.0*math.log(total+1.0)/trials)
        cg,cb=context[field];ct=cg+cb; contextual=((cg+1.0)/(ct+2.0))*0.35 if ct else 0.0
        priorities[field]=mean+bonus+contextual
    return sorted(unique,key=lambda x:(-priorities[x[0]],x[0],json.dumps(x[1],sort_keys=True,ensure_ascii=False)))

class EvolutionController:
    def __init__(self,ledger:JsonlExperimentLedger,evaluator:Callable[[Mapping[str,Any]],Evaluation]):self.ledger=ledger;self.evaluator=evaluator
    def propose(self,parent:Candidate,mutations:Sequence[tuple[str,Any]],limit:int=8,failure_class:str|None=None)->list[Candidate]:
        if limit<1:raise ValueError("limit must be positive")
        ordered=rank_mutations(parent.config,mutations,self.ledger,failure_class);seen=set();out=[]
        for field,value in ordered:
            child=Candidate(mutate(parent.config,field,value),parent.id)
            if child.id==parent.id or child.id in seen:continue
            seen.add(child.id);out.append(child)
            if len(out)>=limit:break
        return out
    def evaluate(self,candidate:Candidate,hypothesis_id:str="astra")->Evaluation:
        existing=self.ledger.terminal_evaluation(candidate.id)
        if existing:
            result=existing.get("result") or {};return Evaluation(existing["status"],result.get("score"),result,existing.get("failure_class"))
        self.ledger.append(ExperimentRecord(candidate.id,hypothesis_id,"PROPOSED",candidate.parent_id,configuration_identity=candidate.id,result={"candidate":candidate.config}))
        try:evaluation=self.evaluator(candidate.config)
        except Exception as exc:evaluation=Evaluation("CRASHED",None,{"error":str(exc)},"EXECUTION_EXCEPTION")
        if evaluation.status not in EVALUATION_STATUSES:raise ValueError(f"invalid_evaluation_status:{evaluation.status}")
        self.ledger.append(ExperimentRecord(candidate.id,hypothesis_id,evaluation.status,candidate.parent_id,configuration_identity=candidate.id,result=dict(evaluation.result),failure_class=evaluation.failure_class));return evaluation
    def rank(self,candidate:Candidate,evaluation:Evaluation,baseline:Evaluation,hypothesis_id:str="astra")->str:
        for record in reversed(self.ledger.read()):
            if record.get("experiment_id")==candidate.id and record.get("status")=="RANKED":return str(record.get("decision") or "REJECT")
        preference=self.compare(evaluation,baseline);self.ledger.append(ExperimentRecord(candidate.id,hypothesis_id,"RANKED",candidate.parent_id,configuration_identity=candidate.id,result={"score":evaluation.score,"baseline_score":baseline.score},decision=preference));return preference
    def run_generation(self,parent:Candidate,mutations:Sequence[tuple[str,Any]],baseline:Evaluation,limit:int=8,hypothesis_id:str="astra",failure_class:str|None=None)->Candidate:
        candidates=self.propose(parent,mutations,limit,failure_class);best=parent;best_score=baseline.score if baseline.status=="SUCCEEDED" else None
        for candidate in candidates:
            evaluation=self.evaluate(candidate,hypothesis_id);preference=self.rank(candidate,evaluation,baseline,hypothesis_id)
            if preference=="PREFER" and evaluation.score is not None and (best_score is None or evaluation.score>best_score):best,best_score=candidate,evaluation.score
        return best
    @staticmethod
    def compare(candidate:Evaluation,baseline:Evaluation)->str:
        if candidate.status!="SUCCEEDED" or baseline.status!="SUCCEEDED" or candidate.score is None or baseline.score is None:return "REJECT"
        return "PREFER" if candidate.score>baseline.score else "REJECT"

__all__=["ALLOWED_MUTATIONS","Candidate","Evaluation","EvolutionController","candidate_id","canonical_candidate","mutate","rank_mutations"]
