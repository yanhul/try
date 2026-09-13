"""Evaluate atomic and bounded composite hypotheses under the same execution model."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
from pathlib import Path
from .backtest import load_bars
from .data_split import chronological_split, validate_splits
from .features import extract_features
from .specific_features import extract_specific_features
from .context_features import gann_reference,multi_timeframe_context,point_figure_directions,PnFConfig,rolling_volatility,rolling_volume_profile_poc,vwap
from .execution import execute_trades
from .ledger import LedgerTrade,build_ledger
from .metrics import Trade,calculate_metrics
from .risk_exit import FixedRiskRewardExit
from .strategy import ReferenceStrategy
from .hypotheses import HYPOTHESES
from .composition import generate_composites
from .trading_features import momentum_trend,mean_reversion_zscore,volume_spread
from .events import Direction
from research.cost_model import CostModel

@dataclass(frozen=True)
class PreparedSplit:
    history:list
    ledger:list
    contexts:list[dict[str,dict]]
    candidate_universe:str="reference_event_ledger"

def _sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
 return h.hexdigest()

def _trade_metrics(bars,ledger,stop,rr,cost,*,cost_model: CostModel | None = None):
 executed,skipped=execute_trades(bars,ledger,FixedRiskRewardExit(stop,rr))
 trades=[Trade(t.ledger_trade.entry_price,t.exit.price,t.ledger_trade.direction.value,t.ledger_trade.entry_bar,t.exit.bar_index,t.exit.reason) for t in executed]
 return calculate_metrics(trades,cost,cost_model=cost_model),skipped

def _feature_rows(history,pnf_box_fraction):
 features=extract_features(history); specific=extract_specific_features(history); vol=rolling_volatility(history); vw=vwap(history); gann=gann_reference(history); mtf=multi_timeframe_context(history); vp_poc=rolling_volume_profile_poc(history)
 first_close=abs(history[0].close) if history else 1.0; box=max(1e-9,first_close*pnf_box_fraction); pnf_direction=point_figure_directions(history,PnFConfig(box_size=box))
 mom=momentum_trend(history); mr=mean_reversion_zscore(history); vsa=volume_spread(history)
 def row(index):
  base=dict(features[index]); base.update(specific[index]); base["close"]=history[index].close; base["open"]=history[index].open; base["high"]=history[index].high; base["low"]=history[index].low; base["volume"]=history[index].volume; base["volatility"]=vol[index]; base["vwap"]=vw[index]; base["vwap_distance"]=((history[index].close-vw[index])/vw[index]) if vw[index] else None; base["volume_ratio"]=(history[index].volume/history[index-1].volume) if index>0 and history[index-1].volume else None; base["range_ratio"]=((history[index].high-history[index].low)/(history[index-1].high-history[index-1].low)) if index>0 and history[index-1].high!=history[index-1].low else None; base["close_location"]=((history[index].close-history[index].low)/(history[index].high-history[index].low)) if history[index].high!=history[index].low else None; base["volume_profile_poc"]=vp_poc[index]; base.update(mtf[index]); base["gann_slope"]=gann[index]["slope"]; base["pnf_direction"]=pnf_direction[index]; base["momentum_trend"]=mom[index]; base["mean_reversion"]=mr[index]; base["wyckoff_vsa_vpa"]=vsa[index]["close_location"]; base["regime"]=mtf[index].get("regime",0); base["seasonality"]=history[index].timestamp.weekday(); base["point_figure"]=pnf_direction[index]; base["gann_reference"]=gann[index]["slope"]; base["vwap_volume_profile"]=((history[index].close-vw[index])/vw[index]) if vw[index] else None; base["smc_ict"]=0.0; base["fvg_imbalance"]=0.0; return base
 return [row(i) for i in range(len(history))]

def _direction_for_row(row,family):
 if family=="momentum_trend": return Direction.BULLISH if (row.get("momentum_trend") or 0)>0 else Direction.BEARISH
 if family=="mean_reversion": return Direction.BULLISH if (row.get("mean_reversion") or 0)<0 else Direction.BEARISH
 if family=="vwap_volume_profile": return Direction.BULLISH if (row.get("vwap_volume_profile") or 0)>=0 else Direction.BEARISH
 if family=="regime": return Direction.BULLISH if bool(row.get("mtf_fast_bullish")) else Direction.BEARISH
 if family=="point_figure": return Direction.BULLISH if row.get("point_figure")=="X" else Direction.BEARISH
 if family=="gann_reference": return Direction.BULLISH if (row.get("gann_reference") or 0)>0 else Direction.BEARISH
 if family=="wyckoff_vsa_vpa": return Direction.BULLISH if (row.get("close_location") or 0)>=0.5 else Direction.BEARISH
 if family=="volatility": return Direction.BULLISH if row.get("close",0)>=row.get("open",0) else Direction.BEARISH
 if family=="seasonality": return Direction.BULLISH if row.get("close",0)>=row.get("open",0) else Direction.BEARISH
 return Direction.BULLISH if row.get("close",0)>=row.get("open",0) else Direction.BEARISH

def prepare_split(bars,start,end,*,pnf_box_fraction=0.01,candidate_universe="reference_event_ledger",candidate_family=None,candidate_spec=None):
 if pnf_box_fraction<=0: raise ValueError("pnf_box_fraction must be positive")
 history=bars[:end]; rows=_feature_rows(history,pnf_box_fraction)
 if candidate_universe=="all_bars":
  family=str(candidate_family or "")
  ledger=[]; contexts=[]
  for i in range(max(1,start),end):
   row=rows[i]
   direction=_direction_for_row(row,family)
   if family=="discovered_primitive":
    direction=Direction.BULLISH if (candidate_spec or {}).get("direction")=="above" else Direction.BEARISH
   ledger.append(LedgerTrade(direction,i,i,i,i,row["close"]))
   contexts.append({"sweep":row,"mss":row,"fvg":row,"entry":row,"history":rows[:i+1]})
  return PreparedSplit(history=history,ledger=ledger,contexts=contexts,candidate_universe="all_bars")
 events=ReferenceStrategy().process(history); ledger=[t for t in build_ledger(events) if start<=t.entry_bar<end]
 contexts=[]
 for t in ledger:
  entry=rows[t.entry_bar].copy()
  contexts.append({"sweep":rows[t.sweep_bar],"mss":rows[t.mss_bar],"fvg":rows[t.fvg_bar],"entry":entry,"history":rows[:t.entry_bar+1]})
 return PreparedSplit(history=history,ledger=ledger,contexts=contexts,candidate_universe="reference_event_ledger")

def evaluate_prepared_split(prepared,predicate,stop=0.01,rr=2.0,cost=0.0,*,cost_model: CostModel | None = None):
 filtered=[t for t,ctx in zip(prepared.ledger,prepared.contexts) if predicate(ctx,t.direction.value)]
 metrics,skipped=_trade_metrics(prepared.history,filtered,stop,rr,cost,cost_model=cost_model)
 return {"candidate_trades":len(prepared.ledger),"accepted_signals":len(filtered),"skipped_overlap_trades":skipped,"candidate_universe":prepared.candidate_universe,"metrics":metrics}

def evaluate_split(bars,start,end,predicate,stop=0.01,rr=2.0,cost=0.0,*,prepared=None,pnf_box_fraction=0.01,cost_model: CostModel | None = None,candidate_universe="reference_event_ledger",candidate_family=None,candidate_spec=None):
 prepared=prepared or prepare_split(bars,start,end,pnf_box_fraction=pnf_box_fraction,candidate_universe=candidate_universe,candidate_family=candidate_family,candidate_spec=candidate_spec)
 return evaluate_prepared_split(prepared,predicate,stop,rr,cost,cost_model=cost_model)

def run_hypothesis_research(csv_path,output_path,*,stop=0.01,rr=2.0,round_trip_cost=0.0,max_components=3,pnf_box_fraction=0.01):
 bars=load_bars(csv_path); splits=chronological_split(len(bars)); validate_splits(splits,len(bars)); composites=generate_composites(max_components=max_components); candidates=list(HYPOTHESES.items())+[(c.name,c.predicate) for c in composites]
 prepared=[prepare_split(bars,split.start,split.end,pnf_box_fraction=pnf_box_fraction) for split in splits]
 result={"schema_version":3,"protocol":{"hypothesis_selection":"pre_registered_fixed_rules_and_bounded_composition","parameter_selection":"none","execution":"shared_reference_execution","oos":"descriptive_only_after_is_validation_gate","max_components":max_components,"max_composites":120,"feature_evaluation":"causal_split_cache_once_per_split","pnf_box_fraction":pnf_box_fraction},"dataset":{"bars":len(bars),"sha256":_sha256(csv_path)},"execution":{"stop_fraction":stop,"reward_multiple":rr,"round_trip_cost":round_trip_cost},"hypotheses":{}}
 for name,predicate in candidates:
  ir=evaluate_prepared_split(prepared[0],predicate,stop,rr,round_trip_cost); vr=evaluate_prepared_split(prepared[1],predicate,stop,rr,round_trip_cost); vm=vr["metrics"]; passed=vm["profit_factor"] is not None and vm["profit_factor"]>=1.0 and vm["total_return"]>=0.0; oos=evaluate_prepared_split(prepared[2],predicate,stop,rr,round_trip_cost) if passed else None; result["hypotheses"][name]={"IS":ir,"VALIDATION":vr,"validation_passed":passed,"OOS":oos}
 Path(output_path).parent.mkdir(parents=True,exist_ok=True); Path(output_path).write_text(json.dumps(result,indent=2),encoding="utf-8"); return result
