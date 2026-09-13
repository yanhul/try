"""Hard compatibility policy for translating external research into BTCUSDT 1H."""
from __future__ import annotations
import re

TARGET_MARKET="BTCUSDT"
TARGET_TIMEFRAME="1H"
PORTABLE_FAMILIES={"momentum_trend","mean_reversion","volatility","smc_ict","fvg_imbalance","wyckoff_vsa_vpa","vwap_volume_profile","regime","seasonality","point_figure","gann_reference"}
NON_PORTABLE_FAMILIES={"china_a_share","cross_sectional","pairs","statistical_arbitrage_pairs","order_book"}
DATA_DEPENDENT_PATTERNS=(r"level[- ]?2",r"order[- ]?book",r"limit order",r"funding rate",r"open interest",r"on[- ]chain",r"options?",r"prediction market",r"pairs? trading",r"cointegration",r"cross[- ]section",r"a[- ]share",r"china stock",r"equities",r"stocks?",r"portfolio")
CRYPTO_MARKETS={"CRYPTO","CRYPTOCURRENCY","DIGITAL_ASSET","BTC","BTCUSDT","BITCOIN"}
CRYPTO_HINTS=("crypto","cryptocurrency","bitcoin","btc","ethereum","eth","solana","sol","doge","digital asset")

def _text(candidate:dict)->str:
 return " ".join(str(candidate.get(k) or "") for k in ("family","market","query","title","description")).lower()

def btc_translation_status(candidate:dict)->tuple[bool,str]:
 family=str(candidate.get("family") or "").strip().lower();market=str(candidate.get("market") or "").strip().upper();text=_text(candidate)
 if family in NON_PORTABLE_FAMILIES:return False,f"non_portable_family:{family}"
 if family not in PORTABLE_FAMILIES:return False,f"unsupported_source_family:{family or 'missing'}"
 for pattern in DATA_DEPENDENT_PATTERNS:
  if re.search(pattern,text):return False,f"requires_unavailable_data:{pattern}"
 if market and market not in CRYPTO_MARKETS:return False,f"single_asset_incompatible:{market}"
 if not market and not any(h in text for h in CRYPTO_HINTS):return True,"portable_price_volume_mechanism"
 return True,"portable_to_btc_ohlcv"

def eligible_survivors(candidates:list[dict])->tuple[list[dict],list[dict]]:
 eligible=[];rejected=[]
 for candidate in candidates:
  ok,reason=btc_translation_status(candidate)
  (eligible if ok else rejected).append({**candidate,"btc_translation_reason":reason})
 return eligible,rejected
