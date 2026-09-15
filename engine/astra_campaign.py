"""Durable ASTRA search loop: bounded mutation, evidence, ranking, resume."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .astra_evaluator import build_evaluator
from .evolution_controller import Candidate, Evaluation, EvolutionController
from .experiment_ledger import JsonlExperimentLedger

@dataclass(frozen=True)
class CampaignState:
    generation:int
    parent:dict[str,Any]
    baseline_score:float|None
    terminal:bool=False
    failure_class:str|None=None

def _save(path:Path,state:CampaignState)->None:
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps({"generation":state.generation,"parent":state.parent,"baseline_score":state.baseline_score,"terminal":state.terminal,"failure_class":state.failure_class},sort_keys=True,ensure_ascii=False),encoding="utf-8")
    tmp.replace(path)

def load_state(path:str|Path)->CampaignState|None:
    p=Path(path)
    if not p.exists(): return None
    raw=json.loads(p.read_text(encoding="utf-8"))
    return CampaignState(int(raw["generation"]),dict(raw["parent"]),raw.get("baseline_score"),bool(raw.get("terminal",False)),raw.get("failure_class"))

def _unique_mutations(items:list[tuple[str,Any]])->list[tuple[str,Any]]:
    seen=set(); out=[]
    for field,value in items:
        key=(field,json.dumps(value,sort_keys=True,separators=(",",":")))
        if key not in seen: seen.add(key); out.append((field,value))
    return out

def _mutations(parent:Candidate,generation:int)->list[tuple[str,Any]]:
    """Coarse-to-fine coordinate search; no policy/evaluator field can mutate."""
    c=parent.config; stop=max(1e-6,float(c.get("stop_fraction",0.01))); rr=max(0.25,float(c.get("reward_multiple",2.0))); pnf=max(1e-6,float(c.get("pnf_box_fraction",0.01)))
    phase=generation%3
    if phase==0:
        stop_scales=(0.60,0.80,1.25,1.60); rr_delta=(-1.0,-0.5,0.5,1.0); pnf_scales=(0.60,0.80,1.25,1.60)
    elif phase==1:
        stop_scales=(0.85,0.925,1.08,1.175); rr_delta=(-0.25,-0.1,0.1,0.25); pnf_scales=(0.85,0.925,1.08,1.175)
    else:
        stop_scales=(0.95,1.05); rr_delta=(-0.1,0.1); pnf_scales=(0.95,1.05)
    items=[]
    items += [("stop_fraction",round(stop*x,8)) for x in stop_scales]
    items += [("reward_multiple",round(max(0.25,rr+x),8)) for x in rr_delta]
    items += [("pnf_box_fraction",round(pnf*x,8)) for x in pnf_scales]
    return _unique_mutations(items)

def _last_evaluation(ledger:JsonlExperimentLedger, candidate_id:str)->dict[str,Any]|None:
    terminal={"SUCCEEDED","REJECTED","INVALID","FAILED","CRASHED"}
    found=None
    for record in ledger.read():
        if record.get("experiment_id")==candidate_id and record.get("status") in terminal: found=record
    return found

def _parent_failure(ledger:JsonlExperimentLedger,parent:Candidate)->str|None:
    record=_last_evaluation(ledger,parent.id)
    value=(record or {}).get("failure_class")
    return str(value) if value else None

def run_campaign(data_path:str|Path,ledger_path:str|Path,state_path:str|Path,*,max_generations:int=100,generation_limit:int=6)->CampaignState:
    if max_generations<1 or generation_limit<1: raise ValueError("campaign limits must be positive")
    ledger=JsonlExperimentLedger(ledger_path); controller=EvolutionController(ledger,build_evaluator(data_path)); state=load_state(state_path)
    if state is None:
        parent=Candidate({"hypothesis_id":"baseline","stop_fraction":0.01,"reward_multiple":2.0,"pnf_box_fraction":0.01})
        baseline=controller.evaluate(parent,hypothesis_id="astra"); state=CampaignState(0,dict(parent.config),baseline.score,False,baseline.failure_class); _save(Path(state_path),state)
    while state.generation<max_generations:
        parent=Candidate(state.parent); baseline=Evaluation("SUCCEEDED",state.baseline_score,{"score":state.baseline_score},state.failure_class)
        failure_class=state.failure_class or _parent_failure(ledger,parent)
        best=controller.run_generation(parent,_mutations(parent,state.generation),baseline,limit=generation_limit,hypothesis_id="astra",failure_class=failure_class)
        score=state.baseline_score; next_failure=_parent_failure(ledger,best)
        if best.id!=parent.id:
            ranked=controller.ledger.last(best.id)
            if ranked: score=(ranked.get("result") or {}).get("score",score)
        state=CampaignState(state.generation+1,dict(best.config),score,state.generation+1>=max_generations,next_failure); _save(Path(state_path),state)
    return state

__all__=["CampaignState","load_state","run_campaign"]
