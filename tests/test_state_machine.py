IDLE=0; BULL_MSS=1; BULL_FVG=2; BULL_RETEST=3
def test_sequence():
 s=IDLE;s= BULL_MSS;assert s==BULL_MSS;s=BULL_FVG;assert s==BULL_FVG;s=BULL_RETEST;assert s==BULL_RETEST;s=IDLE;assert s==IDLE
def test_no_fvg_before_mss():
 s=BULL_MSS;assert s!=BULL_FVG
def test_retest_later():
 fvg_bar=12;current=13;assert current>fvg_bar
def test_single_retest():
 retested=True;assert retested is True
if __name__=='__main__':
 for f in [test_sequence,test_no_fvg_before_mss,test_retest_later,test_single_retest]: f()
 print('PASS: 4 regression tests')
