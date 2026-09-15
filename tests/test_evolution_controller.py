import pytest
from engine.astra_evaluator import build_evaluator
from engine.evolution_controller import Candidate, Evaluation, EvolutionController, candidate_id, mutate, rank_mutations
from engine.experiment_ledger import ExperimentRecord, JsonlExperimentLedger

def test_mutation_is_bounded_and_deterministic():
    parent={"stop_fraction":0.01,"reward_multiple":2.0}; child=mutate(parent,"reward_multiple",3.0)
    assert child["reward_multiple"]==3.0; assert candidate_id(child)==candidate_id(dict(reversed(list(child.items()))))
    with pytest.raises(ValueError): mutate(parent,"evaluation_spec",{})

def test_immutable_fields_are_rejected():
    with pytest.raises(ValueError): candidate_id({"dataset_identity":"abc","reward_multiple":2.0})
    with pytest.raises(ValueError): candidate_id({"candidate_spec":{"promotion_policy":"bad"}})

def test_crash_is_persisted(tmp_path):
    ledger=JsonlExperimentLedger(tmp_path/"ledger.jsonl")
    def boom(_): raise RuntimeError("boom")
    result=EvolutionController(ledger,boom).evaluate(Candidate({"reward_multiple":2.0}))
    assert result.status=="CRASHED"; records=ledger.read(); assert [r["status"] for r in records]==["PROPOSED","CRASHED"]; assert records[-1]["failure_class"]=="EXECUTION_EXCEPTION"

def test_propose_preserves_parent_lineage(tmp_path):
    controller=EvolutionController(JsonlExperimentLedger(tmp_path/"ledger.jsonl"),lambda _: Evaluation("SUCCEEDED",2.0,{"score":2.0}))
    parent=Candidate({"reward_multiple":2.0}); children=controller.propose(parent,[("reward_multiple",2.5),("reward_multiple",3.0)],limit=2)
    assert len(children)==2 and all(c.parent_id==parent.id for c in children)

def test_compare_is_ranking_signal_not_promotion():
    baseline=Evaluation("SUCCEEDED",2.0,{})
    assert EvolutionController.compare(Evaluation("SUCCEEDED",3.0,{}),baseline)=="PREFER"
    assert EvolutionController.compare(Evaluation("REJECTED",9.0,{}),baseline)=="REJECT"

def test_rank_persists_non_authoritative_preference(tmp_path):
    ledger=JsonlExperimentLedger(tmp_path/"ledger.jsonl"); controller=EvolutionController(ledger,lambda _: Evaluation("SUCCEEDED",3.0,{}))
    candidate=Candidate({"reward_multiple":3.0}); evaluation=Evaluation("SUCCEEDED",3.0,{"score":3.0}); baseline=Evaluation("SUCCEEDED",2.0,{"score":2.0})
    assert controller.rank(candidate,evaluation,baseline)=="PREFER"
    assert ledger.last(candidate.id)["status"]=="RANKED"; assert ledger.last(candidate.id)["decision"]=="PREFER"
    assert all(r["status"]!="PROMOTED" for r in ledger.read())

def test_generation_reuses_terminal_evidence(tmp_path):
    ledger=JsonlExperimentLedger(tmp_path/"ledger.jsonl"); calls=[]
    def evaluator(config): calls.append(config); return Evaluation("SUCCEEDED",float(config["reward_multiple"]),{"score":float(config["reward_multiple"])})
    controller=EvolutionController(ledger,evaluator); parent=Candidate({"reward_multiple":2.0}); baseline=Evaluation("SUCCEEDED",2.0,{"score":2.0}); mutations=[("reward_multiple",3.0),("reward_multiple",4.0)]
    best1=controller.run_generation(parent,mutations,baseline,limit=2); best2=controller.run_generation(parent,mutations,baseline,limit=2)
    assert best1.id==best2.id and best1.config["reward_multiple"]==4.0 and len(calls)==2
    statuses=[r["status"] for r in ledger.read()]; assert statuses.count("PROPOSED")==2; assert statuses.count("SUCCEEDED")==2; assert statuses.count("RANKED")==2

def test_adaptive_mutation_prefers_proven_field(tmp_path):
    ledger=JsonlExperimentLedger(tmp_path/"ledger.jsonl"); parent={"reward_multiple":2.0,"stop_fraction":0.01}
    for i in range(4):
        c=mutate(parent,"reward_multiple",3.0+i); ledger.append(ExperimentRecord(candidate_id(c),"astra","PROPOSED",result={"candidate":c})); ledger.append(ExperimentRecord(candidate_id(c),"astra","SUCCEEDED",result={"candidate":c,"score":1.0}))
    for i in range(4):
        c=mutate(parent,"stop_fraction",0.02+i*0.001); ledger.append(ExperimentRecord(candidate_id(c),"astra","PROPOSED",result={"candidate":c})); ledger.append(ExperimentRecord(candidate_id(c),"astra","FAILED",result={"candidate":c},failure_class="OOS_FAIL"))
    ordered=rank_mutations(parent,[("stop_fraction",0.05),("reward_multiple",8.0)],ledger)
    assert ordered[0][0]=="reward_multiple"

def test_contextual_failure_signal_reorders_mutation_field(tmp_path):
    ledger=JsonlExperimentLedger(tmp_path/"ledger.jsonl"); parent={"reward_multiple":2.0,"stop_fraction":0.01}
    c1=mutate(parent,"reward_multiple",3.0); ledger.append(ExperimentRecord(candidate_id(c1),"astra","FAILED",result={"candidate":c1},failure_class="OOS_FAIL"))
    c2=mutate(parent,"stop_fraction",0.02); ledger.append(ExperimentRecord(candidate_id(c2),"astra","SUCCEEDED",result={"candidate":c2,"score":1.0},failure_class="OOS_FAIL"))
    ordered=rank_mutations(parent,[("reward_multiple",4.0),("stop_fraction",0.03)],ledger,failure_class="OOS_FAIL")
    assert ordered[0][0]=="stop_fraction"

def test_controller_mutation_reaches_real_evaluator(monkeypatch):
    calls=[]
    def fake_split(bars,start,end,predicate,stop,rr,**kwargs):
        calls.append((stop,rr,kwargs["pnf_box_fraction"],kwargs["candidate_family"]))
        return {"metrics":{"profit_factor":1.1,"total_return":rr},"accepted_signals":1}
    monkeypatch.setattr("engine.astra_evaluator.evaluate_split",fake_split)
    evaluator=build_evaluator("data/BTCUSDT_1h.csv"); parent=Candidate({"hypothesis_id":"baseline","stop_fraction":0.01,"reward_multiple":2.0,"pnf_box_fraction":0.01}); child=Candidate(mutate(parent.config,"reward_multiple",3.0),parent.id); result=evaluator(child.config)
    assert result.status=="SUCCEEDED" and result.score==3.0 and calls==[(0.01,3.0,0.01,None),(0.01,3.0,0.01,None),(0.01,3.0,0.01,None)]
