#！ /usr/bin/env python
from scipy.stats import rankdata
import scipy as sp
import numpy as np
import pandas as pd
import datetime as dt
from jqdatasdk import get_index_stocks, get_price, auth
import jqdatasdk as jq
from jqfactor_analyzer import analyze_factor

# 输出配置，看起来方便点
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 100)
pd.set_option('display.width', 1000)

auth("15889961554", "attention3")


class GTJA_191:
    def __init__(self, end_date, index, stocks_pool, count=250, fq='pre'):

        price = get_price(stocks_pool, None, end_date, '1d', [
            'open', 'close', 'low', 'high', 'avg', 'pre_close', 'volume',
            'money'
        ], False, fq, count)
        benchmark_price = get_price(
            index,
            None,
            end_date,
            '1d',
            ['open', 'close', 'low', 'high', 'avg', 'pre_close', 'volume'],
            False,
            fq,
            count,
        )
        self.open_price = price.loc['open', :, :].dropna(axis=1, how='any')
        self.close = price.loc['close', :, :].dropna(axis=1, how='any')
        self.low = price.loc['low', :, :].dropna(axis=1, how='any')
        self.high = price.loc['high', :, :].dropna(axis=1, how='any')
        self.avg_price = price.loc['avg', :, :].dropna(axis=1, how='any')
        self.prev_close = price.loc['pre_close', :, :].dropna(axis=1,
                                                              how='any')
        self.volume = price.loc['volume', :, :].dropna(axis=1, how='any')
        self.amount = price.loc['money', :, :].dropna(axis=1, how='any')
        self.benchmark_open_price = benchmark_price.loc[:, 'open']
        self.benchmark_close_price = benchmark_price.loc[:, 'close']
        #########################################################################

    def func_rank(self, na):
        return rankdata(na)[-1] / rankdata(na).max()

    def func_decaylinear(self, na):
        n = len(na)
        decay_weights = np.arange(1, n + 1, 1)
        decay_weights = decay_weights / decay_weights.sum()

        return (na * decay_weights).sum()

    def func_highday(self, na):
        return len(na) - na.values.argmax()

    def func_lowday(self, na):
        return len(na) - na.values.argmin()

    #############################################################################
    # 衡量成交量和价格背离程度
    def alpha_001(self):
        # 源代码缺少log
        '''
        (-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK(((CLOSE - OPEN) / OPEN)), 6)) 
        刻画成交量变化排名与日内收益率排名的偏离程度，
        表现为成交量变化排名上升，日内收益率排名下降；
        成交量变化排名下降，日内收益率排名上升。
        '''
        # 与joinQuant测试 结果一致
        data1 = np.log(self.volume).diff(periods=1).rank(axis=1, pct=False)
        data2 = ((self.close - self.open_price) / self.open_price).rank(
            axis=1, pct=False)
        alpha = -data1.iloc[-6:, :].corrwith(data2.iloc[-6:, :]).dropna()
        alpha = alpha.dropna()
        return alpha

    def alpha_002(self):
        ##### -1 * delta((((close-low)-(high-close))/((high-low)),1))####
        # 源代码缺少括号
        '''
        刻画多空失衡变动情况，用(CLOSE - LOW) - (HIGH - CLOSE)) / (HIGH - LOW)表示多空力量不平衡度。
        '''
        # 与joinQuant测试 结果一致
        result = -1 * (((self.close - self.low) - (self.high - self.close)) /
                       ((self.high - self.low))).diff()
        m = result.iloc[-1, :].dropna()
        alpha = m[(m < np.inf) & (m > -np.inf)]
        return alpha.dropna()

    ################################################################
    def alpha_003(self):
        #SUM((CLOSE=DELAY(CLOSE,1)?0:CLOSE-(CLOSE>DELAY(CLOSE,1)?MIN(LOW,DELAY(CLOSE,1)):MAX(HIGH,DELAY(CLOSE,1)))),6)
        # 源代码 part3 self.low 应为 self.high
        '''
        
         '''
        delay1 = self.close.shift()
        #condition1 = (self.close == delay1)
        condition2 = (self.close > delay1)
        condition3 = (self.close < delay1)

        part2 = (self.close - np.minimum(
            delay1[condition2], self.low[condition2])).iloc[-6:, :]  #取最近的6位数据
        part3 = (
            self.close -
            np.maximum(delay1[condition3], self.high[condition3])).iloc[-6:, :]

        result = part2.fillna(0) + part3.fillna(0)
        alpha = result.sum()
        return alpha.dropna()

    ########################################################################
    def alpha_004(self):
        '''
        区间突破因子。价格（2日均价）突破布林带（8日）上限取-1，价格突破布林带下限取1，
        价格在布林带区间内时，成交量放大或不变取1，成交量缩小取-1
        '''
        #((((SUM(CLOSE,8)/8)+STD(CLOSE,8))<(SUM(CLOSE,2)/2))?(-11):(((SUM(CLOSE,2)/2)<((SUM(CLOSE,8)/8)-STD(CLOSE,8)))?
        #  1:(((1<(VOLUME/MEAN(VOLUME,20)))||((VOLUME/MEAN(VOLUME,20))==1))?1:(-11))))
        condition1 = (
            (self.close.rolling(8).sum() / 8 + self.close.rolling(8).std()) <
            self.close.rolling(2).sum() / 2)  # 2日均价突破
        condition2 = (
            (self.close.rolling(8).sum() / 8 - self.close.rolling(8).std()) >
            self.close.rolling(2).sum() / 2)  # 2日均价跌破
        condition3 = (1 <= self.volume / self.volume.rolling(20).mean())

        indicator1 = pd.DataFrame(np.ones(self.close.shape),
                                  index=self.close.index,
                                  columns=self.close.columns)  #[condition2]
        indicator2 = -pd.DataFrame(np.ones(self.close.shape),
                                   index=self.close.index,
                                   columns=self.close.columns)  #[condition3]

        #part0=self.close.rolling(8).sum()/8
        part1 = indicator2[condition1].fillna(0)
        part2 = (indicator1[~condition1][condition2]).fillna(0)
        part3 = (indicator1[~condition1][~condition2][condition3]).fillna(0)
        part4 = (indicator2[~condition1][~condition2][~condition3]).fillna(0)

        result = part1 + part2 + part3 + part4
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ################################################################
    def alpha_005(self):
        '''
        短期（3天）内成交量、高点最大偏离程度。
        表现为短周期内（5天）成交量上升，最高价下降；或者成交量下降，最高价上升。
        (-1*TSMAX(CORR(TSRANK(VOLUME,5),TSRANK(HIGH,5),5),3))
        '''

        ts_volume = (self.volume.iloc[-7:, :]).rank(axis=0, pct=False)
        ts_high = (self.high.iloc[-7:, :]).rank(axis=0, pct=False)
        #np.corrcoef(ts_volume.iloc[:, 0], ts_high.iloc[:, 0])
        corr_ts = ts_high.rolling(5).corr(ts_volume)
        #corr_ts=pd.rolling_corr(ts_high,ts_volume,5)
        alpha = corr_ts.max().dropna() * -1
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        return alpha

    ###############################################################
    def alpha_006(self):
        '''
            可能是在刻画当前价格位置和此前位置价格的差距，进行动量交易，具体意义不明。
            (RANK(SIGN(DELTA((((OPEN0.85)+(HIGH0.15))),4)))*-1)
            该值和JQuant 对比，T日 = T-1 日 （）
        '''
        condition1 = ((self.open_price * 0.85 + self.high * 0.15).diff(4) > 1)
        condition2 = ((self.open_price * 0.85 + self.high * 0.15).diff(4) == 1)
        condition3 = ((self.open_price * 0.85 + self.high * 0.15).diff(4) < 1)
        indicator1 = pd.DataFrame(np.ones(self.close.shape),
                                  index=self.close.index,
                                  columns=self.close.columns)
        indicator2 = pd.DataFrame(np.zeros(self.close.shape),
                                  index=self.close.index,
                                  columns=self.close.columns)
        indicator3 = -pd.DataFrame(np.ones(self.close.shape),
                                   index=self.close.index,
                                   columns=self.close.columns)
        part1 = indicator1[condition1].fillna(0)
        part2 = indicator2[condition2].fillna(0)
        part3 = indicator3[condition3].fillna(0)
        result = part1 + part2 + part3
        alpha = (result.rank(axis=1, pct=True)) * -1  #cross section rank
        return alpha.dropna()

    ##################################################################
    def alpha_007(self):
        '''
            部分结果和JQaunt 一直，但总会有一些结果不一致，暂时找不到原因
            ((RANK(MAX((VWAP-CLOSE),3))+RANK(MIN((VWAP-CLOSE),3)))*RANK(DELTA(VOLUME,3)))
        '''
        part1 = (np.maximum(self.avg_price - self.close, 3)).rank(axis=1,
                                                                  pct=True)
        part2 = (np.minimum(self.avg_price - self.close, 3)).rank(axis=1,
                                                                  pct=True)
        # part1=(self.avg_price-self.close).rolling(3).max().rank(axis=1,pct=True)
        # part2=(self.avg_price-self.close).rolling(3).min().rank(axis=1,pct=True)

        part3 = (self.volume.diff(3)).rank(axis=1, pct=True)
        result = (part1 + part2) * part3
        alpha = result.iloc[-1, :]
        return result.dropna()

    ##################################################################
    def alpha_008(self):
        # RANK(DELTA(((((HIGH + LOW) / 2)0.2) + (VWAP * 0.8)), 4) - 1
        '与Joquant 保持一致'
        ' 横截面对比'
        temp = (self.high + self.low) * 0.2 / 2 + self.avg_price * 0.8
        result = -temp.diff(4)
        alpha = result.rank(axis=1, pct=True)
        alpha = alpha.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_009(self):
        '测试结果与JQuant一致'
        '非横截面对比'
        #SMA(((HIGH+LOW)/2-(DELAY(HIGH,1)+DELAY(LOW,1))/2)*(HIGH-LOW)/VOLUME,7，2)
        temp = ((self.high + self.low) * 0.5 -
                (self.high.shift() + self.low.shift()) * 0.5) * (
                    self.high - self.low) / self.volume  #计算close_{i-1}

        result = pd.DataFrame.ewm(temp, alpha=2 / 7).mean()
        #result=pd.ewma(temp,alpha=2/7)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_010(self):
        ### (RANK(MAX(((RET<0)?STD(RET,20):CLOSE)^2),5))
        '''
            部分结果和JQaunt 一直，但总会有一些结果不一致，暂时找不到原因

        '''
        ret = self.close.pct_change()
        condition = (ret < 0)
        part1 = ret.rolling(20).std()[condition].fillna(0)
        # part1=(pd.rolling_std(ret,20)[condition]).fillna(0)
        part2 = (self.close[~condition]).fillna(0)
        result = np.maximum((part1 + part2)**2, 5)
        alpha = result.rank(axis=1, pct=True)
        alpha = alpha.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_011(self):
        ### (SUM(((CLOSE-LOW)-(HIGH-CLOSE))./(HIGH-LOW).*VOLUME,6)
        ##  结果与JQuant一致
        temp = ((self.close - self.low) -
                (self.high - self.close)) / (self.high - self.low)
        result = temp * self.volume
        alpha = result.iloc[-6:, :].sum()
        return alpha.dropna()

    ##################################################################
    def alpha_012(self):
        # (RANK((OPEN-(SUM(VWAP,10)/10))))(-1(RANK(ABS((CLOSE-VWAP)))))
        ## JQUANT上的值和它相反数，按公式来看，应该这里是对的
        # vwap10=pd.rolling_sum(self.avg_price,10)/10
        vwap10 = self.avg_price.rolling(10).sum() / 10
        temp1 = self.open_price - vwap10
        part1 = temp1.rank(axis=1, pct=True)
        temp2 = (self.close - self.avg_price).abs()
        part2 = -temp2.rank(axis=1, pct=True)
        result = part1 * part2
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_013(self):
        # (((HIGH*LOW)^0.5)-VWAP)
        # 与JQuant计算结果有差异，应该是vwap价格的不一致导致的，但是具体并不清楚
        result = ((self.high * self.low)**0.5) - self.avg_price
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_014(self):
        # CLOSE-DELAY(CLOSE,5)
        result = self.close - self.close.shift(5)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_015(self):
        # OPEN/DELAY(CLOSE,1)-1
        result = self.open_price / self.close.shift() - 1
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_016(self):
        # (-1*TSMAX(RANK(CORR(RANK(VOLUME),RANK(VWAP),5)),5))
        # MAX - > maxium
        # TSMAX -> max
        temp1 = self.volume.rank(axis=1, pct=True)
        temp2 = self.avg_price.rank(axis=1, pct=True)
        # part=pd.rolling_corr(temp1,temp2,5)#
        part = temp1.rolling(5).corr(temp2)
        part = part.rank(axis=1, pct=True)
        part = part[(part < np.inf) & (part > -np.inf)]
        result = part.iloc[-5:, :]
        result = result.dropna(axis=1)
        alpha = -result.max()
        return alpha.dropna()

    ##################################################################
    def alpha_017(self):
        # RANK((VWAP-MAX(VWAP,15)))^DELTA(CLOSE,5)
        # temp1=pd.rolling_max(self.avg_price,15)
        temp1 = self.avg_price.rolling(15).max()
        temp2 = (self.avg_price - temp1).dropna()
        part1 = temp2.rank(axis=1, pct=True)
        part2 = self.close.diff(5)
        # 这个指数计算会产生非常大的数值变化，目前没看到实际意义
        # result=part1**part2
        result = part1
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_018(self):
        # CLOSE / DELAY(CLOSE, 5)
        delay5 = self.close.shift(5)
        alpha = self.close / delay5
        alpha = alpha.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_019(self):
        # (CLOSE < DELAY(CLOSE, 5)?(CLOSE-DELAY(CLOSE, 5)) / DELAY(CLOSE, 5): (CLOSE=DELAY(CLOSE, 5)?0: (CLOSE - DELAY(CLOSE, 5)) / CLOSE))
        delay5 = self.close.shift(5)
        condition1 = (self.close < delay5)
        condition3 = (self.close > delay5)
        part1 = (self.close[condition1] -
                 delay5[condition1]) / delay5[condition1]
        part1 = part1.fillna(0)
        part2 = (self.close[condition3] -
                 delay5[condition3]) / self.close[condition3]
        part2 = part2.fillna(0)
        result = part1 + part2
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_020(self):
        # (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*100
        delay6 = self.close.shift(6)
        result = (self.close - delay6) * 100 / delay6
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_021(self):
        # REGBETA(MEAN(CLOSE,6),SEQUENCE(6))
        # A=pd.rolling_mean(self.close,6).iloc[-6:,:]
        A = self.close.rolling(6).mean().iloc[-6:, :]
        # print(A)
        B = np.arange(1, 7)
        temp = A.apply(lambda x: sp.stats.linregress(x, B), axis=0)
        drop_list = [i for i in range(len(temp)) if temp[i].pvalue > 0.05]
        temp.drop(temp.index[drop_list], inplace=True)
        beta_list = [temp[i].slope for i in range(len(temp))]
        # print([temp[i].intercept for i in range(len(temp))])
        alpha = pd.Series(beta_list, index=temp.index)
        return alpha.dropna()

    ##################################################################
    def alpha_022(self):
        #SMEAN(((CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)-DELAY((CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6),3)),12,1)
        # part1=(self.close-pd.rolling_mean(self.close,6))/pd.rolling_mean(self.close,6)
        rolling_mean = self.close.rolling(6).mean()
        part1 = (self.close - rolling_mean) / rolling_mean
        # temp=(self.close-pd.rolling_mean(self.close,6))/pd.rolling_mean(self.close,6)
        temp = (self.close - rolling_mean) / rolling_mean
        part2 = temp.shift(3)
        result = part1 - part2
        # result=pd.ewma(result,alpha=1.0/12)
        result = pd.DataFrame.ewm(result, alpha=1.0 / 12.0).mean()
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_023(self):
        #  SMA((CLOSE > DELAY(CLOSE, 1)?STD(CLOSE:20), 0), 20, 1) / (SMA((CLOSE > DELAY(CLOSE, 1)?STD(CLOSE, 20):0), 20, 1 \
        #   +SMA((CLOSE <= DELAY(CLOSE, 1)?STD(CLOSE, 20): 0), 20, 1))*100

        condition1 = (self.close > self.close.shift())
        # temp1=pd.rolling_std(self.close,20)[condition1]
        temp1 = self.close.rolling(20).std()[condition1]
        temp1 = temp1.fillna(0)
        # temp2=pd.rolling_std(self.close,20)[~condition1]
        temp2 = self.close.rolling(20).std()[~condition1]
        temp2 = temp2.fillna(0)
        # part1=pd.ewma(temp1,alpha=1.0/20)
        part1 = pd.DataFrame.ewm(temp1, alpha=1.0 / 20).mean()
        # part2=pd.ewma(temp2,alpha=1.0/20)
        part2 = pd.DataFrame.ewm(temp2, alpha=1.0 / 20).mean()
        result = part1 * 100 / (part1 + part2)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_024(self):
        #SMA(CLOSE-DELAY(CLOSE,5),5,1)
        delay5 = self.close.shift(5)
        result = self.close - delay5
        # result=pd.ewma(result,alpha=1.0/5)
        result = pd.DataFrame.ewm(result, alpha=1.0 / 5).mean()
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_025(self):
        # ((-1 * RANK((DELTA(CLOSE,7) * (1-RANK(DECAYLINEAR((VOLUME/MEAN(VOLUME,20)),9))))))*(1+RANK(SUM(RET,250))))
        #((-1RANK((DELTA(CLOSE, 7)(1 - RANK(DECAYLINEAR((VOLUME / MEAN(VOLUME, 20)), 9))))))*(1 + RANK(SUM(RET, 250))))
        n = 9
        part1 = (self.close.diff(7))
        part1 = part1.iloc[-1, :]
        # temp=self.volume/pd.rolling_mean(self.volume,20)
        temp = self.volume / (self.volume.rolling(20).mean())
        temp1 = temp.iloc[-9:, :]
        seq = [2 * i / (n * (n + 1))
               for i in range(1, n + 1)]  # sum(1:(n+1)) => n*(n+1)/2
        weight = np.array(seq)
        # print(temp1.sum())
        temp1 = temp1.apply(lambda x: x * weight)
        ret = self.close.iloc[-250:, :].pct_change()
        rank_sum_ret = (ret.sum()).rank(pct=True)
        part2 = 1 - temp1.sum().rank(pct=True)
        part3 = 1 + rank_sum_ret
        alpha = -(part1 * part2).rank(pct=True) * part3
        return alpha.dropna()

    ##################################################################
    def alpha_026(self):
        # ((((SUM(CLOSE, 7) / 7) - CLOSE)) + ((CORR(VWAP, DELAY(CLOSE, 5), 230))))
        part1 = pd.rolling_sum(self.close, 7) / 7 - self.close
        part1 = part1.iloc[-1, :]
        delay5 = self.close.shift(5)
        part2 = pd.rolling_corr(self.avg_price, delay5, 230)
        part2 = part2.iloc[-1, :]
        alpha = part1 + part2
        return alpha.dropna()

    ##################################################################
    def alpha_027(self):
        # WMA((CLOSE-DELAY(CLOSE,3))/DELAY(CLOSE,3)*100+(CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*100,12)
        return 0

    ##################################################################
    def alpha_028(self):
        #3*SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1)-2*SMA(SMA((CLOSE-TSMIN(LOW,9))/(MAX(HIGH,9)-TSMAX(LOW,9))*100,3,1),3,1)
        temp1 = self.close - pd.rolling_min(self.low, 9)
        temp2 = pd.rolling_max(self.high, 9) - pd.rolling_min(self.low, 9)
        part1 = 3 * pd.ewma(temp1 * 100 / temp2, alpha=1.0 / 3)
        temp3 = pd.ewma(temp1 * 100 / temp2, alpha=1.0 / 3)
        part2 = 2 * pd.ewma(temp3, alpha=1.0 / 3)
        result = part1 - part2
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_029(self):
        # (CLOSE-DELAY(CLOSE,6))/DELAY(CLOSE,6)*VOLUME
        delay6 = self.close.shift(6)
        result = (self.close - delay6) * self.volume / delay6
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_030(self):
        #WMA((REGRESI(CLOSE/DELAY(CLOSE)-1,MKT,SMB,HML，60))^2,20)
        return 0

    ##################################################################
    def alpha_031(self):
        # (CLOSE-MEAN(CLOSE,12))/MEAN(CLOSE,12)*100
        result = (self.close - pd.rolling_mean(
            self.close, 12)) * 100 / pd.rolling_mean(self.close, 12)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_032(self):
        # (-1 * SUM(RANK(CORR(RANK(HIGH), RANK(VOLUME), 3)), 3))
        temp1 = self.high.rank(axis=1, pct=True)
        temp2 = self.volume.rank(axis=1, pct=True)
        temp3 = pd.rolling_corr(temp1, temp2, 3)
        temp3 = temp3[(temp3 < np.inf) & (temp3 > -np.inf)].fillna(0)
        result = (temp3.rank(axis=1, pct=True)).iloc[-3:, :]
        alpha = -result.sum()
        return alpha.dropna()

    ##################################################################
    def alpha_033(self):
        # ((((-1 * TSMIN(LOW, 5)) + DELAY(TSMIN(LOW, 5), 5)) * RANK(((SUM(RET, 240) - SUM(RET, 20)) / 220))) * TSRANK(VOLUME, 5))
        ret = self.close.pct_change()
        temp1 = pd.rolling_min(self.low, 5)  #TS_MIN
        part1 = temp1.shift(5) - temp1
        part1 = part1.iloc[-1, :]
        temp2 = (pd.rolling_sum(ret, 240) - pd.rolling_sum(ret, 20)) / 220
        part2 = temp2.rank(axis=1, pct=True)
        part2 = part2.iloc[-1, :]
        temp3 = self.volume.iloc[-5:, :]
        part3 = temp3.rank(axis=0, pct=True)  #TS_RANK
        part3 = part3.iloc[-1, :]
        alpha = part1 + part2 + part3
        return alpha.dropna()

    ##################################################################
    def alpha_034(self):
        # MEAN(CLOSE,12)/CLOSE
        result = pd.rolling_mean(self.close, 12) / self.close
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_035(self):
        """
            这里的OPEN * 0.35应该是CLOSE
             (MIN(RANK(DECAYLINEAR(DELTA(OPEN, 1), 15)), RANK(DECAYLINEAR(CORR((VOLUME), ((OPEN * 0.65) + (OPEN *0.35)), 17),7))) * -1)
            正确的公式:
            MIN(
                RANK(DECAYLINEAR(DELTA(OPEN, 1), 15)),
                RANK(DECAYLINEAR(CORR((VOLUME), ((OPEN * 0.65) + (CLOSE * 0.35)), 17), 7))
            ) * -1
            公式结合了开盘价变动的排名、交易量与价格组合的相关性的排名,二者最小值，结果乘以-1

        """
        # (MIN(RANK(DECAYLINEAR(DELTA(OPEN, 1), 15)), RANK(DECAYLINEAR(CORR((VOLUME), ((OPEN * 0.65) + (OPEN *0.35)), 17),7))) * -1)
        n = 15
        m = 7
        temp1 = self.open_price.diff()
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]
        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.rank(axis=1, pct=True)

        # temp2 = 0.65 * self.open_price + 0.35 * self.open_price
        temp2 = 0.65 * self.open_price + 0.35 * self.close
        temp2 = pd.rolling_corr(temp2, self.volume, 17)
        temp2 = temp2.iloc[-m:, :]
        part2 = temp2.apply(lambda x: x * weight2)
        alpha = np.minimum(part1.iloc[-1, :], -part2.iloc[-1, :])
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_036(self):
        # RANK(SUM(CORR(RANK(VOLUME), RANK(VWAP)), 6), 2)
        temp1 = self.volume.rank(axis=1, pct=True)
        temp2 = self.avg_price.rank(axis=1, pct=True)
        part1 = pd.rolling_corr(temp1, temp2, 6)
        result = pd.rolling_sum(part1, 2)
        result = result.rank(axis=1, pct=True)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_037(self):
        """
            (-1 * (RANK((SUM(OPEN, 5) * SUM(RET, 5)) - DELAY((SUM(OPEN, 5) * SUM(RET, 5)), 10))))
        """

        ret = self.close.pct_change()
        temp = pd.rolling_sum(self.open_price, 5) * pd.rolling_sum(ret, 5)
        part1 = temp.rank(axis=1, pct=True)
        part2 = temp.shift(10)
        result = -(part1 - part2)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_038(self):
        # (((SUM(HIGH, 20) / 20) < HIGH) ? (-1 * DELTA(HIGH, 2)) : 0)
        sum_20 = pd.rolling_sum(self.high, 20) / 20
        delta2 = self.high.diff(2)
        condition = (sum_20 < self.high)
        result = -delta2[condition].fillna(0)
        alpha = result.iloc[-1, :]
        return alpha

    ##################################################################
    def alpha_039(self):
        # ((RANK(DECAYLINEAR(DELTA((CLOSE), 2),8)) - RANK(DECAYLINEAR(CORR(((VWAP * 0.3) + (OPEN * 0.7)), SUM(MEAN(VOLUME,180), 37), 14), 12))) * -1)
        n = 8
        m = 12
        temp1 = self.close.diff(2)
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]

        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.rank(axis=1, pct=True)

        temp2 = 0.3 * self.avg_price + 0.7 * self.open_price
        volume_180 = pd.rolling_mean(self.volume, 180)
        sum_vol = pd.rolling_sum(volume_180, 37)
        temp3 = pd.rolling_corr(temp2, sum_vol, 14)
        temp3 = temp3.iloc[-m:, :]
        part2 = -temp3.apply(lambda x: x * weight2)
        part2.rank(axis=1, pct=True)
        result = part1.iloc[-1, :] - part2.iloc[-1, :]
        alpha = result
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_040(self):
        # SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:0),26)/SUM((CLOSE<=DELAY(CLOSE,1)?VOLUME:0),26)*100
        delay1 = self.close.shift()
        condition = (self.close > delay1)
        vol = self.volume[condition].fillna(0)
        vol_sum = pd.rolling_sum(vol, 26)
        vol1 = self.volume[~condition].fillna(0)
        vol1_sum = pd.rolling_sum(vol1, 26)
        result = 100 * vol_sum / vol1_sum
        result = result.iloc[-1, :]
        alpha = result
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_041(self):
        # (RANK(MAX(DELTA((VWAP), 3), 5))* -1)
        delta_avg = self.avg_price.diff(3)
        part = np.maximum(delta_avg, 5)
        result = -part.rank(axis=1, pct=True)
        alpha = result.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_042(self):
        # ((-1 * RANK(STD(HIGH, 10))) * CORR(HIGH, VOLUME, 10))
        part1 = pd.rolling_corr(self.high, self.volume, 10)
        part2 = pd.rolling_std(self.high, 10)
        part2 = part2.rank(axis=1, pct=True)
        result = -part1 * part2
        alpha = result.iloc[-1, :]
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_043(self):
        # SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),6)
        delay1 = self.close.shift()
        condition1 = (self.close > delay1)
        condition2 = (self.close < delay1)
        temp1 = self.volume[condition1].fillna(0)
        temp2 = -self.volume[condition2].fillna(0)
        result = temp1 + temp2
        result = pd.rolling_sum(result, 6)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_044(self):
        # (TSRANK(DECAYLINEAR(CORR(((LOW )), MEAN(VOLUME,10), 7), 6),4) + TSRANK(DECAYLINEAR(DELTA((VWAP),3), 10), 15))
        part1 = self.open_price * 0.4 + self.close * 0.6
        n = 6
        m = 10
        temp1 = pd.rolling_corr(self.low, pd.rolling_mean(self.volume, 10), 7)
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]
        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.iloc[-4:, ].rank(axis=0, pct=True)

        temp2 = self.avg_price.diff(3)
        temp2 = temp2.iloc[-m:, :]
        part2 = temp2.apply(lambda x: x * weight2)
        part2 = part1.iloc[-5:, ].rank(axis=0, pct=True)
        alpha = part1.iloc[-1, :] + part2.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_045(self):
        # (RANK(DELTA((((CLOSE * 0.6) + (OPEN *0.4))), 1)) * RANK(CORR(VWAP, MEAN(VOLUME,150), 15)))
        temp1 = self.close * 0.6 + self.open_price * 0.4
        part1 = temp1.diff()
        part1 = part1.rank(axis=1, pct=True)
        temp2 = pd.rolling_mean(self.volume, 150)
        part2 = pd.rolling_corr(self.avg_price, temp2, 15)
        part2 = part2.rank(axis=1, pct=True)
        result = part1 * part2
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_046(self):
        # (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/(4*CLOSE)
        part1 = pd.rolling_mean(self.close, 3)
        part2 = pd.rolling_mean(self.close, 6)
        part3 = pd.rolling_mean(self.close, 12)
        part4 = pd.rolling_mean(self.close, 24)
        result = (part1 + part2 + part3 + part4) * 0.25 / self.close
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_047(self):
        # SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,9,1)
        part1 = pd.rolling_max(self.high, 6) - self.close
        part2 = pd.rolling_max(self.high, 6) - pd.rolling_min(self.low, 6)
        result = pd.ewma(100 * part1 / part2, alpha=1.0 / 9)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_048(self):
        # (-1*((RANK(((SIGN((CLOSE - DELAY(CLOSE, 1))) + SIGN((DELAY(CLOSE, 1) - DELAY(CLOSE, 2)))) + SIGN((DELAY(CLOSE, 2) - DELAY(CLOSE, 3)))))) * SUM(VOLUME, 5)) / SUM(VOLUME, 20))
        condition1 = (self.close > self.close.shift())
        condition2 = (self.close.shift() > self.close.shift(2))
        condition3 = (self.close.shift(2) > self.close.shift(3))

        indicator1 = pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[condition1].fillna(0)
        indicator2 = pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[condition2].fillna(0)
        indicator3 = pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[condition3].fillna(0)

        indicator11 = -pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[
                (~condition1) & (self.close != self.close.shift())].fillna(0)
        indicator22 = -pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[(~condition2) & (
                self.close.shift() != self.close.shift(2))].fillna(0)
        indicator33 = -pd.DataFrame(
            np.ones(self.close.shape),
            index=self.close.index,
            columns=self.close.columns)[(~condition3) & (
                self.close.shift(2) != self.close.shift(3))].fillna(0)

        summ = indicator1 + indicator2 + indicator3 + indicator11 + indicator22 + indicator33
        result = -summ * pd.rolling_sum(self.volume, 5) / pd.rolling_sum(
            self.volume, 20)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_049(self):
        """
            SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))
        """
        delay_high = self.high.shift()
        delay_low = self.low.shift()
        condition1 = (self.high + self.low >= delay_high + delay_low)
        condition2 = (self.high + self.low <= delay_high + delay_low)
        part1 = np.maximum(np.abs(self.high - delay_high),
                           np.abs(self.low - delay_low))
        part1 = part1[~condition1]
        part1 = part1.iloc[-12:, :].sum()

        part2 = np.maximum(np.abs(self.high - delay_high),
                           np.abs(self.low - delay_low))
        part2 = part2[~condition2]
        part2 = part2.iloc[-12:, :].sum()
        result = part1 / (part1 + part2)
        alpha = result.dropna()
        return alpha

    ##################################################################
    def alpha_050(self):
        """
            SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))-SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12))
        """
        return 0

    ##################################################################
    def alpha_051(self):
        """
            SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)/(SUM(((HIGH+LOW)<=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)+SUM(((HIGH+LOW)>=(DELAY(HIGH,1)+DELAY(LOW,1))?0:MAX(ABS(HIGH-DELAY(HIGH,1)),ABS(LOW-DELAY(LOW,1)))),12)) 
        """
        return 0

    ##################################################################
    def alpha_052(self):
        """
            SUM(MAX(0,HIGH-DELAY((HIGH+LOW+CLOSE)/3,1)),26)/SUM(MAX(0,DELAY((HIGH+LOW+CLOSE)/3,1)-LOW),26)*100
        """
        delay = ((self.high + self.low + self.close) / 3).shift()
        part1 = (np.maximum(self.high - delay, 0)).iloc[-26:, :]

        part2 = (np.maximum(delay - self.low, 0)).iloc[-26:, :]
        alpha = part1.sum() + part2.sum()
        return alpha

    ##################################################################
    def alpha_053(self):
        """
            COUNT(CLOSE>DELAY(CLOSE,1),12)/12*100
        """
        delay = self.close.shift()
        condition = self.close > delay
        result = self.close[condition].iloc[-12:, :]
        alpha = result.count() * 100 / 12
        return alpha.dropna()

    ##################################################################
    def alpha_054(self):
        """
            (-1 * RANK((STD(ABS(CLOSE - OPEN)) + (CLOSE - OPEN)) + CORR(CLOSE, OPEN,10))) 
        """
        part1 = (self.close - self.open_price).abs()
        part1 = part1.std()
        part2 = (self.close - self.open_price).iloc[-1, :]
        part3 = self.close.iloc[-10:, :].corrwith(
            self.open_price.iloc[-10:, :])
        result = (part1 + part2 + part3).dropna()
        alpha = result.rank(pct=True)
        return alpha.dropna()

    ##################################################################
    def alpha_055(self):
        """
            SUM(16*(CLOSE-DELAY(CLOSE,1)+(CLOSE-OPEN)/2+DELAY(CLOSE,1)-DELAY(OPEN,1))/((ABS(HIGH-DELAY(CLOSE,1))>ABS(LOW-DELAY(CLOSE,1)) & ABS(HIGH-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1))?ABS(HIGH-DELAY(CLOSE,1))+ABS(LOW-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:(ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1)) & ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(CLOSE,1))?ABS(LOW-DELAY(CLOSE,1))+ABS(HIGH-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:ABS(HIGH-DELAY(LOW,1))+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4)))*MAX(ABS(HIGH-DELAY(CLOSE,1)),ABS(LOW-DELAY(CLOSE,1))),20) 
        """
        return 0

    ##################################################################
    def alpha_056(self):
        """
        (RANK((OPEN - TSMIN(OPEN, 12))) < RANK((RANK(CORR(SUM(((HIGH + LOW) / 2), 19), SUM(MEAN(VOLUME,40), 19), 13))^5))) 

        """
        part1 = self.open_price.iloc[-1, :] - self.open_price.iloc[
            -12:, :].min()
        part1 = part1.rank(pct=1)
        temp1 = (self.high + self.low) / 2
        temp1 = pd.rolling_sum(temp1, 19)
        temp2 = pd.rolling_sum(pd.rolling_mean(self.volume, 40), 19)
        part2 = temp1.iloc[-13:, :].corrwith(temp2.iloc[-13:, :])
        part2 = (part2.rank(pct=1))**5
        part2 = part2.rank(pct=1)

        part1[part1 < part2] = 1
        part1 = part1.apply(lambda x: 0 if x < 1 else None)
        alpha = part1.fillna(1)
        return alpha.dropna()

    ##################################################################
    def alpha_057(self):
        """
            SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1) 
        """
        part1 = self.close - pd.rolling_min(self.low, 9)
        part2 = pd.rolling_max(self.high, 9) - pd.rolling_min(self.low, 9)
        result = pd.ewma(100 * part1 / part2, alpha=1.0 / 3)
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_058(self):
        """
            COUNT(CLOSE>DELAY(CLOSE,1),20)/20*100 
        """
        delay = self.close.shift()
        condition = self.close > delay
        result = self.close[condition].iloc[-20:, :]
        alpha = result.count() * 100 / 20
        return alpha.dropna()

    ##################################################################
    def alpha_059(self):
        """
            SUM((CLOSE=DELAY(CLOSE,1)?0:CLOSE-(CLOSE>DELAY(CLOSE,1)?MIN(LOW,DELAY(CLOSE,1)):MAX(HIGH,DELAY(CLOSE,1)))),20) 
        """

        delay = self.close.shift()
        condition1 = (self.close > delay)
        condition2 = (self.close < delay)
        part1 = np.minimum(self.low[condition1], delay[condition1]).fillna(0)
        part2 = np.maximum(self.high[condition2], delay[condition2]).fillna(0)
        part1 = part1.iloc[-20:, :]
        part2 = part2.iloc[-20:, :]
        result = self.close - part1 - part2
        alpha = result.sum()
        return alpha

    ##################################################################
    def alpha_060(self):
        """
            SUM(((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW)*VOLUME,20)
        """
        part1 = (self.close.iloc[-20:, :] - self.low.iloc[-20:, :]) - (
            self.high.iloc[-20:, :] - self.close.iloc[-20:, :])
        part2 = self.high.iloc[-20:, :] - self.low.iloc[-20:, :]
        result = self.volume.iloc[-20:, :] * part1 / part2
        alpha = result.sum()
        return alpha

    ##################################################################
    def alpha_061(self):
        """
            (MAX(RANK(DECAYLINEAR(DELTA(VWAP, 1), 12)),RANK(DECAYLINEAR(RANK(CORR((LOW),MEAN(VOLUME,80), 8)), 17))) * -1)
        """
        n = 12
        m = 17
        temp1 = self.avg_price.diff()
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]

        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.rank(axis=1, pct=True)

        temp2 = self.low
        temp2 = pd.rolling_corr(temp2, pd.rolling_mean(self.volume, 80), 8)
        temp2 = temp2.rank(axis=1, pct=1)
        temp2 = temp2.iloc[-m:, :]
        part2 = temp2.apply(lambda x: x * weight2)
        part2 = -part2.rank(axis=1, pct=1)
        alpha = np.maximum(part1.iloc[-1, :], part2.iloc[-1, :])
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_062(self):
        """
            (-1 * CORR(HIGH, RANK(VOLUME), 5))
        """
        volume_rank = self.volume.rank(axis=1, pct=1)
        result = self.high.iloc[-5:, :].corrwith(volume_rank.iloc[-5:, :])
        alpha = -result
        return alpha.dropna()

    ##################################################################
    def alpha_063(self):
        """
            SMA(MAX(CLOSE-DELAY(CLOSE,1),0),6,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),6,1)*100
        """
        part1 = np.maximum(self.close - self.close.shift(), 0)
        part1 = pd.ewma(part1, alpha=1.0 / 6)
        part2 = (self.close - self.close.shift()).abs()
        part2 = pd.ewma(part2, alpha=1.0 / 6)
        result = part1 * 100 / part2
        alpha = result.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_064(self):
        """
            (MAX(RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 4), 4)),RANK(DECAYLINEAR(MAX(CORR(RANK(CLOSE), RANK(MEAN(VOLUME,60)), 4), 13), 14))) * -1)
        """
        n = 4
        m = 14
        temp1 = pd.rolling_corr(self.avg_price.rank(axis=1, pct=1),
                                self.volume.rank(axis=1, pct=1), 4)
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]
        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.rank(axis=1, pct=True)

        temp2 = self.close.rank(axis=1, pct=1)
        temp2 = pd.rolling_corr(temp2, pd.rolling_mean(self.volume, 60), 4)
        temp2 = np.maximum(temp2, 13)
        temp2 = temp2.iloc[-m:, :]
        part2 = temp2.apply(lambda x: x * weight2)
        part2 = -part2.rank(axis=1, pct=1)
        alpha = np.maximum(part1.iloc[-1, :], part2.iloc[-1, :])
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    ##################################################################
    def alpha_065(self):
        """
            MEAN(CLOSE,6)/CLOSE
        """
        part1 = self.close.iloc[-6:, :]
        alpha = part1.mean() / self.close.iloc[-1, :]
        return alpha.dropna()

    ##################################################################
    def alpha_066(self):
        """
            (CLOSE-MEAN(CLOSE,6))/MEAN(CLOSE,6)*100
        """
        part1 = self.close.iloc[-6:, :]
        alpha = (self.close.iloc[-1, :] - part1.mean()) / part1.mean()
        return alpha

    ##################################################################
    def alpha_067(self):
        """
            SMA(MAX(CLOSE-DELAY(CLOSE,1),0),24,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),24,1)*100 
        """
        temp1 = self.close - self.close.shift()
        part1 = np.maximum(temp1, 0)
        part1 = pd.ewma(part1, alpha=1.0 / 24)
        temp2 = temp1.abs()
        part2 = pd.ewma(temp2, alpha=1.0 / 24)
        result = part1 * 100 / part2
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_068(self):
        """
            SMA(((HIGH+LOW)/2-(DELAY(HIGH,1)+DELAY(LOW,1))/2)*(HIGH-LOW)/VOLUME,15,2)
        """
        part1 = (self.high + self.low) / 2 - self.high.shift()
        part2 = 0.5 * self.low.shift() * (self.high - self.low) / self.volume
        result = (part1 + part2) * 100
        result = pd.ewma(result, alpha=2.0 / 15)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    ##################################################################
    def alpha_069(self):
        """
            DTM = (OPEN<=DELAY(OPEN,1)?0:MAX((HIGH-OPEN),(OPEN-DELAY(OPEN,1)))
            DBM = (OPEN>=DELAY(OPEN,1)?0:MAX((OPEN-LOW),(OPEN-DELAY(OPEN,1))))
            (SUM(DTM, 20) > SUM(DBM, 20) ? (SUM(DTM, 20) - SUM(DBM, 20)) / SUM(DTM, 20) : (SUM(DTM, 20) = SUM(DBM, 20) ? 0 : (SUM(DTM, 20) - SUM(DBM, 20)) / SUM(DBM, 20)))
        """
        return 0

    ##################################################################
    def alpha_070(self):
        #### STD(AMOUNT, 6)
        ##
        alpha = self.amount.iloc[-6:, :].std().dropna()
        return alpha

    #############################################################################
    def alpha_071(self):
        # (CLOSE-MEAN(CLOSE,24))/MEAN(CLOSE,24)*100
        #
        data = self.close - pd.rolling_mean(self.close, 24) / pd.rolling_mean(
            self.close, 24)
        alpha = data.iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_072(self):
        #SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,15,1)
        #
        data1 = pd.rolling_max(self.high, 6) - self.close
        data2 = pd.rolling_max(self.high, 6) - pd.rolling_min(self.low, 6)
        alpha = pd.ewma(data1 / data2 * 100, alpha=1 / 15).iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_073(self):
        """
            ((TSRANK(DECAYLINEAR(DECAYLINEAR(CORR((CLOSE), VOLUME, 10), 16), 4), 5) - RANK(DECAYLINEAR(CORR(VWAP, MEAN(VOLUME,30), 4),3))) * -1) 
        """
        return 0

    #############################################################################
    def alpha_074(self):
        #(RANK(CORR(SUM(((LOW * 0.35) + (VWAP * 0.65)), 20), SUM(MEAN(VOLUME,40), 20), 7)) + RANK(CORR(RANK(VWAP), RANK(VOLUME), 6)))
        #
        data1 = pd.rolling_sum((self.low * 0.35 + self.avg_price * 0.65),
                               window=20)
        data2 = pd.rolling_mean(self.volume, window=40)
        rank1 = pd.rolling_corr(data1, data2, window=7).rank(axis=1, pct=True)
        data3 = self.avg_price.rank(axis=1, pct=True)
        data4 = self.volume.rank(axis=1, pct=True)
        rank2 = pd.rolling_corr(data3, data4, window=6).rank(axis=1, pct=True)
        alpha = (rank1 + rank2).iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_075(self):
        #COUNT(CLOSE>OPEN & BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN,50)/COUNT(BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN,50)
        #
        benchmark = get_price('000001.SH', None, end_date, '1d',
                              ['open', 'close'], False, None, 50)
        condition = benchmark['close'] < benchmark['open']
        data1 = benchmark[condition]
        numbench = len(data1)
        timelist = data1.index.tolist()
        data2 = pd.merge(self.close, data1, left_index=True,
                         right_index=True).drop(['close', 'open'], axis=1)
        data3 = pd.merge(self.open_price,
                         data1,
                         left_index=True,
                         right_index=True).drop(['close', 'open'], axis=1)
        data4 = data2[data2 > data3]
        alpha = 1 - data4.isnull().sum(axis=0) / numbench
        return alpha

    #############################################################################
    def alpha_076(self):
        #STD(ABS((CLOSE/DELAY(CLOSE,1)-1))/VOLUME,20)/MEAN(ABS((CLOSE/DELAY(CLOSE,1)-1))/VOLUME,20)
        #

        data1 = abs((self.close /
                     ((self.prev_close - 1) / self.volume).shift(20))).std()
        data2 = abs((self.close /
                     ((self.prev_close - 1) / self.volume).shift(20))).mean()
        alpha = (data1 / data2).dropna()
        return alpha

    #############################################################################
    def alpha_077(self):
        #MIN(RANK(DECAYLINEAR(((((HIGH + LOW) / 2) + HIGH)  -  (VWAP + HIGH)), 20)), RANK(DECAYLINEAR(CORR(((HIGH + LOW) / 2), MEAN(VOLUME,40), 3), 6)))
        #

        data1 = ((self.high + self.low) / 2 + self.high -
                 (self.avg_price + self.high)).iloc[-20:, :]
        decay_weights = np.arange(1, 20 + 1, 1)[::-1]
        decay_weights = decay_weights / decay_weights.sum()
        rank1 = data1.apply(lambda x: x * decay_weights).rank(axis=1, pct=True)
        data2 = pd.rolling_corr((self.high + self.low) / 2,
                                pd.rolling_mean(self.volume, window=40),
                                window=3).iloc[-6:, :]
        decay_weights2 = np.arange(1, 6 + 1, 1)[::-1]
        decay_weights2 = decay_weights2 / decay_weights2.sum()
        rank2 = data2.apply(lambda x: x * decay_weights2).rank(axis=1,
                                                               pct=True)
        alpha = np.minimum(rank1.iloc[-1], rank2.iloc[-1])
        return alpha

    #############################################################################
    def alpha_078(self):
        #((HIGH+LOW+CLOSE)/3-MA((HIGH+LOW+CLOSE)/3,12))/(0.015*MEAN(ABS(CLOSE-MEAN((HIGH+LOW+CLOSE)/3,12)),12))
        #
        data1 = (self.high + self.low + self.close) / 3 - pd.rolling_mean(
            (self.high + self.low + self.close) / 3, window=12)
        data2 = abs(self.close - pd.rolling_mean(
            (self.high + self.low + self.close) / 3, window=12))
        data3 = pd.rolling_mean(data2, window=12) * 0.015
        alpha = (data1 / data3).iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_079(self):
        #SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100
        #
        data1 = pd.ewma(np.maximum((self.close - self.prev_close), 0),
                        alpha=1 / 12)
        data2 = pd.ewma(abs(self.close - self.prev_close), alpha=1 / 12)
        alpha = (data1 / data2 * 100).iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_080(self):
        #(VOLUME-DELAY(VOLUME,5))/DELAY(VOLUME,5)*100
        #
        alpha = ((self.volume - self.volume.shift(5)) / self.volume.shift(5) *
                 100).iloc[-1].dropna()
        return alpha

    #############################################################################
    def alpha_081(self):
        """
            SMA(VOLUME,21,2)
        """
        result = pd.ewma(self.volume, alpha=2.0 / 21)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    #############################################################################
    def alpha_082(self):
        """
            SMA((TSMAX(HIGH,6)-CLOSE)/(TSMAX(HIGH,6)-TSMIN(LOW,6))*100,20,1)
        """
        part1 = pd.rolling_max(self.high, 6) - self.close
        part2 = pd.rolling_max(self.high, 6) - pd.rolling_min(self.low, 6)
        result = pd.ewma(100 * part1 / part2, alpha=1.0 / 20)
        alpha = result.iloc[-1, :].dropna()
        return alpha

    #############################################################################
    def alpha_083(self):
        """
            (-1 * RANK(COVIANCE(RANK(HIGH), RANK(VOLUME), 5))) 
        """
        part1 = self.high.rank(axis=0, pct=True)
        part1 = part1.iloc[-5:, :]
        part2 = self.volume.rank(axis=0, pct=True)
        part2 = part2.iloc[-5:, :]
        result = part1.corrwith(part2)
        alpha = -result
        return alpha.dropna()

    #############################################################################
    def alpha_084(self):
        """
            SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),20)
        """
        condition1 = (self.close > self.close.shift())
        condition2 = (self.close < self.close.shift())
        part1 = self.volume[condition1].fillna(0)
        part2 = -self.volume[condition2].fillna(0)
        result = part1.iloc[-20:, :] + part2.iloc[-20:, :]
        alpha = result.sum().dropna()
        return alpha

    #############################################################################
    def alpha_085(self):
        """
            (TSRANK((VOLUME / MEAN(VOLUME,20)), 20) * TSRANK((-1 * DELTA(CLOSE, 7)), 8)) 
        """
        temp1 = self.volume.iloc[-20:, :] / self.volume.iloc[-20:, :].mean()
        temp1 = temp1
        part1 = temp1.rank(axis=0, pct=True)
        part1 = part1.iloc[-1, :]

        delta = self.close.diff(7)
        temp2 = -delta.iloc[-8:, :]
        part2 = temp2.rank(axis=0, pct=True).iloc[-1, :]
        part2 = part2
        alpha = part1 * part2
        return alpha.dropna()

    #############################################################################
    def alpha_086(self):
        """
            ((0.25 < (((DELAY(CLOSE, 20) - DELAY(CLOSE, 10)) / 10) - ((DELAY(CLOSE, 10) - CLOSE) / 10))) ? (-1 * 1) : (((((DELAY(CLOSE, 20) - DELAY(CLOSE, 10)) / 10) - ((DELAY(CLOSE, 10) - CLOSE) / 10)) < 0) ? 1 : ((-1 * 1) *(CLOSE - DELAY(CLOSE, 1)))))
        """
        delay10 = self.close.shift(10)
        delay20 = self.close.shift(20)
        indicator1 = pd.DataFrame(-np.ones(self.close.shape),
                                  index=self.close.index,
                                  columns=self.close.columns)
        indicator2 = pd.DataFrame(np.ones(self.close.shape),
                                  index=self.close.index,
                                  columns=self.close.columns)

        temp = (delay20 - delay10) / 10 - (delay10 - self.close) / 10
        condition1 = (temp > 0.25)
        condition2 = (temp < 0)
        temp2 = (self.close - self.close.shift()) * indicator1

        part1 = indicator1[condition1].fillna(0)
        part2 = indicator2[~condition1][condition2].fillna(0)
        part3 = temp2[~condition1][~condition2].fillna(0)
        result = part1 + part2 + part3
        alpha = result.iloc[-1, :].dropna()

        return alpha

    #############################################################################
    def alpha_087(self):
        """
            ((RANK(DECAYLINEAR(DELTA(VWAP, 4), 7)) + TSRANK(DECAYLINEAR(((((LOW * 0.9) + (LOW * 0.1)) - VWAP) / (OPEN - ((HIGH + LOW) / 2))), 11), 7)) * -1) 
        """
        n = 7
        m = 11
        temp1 = self.avg_price.diff(4)
        temp1 = temp1.iloc[-n:, :]
        seq1 = [2 * i / (n * (n + 1)) for i in range(1, n + 1)]
        seq2 = [2 * i / (m * (m + 1)) for i in range(1, m + 1)]

        weight1 = np.array(seq1)
        weight2 = np.array(seq2)
        part1 = temp1.apply(lambda x: x * weight1)
        part1 = part1.rank(axis=1, pct=True)

        temp2 = self.low - self.avg_price
        temp3 = self.open_price - 0.5 * (self.high + self.low)
        temp2 = temp2 / temp3
        temp2 = temp2.iloc[-m:, :]
        part2 = -temp2.apply(lambda x: x * weight2)

        part2 = part2.rank(axis=0, pct=1)
        alpha = part1.iloc[-1, :] + part2.iloc[-1, :]
        alpha = alpha[(alpha < np.inf) & (alpha > -np.inf)]
        alpha = alpha.dropna()
        return alpha

    '''
    ########################################################################
    '''

    def alpha_88(self):
        """
            (CLOSE-DELAY(CLOSE,20))/DELAY(CLOSE,20)*100
        """
        #(close-delay(close,20))/delay(close,20)*100
        ####################
        data1 = self.close.iloc[-21, :]
        alpha = ((self.close.iloc[-1, :] - data1) / data1) * 100
        alpha = alpha.dropna()
        return alpha

    def alpha_89(self):
        """
            2*(SMA(CLOSE,13,2)-SMA(CLOSE,27,2)-SMA(SMA(CLOSE,13,2)-SMA(CLOSE,27,2),10,2))
        """
        #2*(sma(close,13,2)-sma(close,27,2)-sma(sma(close,13,2)-sma(close,27,2),10,2))
        ######################
        data1 = pd.ewma(self.close, span=12, adjust=False)
        data2 = pd.ewma(self.close, span=26, adjust=False)
        data3 = pd.ewma(data1 - data2, span=9, adjust=False)
        alpha = ((data1 - data2 - data3) * 2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_90(self):
        """
            ( RANK(CORR(RANK(VWAP), RANK(VOLUME), 5)) * -1) 
        """
        #(rank(corr(rank(vwap),rank(volume),5))*-1)
        #######################
        data1 = self.avg_price.rank(axis=1, pct=True)
        data2 = self.volume.rank(axis=1, pct=True)
        corr = data1.iloc[-5:, :].corrwith(data2.iloc[-5:, :])
        rank1 = corr.rank(pct=True)
        alpha = rank1 * -1
        alpha = alpha.dropna()
        return alpha

    def alpha_91(self):
        """
            ((RANK((CLOSE - MAX(CLOSE, 5)))*RANK(CORR((MEAN(VOLUME,40)), LOW, 5))) * -1)
        """
        #((rank((close-max(close,5)))*rank(corr((mean(volume,40)),low,5)))*-1)
        #################
        data1 = self.close
        cond = data1 > 5
        data1[~cond] = 5
        rank1 = ((self.close - data1).rank(axis=1, pct=True)).iloc[-1, :]
        mean = pd.rolling_mean(self.volume, window=40)
        corr = mean.iloc[-5:, :].corrwith(self.low.iloc[-5:, :])
        rank2 = corr.rank(pct=True)
        alpha = rank1 * rank2 * (-1)
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_92(self):
        """
            (MAX(RANK(DECAYLINEAR(DELTA(((CLOSE * 0.35) + (VWAP *0.65)), 2), 3)), TSRANK(DECAYLINEAR(ABS(CORR((MEAN(VOLUME,180)), CLOSE, 13)), 5), 15)) * -1)
        """
        # (MAX(RANK(DECAYLINEAR(DELTA(((CLOSE*0.35)+(VWAP*0.65)),2),3)),TSRANK(DECAYLINEAR(ABS(CORR((MEAN(VOLUME,180)),CLOSE,13)),5),15))*-1) #
        delta = (self.close * 0.35 + self.avg_price * 0.65) - (
            self.close * 0.35 + self.avg_price * 0.65).shift(2)
        rank1 = (pd.rolling_apply(delta, 3,
                                  self.func_decaylinear)).rank(axis=1,
                                                               pct=True)
        rank2 = pd.rolling_apply(
            pd.rolling_apply(
                self.volume.rolling(180).mean().rolling(13).corr(
                    self.close).abs(), 5, self.func_decaylinear), 15,
            self.func_rank)
        cond_max = rank1 > rank2
        rank2[cond_max] = rank1[cond_max]
        alpha = (-rank2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_93(self):
        """
            SUM((OPEN>=DELAY(OPEN,1)?0:MAX((OPEN-LOW),(OPEN-DELAY(OPEN,1)))),20) 
        """
        # SUM((OPEN>=DELAY(OPEN,1)?0:MAX((OPEN-LOW),(OPEN-DELAY(OPEN,1)))),20) #
        cond = self.open_price >= self.open_price.shift()
        data1 = self.open_price - self.low
        data2 = self.open_price - self.open_price.shift()
        cond_max = data1 > data2
        data2[cond_max] = data1[cond_max]
        data2[cond] = 0
        alpha = data2.iloc[-20:, :].sum()
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_94(self):
        """
            SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),30) 
        """
        # SUM((CLOSE>DELAY(CLOSE,1)?VOLUME:(CLOSE<DELAY(CLOSE,1)?-VOLUME:0)),30) #
        cond1 = self.close > self.prev_close
        cond2 = self.close < self.prev_close
        value = -self.volume
        value[~cond2] = 0
        value[cond1] = self.volume[cond1]
        alpha = value.iloc[-30:, :].sum()
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_95(self):
        """
            STD(AMOUNT,20) 
        """
        # STD(AMOUNT,20) #
        alpha = self.amount.iloc[-20:, :].std()
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_96(self):
        """
            SMA(SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1),3,1)
        """
        # SMA(SMA((CLOSE-TSMIN(LOW,9))/(TSMAX(HIGH,9)-TSMIN(LOW,9))*100,3,1),3,1) #
        sma1 = pd.ewma(
            100 * (self.close - self.low.rolling(9).min()) /
            (self.high.rolling(9).max() - self.low.rolling(9).min()),
            span=5,
            adjust=False)
        alpha = pd.ewma(sma1, span=5, adjust=False).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_97(self):
        """
            STD(VOLUME,10)
        """
        # STD(VOLUME,10) #
        alpha = self.volume.iloc[-10:, :].std()
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_98(self):
        """
            ((((DELTA((SUM(CLOSE, 100) / 100), 100) / DELAY(CLOSE, 100)) < 0.05) || ((DELTA((SUM(CLOSE, 100) / 100), 100) / DELAY(CLOSE, 100)) == 0.05)) ? (-1 * (CLOSE - TSMIN(CLOSE, 100))) : (-1 * DELTA(CLOSE, 3))) 
        """
        # ((((DELTA((SUM(CLOSE,100)/100),100)/DELAY(CLOSE,100))<0.05)||((DELTA((SUM(CLOSE,100)/100),100)/DELAY(CLOSE,100))==0.05))?(-1*(CLOSE-TSMIN(CLOSE,100))):(-1*DELTA(CLOSE,3))) #
        sum_close = self.close.rolling(100).sum()
        cond = (sum_close / 100 -
                (sum_close / 100).shift(100)) / self.close.shift(100) <= 0.05
        left_value = -(self.close - self.close.rolling(100).min())
        right_value = -(self.close - self.close.shift(3))
        right_value[cond] = left_value[cond]
        alpha = right_value.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_99(self):
        """
            (-1 * RANK(COVIANCE(RANK(CLOSE), RANK(VOLUME), 5)))
        """
        # (-1 * RANK(COVIANCE(RANK(CLOSE), RANK(VOLUME), 5))) #
        alpha = (-pd.rolling_cov(self.close.rank(axis=1, pct=True),
                                 self.volume.rank(axis=1, pct=True),
                                 window=5).rank(axis=1, pct=True)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_100(self):
        """
            STD(VOLUME,20)
        """
        # STD(VOLUME,20) #
        alpha = self.volume.iloc[-20:, :].std()
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_101(self):
        """
            ((RANK(CORR(CLOSE, SUM(MEAN(VOLUME,30), 37), 15)) < RANK(CORR(RANK(((HIGH * 0.1) + (VWAP * 0.9))), RANK(VOLUME), 11))) * -1)
        """
        # ((RANK(CORR(CLOSE,SUM(MEAN(VOLUME,30),37),15))<RANK(CORR(RANK(((HIGH*0.1)+(VWAP*0.9))),RANK(VOLUME),11)))*-1) #
        rank1 = (self.close.rolling(window=15).corr((self.volume.rolling(
            window=30).mean()).rolling(window=37).sum())).rank(axis=1,
                                                               pct=True)
        rank2 = (self.high * 0.1 + self.avg_price * 0.9).rank(axis=1, pct=True)
        rank3 = self.volume.rank(axis=1, pct=True)
        rank4 = (rank2.rolling(window=11).corr(rank3)).rank(axis=1, pct=True)
        alpha = -(rank1 < rank4)
        alpha = alpha.iloc[-1, :].dropna()
        return alpha

    #
    def alpha_102(self):
        """
            SMA(MAX(VOLUME-DELAY(VOLUME,1),0),6,1)/SMA(ABS(VOLUME-DELAY(VOLUME,1)),6,1)*100 
        """
        # SMA(MAX(VOLUME-DELAY(VOLUME,1),0),6,1)/SMA(ABS(VOLUME-DELAY(VOLUME,1)),6,1)*100 #
        max_cond = (self.volume - self.volume.shift()) > 0
        max_data = self.volume - self.volume.shift()
        max_data[~max_cond] = 0
        sma1 = pd.ewma(max_data, span=11, adjust=False)
        sma2 = pd.ewma((self.volume - self.volume.shift()).abs(),
                       span=11,
                       adjust=False)
        alpha = (sma1 / sma2 * 100).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_103(self):
        """
            ((20-LOWDAY(LOW,20))/20)*100
        """
        ##### ((20-LOWDAY(LOW,20))/20)*100
        ##
        alpha = (20 -
                 self.low.iloc[-20:, :].apply(self.func_lowday)) / 20 * 100
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_104(self):
        """
            (-1 * (DELTA(CORR(HIGH, VOLUME, 5), 5) * RANK(STD(CLOSE, 20))))
        """
        # (-1*(DELTA(CORR(HIGH,VOLUME,5),5)*RANK(STD(CLOSE,20)))) #
        corr = self.high.rolling(window=5).corr(self.volume)
        alpha = (-(corr - corr.shift(5)) *
                 ((self.close.rolling(window=20).std()).rank(
                     axis=1, pct=True))).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_105(self):
        """
            (-1 * CORR(RANK(OPEN), RANK(VOLUME), 10))
        """
        # (-1*CORR(RANK(OPEN),RANK(VOLUME),10)) #
        alpha = -(
            (self.open_price.rank(axis=1, pct=True)).iloc[-10:, :]).corrwith(
                self.volume.iloc[-10:, :].rank(axis=1, pct=True))
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_106(self):
        """
            CLOSE-DELAY(CLOSE,20)
        """
        # CLOSE-DELAY(CLOSE,20) #
        alpha = (self.close - self.close.shift(20)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_107(self):
        """
            (((-1 * RANK((OPEN - DELAY(HIGH, 1)))) * RANK((OPEN - DELAY(CLOSE, 1)))) * RANK((OPEN - DELAY(LOW, 1))))
        """
        # (((-1*RANK((OPEN-DELAY(HIGH,1))))*RANK((OPEN-DELAY(CLOSE,1))))*RANK((OPEN-DELAY(LOW,1)))) #
        rank1 = -(self.open_price - self.high.shift()).rank(axis=1, pct=True)
        rank2 = (self.open_price - self.close.shift()).rank(axis=1, pct=True)
        rank3 = (self.open_price - self.low.shift()).rank(axis=1, pct=True)
        alpha = (rank1 * rank2 * rank3).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_108(self):
        """
           ((RANK((HIGH - MIN(HIGH, 2)))^RANK(CORR((VWAP), (MEAN(VOLUME,120)), 6))) * -1) 
        """
        # ((RANK((HIGH-MIN(HIGH,2)))^RANK(CORR((VWAP),(MEAN(VOLUME,120)),6)))*-1) #
        min_cond = self.high > 2
        data = self.high
        data[min_cond] = 2
        rank1 = (self.high - data).rank(axis=1, pct=True)
        rank2 = (self.avg_price.rolling(window=6).corr(
            self.volume.rolling(window=120).mean())).rank(axis=1, pct=True)
        alpha = (-rank1**rank2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_109(self):
        """
            SMA(HIGH-LOW,10,2)/SMA(SMA(HIGH-LOW,10,2),10,2) 
        """
        # SMA(HIGH-LOW,10,2)/SMA(SMA(HIGH-LOW,10,2),10,2)#
        data = self.high - self.low
        sma1 = pd.ewma(data, span=9, adjust=False)
        sma2 = pd.ewma(sma1, span=9, adjust=False)
        alpha = (sma1 / sma2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_110(self):
        """
            SUM(MAX(0,HIGH-DELAY(CLOSE,1)),20)/SUM(MAX(0,DELAY(CLOSE,1)-LOW),20)*100 
        """
        # SUM(MAX(0,HIGH-DELAY(CLOSE,1)),20)/SUM(MAX(0,DELAY(CLOSE,1)-LOW),20)*100 #
        data1 = self.high - self.prev_close
        data2 = self.prev_close - self.low
        max_cond1 = data1 < 0
        max_cond2 = data2 < 0
        data1[max_cond1] = 0
        data2[max_cond2] = 0
        sum1 = data1.rolling(window=20).sum()
        sum2 = data2.rolling(window=20).sum()
        alpha = sum1 / sum2 * 100
        alpha = alpha.dropna()
        return alpha.iloc[-1, :]

    def alpha_111(self):
        """
            SMA(VOL*((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW),11,2)-SMA(VOL*((CLOSE-LOW)-(HIGH-CLOSE))/(HIGH-LOW),4,2) 
        """
        #sma(vol*((close-low)-(high-close))/(high-low),11,2)-sma(vol*((close-low)-(high-close))/(high-low),4,2)
        ######################
        data1 = self.volume * (
            (self.close - self.low) -
            (self.high - self.close)) / (self.high - self.low)
        x = pd.ewma(data1, span=10)
        y = pd.ewma(data1, span=3)
        alpha = (x - y).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_112(self):
        """
            (SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)-SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))/(SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)+SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))*100 
        """
        # (SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)-SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))/(SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)+SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12))*100 #
        cond1 = self.close > self.prev_close
        cond2 = self.close < self.prev_close
        data1 = self.close - self.prev_close
        data2 = self.close - self.prev_close
        data1[~cond1] = 0
        data2[~cond2] = 0
        data2 = data2.abs()
        sum1 = data1.rolling(window=12).sum()
        sum2 = data2.rolling(window=12).sum()
        alpha = ((sum1 - sum2) / (sum1 + sum2) * 100).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_113(self):
        """
            (-1 * ((RANK((SUM(DELAY(CLOSE, 5), 20) / 20)) * CORR(CLOSE, VOLUME, 2)) * RANK(CORR(SUM(CLOSE, 5), SUM(CLOSE, 20), 2)))) 

        """
        #(-1*((rank((sum(delay(close,5),20)/20))*corr(close,volume,2))*rank(corr(sum(close,5),sum(close,20),2))))
        #####################
        data1 = self.close.iloc[:-5, :]
        rank1 = (pd.rolling_sum(data1, window=20) / 20).rank(axis=1, pct=True)
        corr1 = self.close.iloc[-2:, :].corrwith(self.volume.iloc[-2:, :])
        data2 = pd.rolling_sum(self.close, window=5)
        data3 = pd.rolling_sum(self.close, window=20)
        corr2 = data2.iloc[-2:, :].corrwith(data3.iloc[-2:, :])
        rank2 = corr2.rank(axis=0, pct=True)
        alpha = (-1 * rank1 * corr1 * rank2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_114(self):
        """
            ((RANK(DELAY(((HIGH - LOW) / (SUM(CLOSE, 5) / 5)), 2)) * RANK(RANK(VOLUME))) / (((HIGH - LOW) /(SUM(CLOSE, 5) / 5)) / (VWAP - CLOSE))) 
        """
        #((rank(delay(((high-low)/(sum(close,5)/5)),2))*rank(rank(volume)))/(((high-low)/(sum(close,5)/5))/(vwap-close)))
        #####################
        data1 = (self.high -
                 self.low) / (pd.rolling_sum(self.close, window=5) / 5)
        rank1 = (data1.iloc[-2, :]).rank(axis=0, pct=True)
        rank2 = ((self.volume.rank(axis=1,
                                   pct=True)).rank(axis=1,
                                                   pct=True)).iloc[-1, :]
        data2 = (((self.high - self.low) /
                  (pd.rolling_sum(self.close, window=5) / 5)) /
                 (self.avg_price - self.close)).iloc[-1, :]
        alpha = (rank1 * rank2) / data2
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_115(self):
        """
            (RANK(CORR(((HIGH * 0.9) + (CLOSE * 0.1)), MEAN(VOLUME,30), 10))^RANK(CORR(TSRANK(((HIGH + LOW) / 2), 4), TSRANK(VOLUME, 10), 7)))

        """
        # RANK(CORR(((HIGH*0.9)+(CLOSE*0.1)),MEAN(VOLUME,30),10))^RANK(CORR(TSRANK(((HIGH+LOW)/2),4),TSRANK(VOLUME,10),7)) #
        data1 = (self.high * 0.9 + self.close * 0.1)
        data2 = self.volume.rolling(window=30).mean()
        rank1 = (data1.iloc[-10:, :].corrwith(
            data2.iloc[-10:, :])).rank(pct=True)
        tsrank1 = pd.rolling_apply((self.high + self.low) / 2, 4,
                                   self.func_rank)
        tsrank2 = pd.rolling_apply(self.volume, 10, self.func_rank)
        rank2 = tsrank1.iloc[-7:, :].corrwith(
            tsrank2.iloc[-7:, :]).rank(pct=True)
        alpha = rank1**rank2
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_116(self):
        """
            REGBETA(CLOSE,SEQUENCE,20)
        """
        # REGBETA(CLOSE,SEQUENCE,20) #
        sequence = pd.Series(range(1, 21),
                             index=self.close.iloc[-20:, ].index)  # 1~20
        corr = self.close.iloc[-20:, :].corrwith(sequence)
        alpha = corr
        alpha = alpha.dropna()
        return alpha

    def alpha_117(self):
        """
            ((TSRANK(VOLUME, 32) * (1 - TSRANK(((CLOSE + HIGH) - LOW), 16))) * (1 - TSRANK(RET, 32)))
        """
        #######((tsrank(volume,32)*(1-tsrank(((close+high)-low),16)))*(1-tsrank(ret,32)))
        ####################
        data1 = (self.close + self.high - self.low).iloc[-16:, :]
        data2 = 1 - data1.rank(axis=0, pct=True)
        data3 = (self.volume.iloc[-32:, :]).rank(axis=0, pct=True)
        ret = (self.close / self.close.shift() - 1).iloc[-32:, :]
        data4 = 1 - ret.rank(axis=0, pct=True)
        alpha = (data2.iloc[-1, :]) * (data3.iloc[-1, :]) * (data4.iloc[-1, :])
        alpha = alpha.dropna()
        return alpha

    def alpha_118(self):
        """
            SUM(HIGH-OPEN,20)/SUM(OPEN-LOW,20)*100
        """
        ######sum(high-open,20)/sum((open-low),20)*100
        ###################
        data1 = self.high - self.open_price
        data2 = self.open_price - self.low
        data3 = pd.rolling_sum(data1, window=20)
        data4 = pd.rolling_sum(data2, window=20)
        alpha = ((data3 / data4) * 100).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_119(self):
        """
            (RANK(DECAYLINEAR(CORR(VWAP, SUM(MEAN(VOLUME,5), 26), 5), 7)) -RANK(DECAYLINEAR(TSRANK(MIN(CORR(RANK(OPEN), RANK(MEAN(VOLUME,15)), 21), 9), 7), 8)))
        """
        # (RANK(DECAYLINEAR(CORR(VWAP,SUM(MEAN(VOLUME,5),26),5),7))-RANK(DECAYLINEAR(TSRANK(MIN(CORR(RANK(OPEN),RANK(MEAN(VOLUME,15)),21),9),7),8)))
        sum1 = (self.volume.rolling(window=5).mean()).rolling(window=26).sum()
        corr1 = self.avg_price.rolling(window=5).corr(sum1)
        rank1 = pd.rolling_apply(corr1, 7,
                                 self.func_decaylinear).rank(axis=1, pct=True)
        rank2 = self.open_price.rank(axis=1, pct=True)
        rank3 = (self.volume.rolling(window=15).mean()).rank(axis=1, pct=True)
        rank4 = pd.rolling_apply(
            rank2.rolling(window=21).corr(rank3).rolling(window=9).min(), 7,
            self.func_rank)
        rank5 = pd.rolling_apply(rank4, 8,
                                 self.func_decaylinear).rank(axis=1, pct=True)
        alpha = (rank1 - rank5).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_120(self):
        """
            (RANK((VWAP - CLOSE)) / RANK((VWAP + CLOSE)))
        """
        ###############(rank(vwap-close))/(rank(vwap+close))
        ###################
        data1 = (self.avg_price - self.close).rank(axis=1, pct=True)
        data2 = (self.avg_price + self.close).rank(axis=1, pct=True)
        alpha = (data1 / data2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_121(self):
        """
            ((RANK((VWAP - MIN(VWAP, 12)))^TSRANK(CORR(TSRANK(VWAP, 20), TSRANK(MEAN(VOLUME,60), 2), 18), 3)) * -1) 
        """
        return 0

    def alpha_122(self):
        """
            (SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2)-DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1))/DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1) 
        """
        ##### (SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2) - DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1))
        ##### / DELAY(SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2),1)
        ##
        log_close = np.log(self.close)
        data = pd.ewma(pd.ewma(pd.ewma(log_close, span=12, adjust=False),
                               span=12,
                               adjust=False),
                       span=12,
                       adjust=False)
        alpha = (data.iloc[-1, :] / data.iloc[-2, :]) - 1
        alpha = alpha.dropna()
        return alpha

    def alpha_123(self):
        """
            ((RANK(CORR(SUM(((HIGH + LOW) / 2), 20), SUM(MEAN(VOLUME,60), 20), 9)) < RANK(CORR(LOW, VOLUME, 6))) * -1) 
        """
        #####((RANK(CORR(SUM(((HIGH+LOW)/2), 20), SUM(MEAN(VOLUME, 60), 20), 9)) < RANK(CORR(LOW, VOLUME, 6))) * -1)
        ##
        data1 = ((self.high + self.low) / 2).rolling(20).sum()
        data2 = self.volume.rolling(60).mean().rolling(20).sum()
        rank1 = data1.iloc[-9:, :].corrwith(data2.iloc[-9:, :]).dropna().rank(
            axis=0, pct=True)
        rank2 = self.low.iloc[-6:, :].corrwith(
            self.volume.iloc[-6:, :]).dropna().rank(axis=0, pct=True)
        rank1 = rank1[rank1.index.isin(rank2.index)]
        rank2 = rank2[rank2.index.isin(rank1.index)]
        alpha = (rank1 < rank2) * (-1)
        alpha = alpha.dropna()
        return alpha

    def alpha_124(self):
        """
            (CLOSE - VWAP) / DECAYLINEAR(RANK(TSMAX(CLOSE, 30)),2)
        """
        ##### (CLOSE - VWAP) / DECAYLINEAR(RANK(TSMAX(CLOSE, 30)),2)
        ##
        data1 = self.close.rolling(30).max().rank(axis=1, pct=True)
        alpha = (self.close.iloc[-1, :] - self.avg_price.iloc[-1, :]) / (
            2. / 3 * data1.iloc[-2, :] + 1. / 3 * data1.iloc[-1, :])
        alpha = alpha.dropna()
        return alpha

    def alpha_125(self):
        """
            (RANK(DECAYLINEAR(CORR((VWAP), MEAN(VOLUME,80),17), 20)) / RANK(DECAYLINEAR(DELTA(((CLOSE * 0.5) + (VWAP * 0.5)), 3), 16)))
        """
        ##### (RANK(DECAYLINEAR(CORR((VWAP), MEAN(VOLUME, 80), 17), 20)) / RANK(DECAYLINEAR(DELTA((CLOSE * 0.5 + VWAP * 0.5), 3), 16)))
        ##
        data1 = pd.rolling_corr(self.avg_price,
                                self.volume.rolling(80).mean(),
                                window=17)
        decay_weights = np.arange(1, 21, 1)[::-1]  # 倒序数组
        decay_weights = decay_weights / decay_weights.sum()
        rank1 = data1.iloc[-20:, :].mul(decay_weights,
                                        axis=0).sum().rank(axis=0, pct=True)

        data2 = (self.close * 0.5 + self.avg_price * 0.5).diff(3)
        decay_weights = np.arange(1, 17, 1)[::-1]  # 倒序数组
        decay_weights = decay_weights / decay_weights.sum()
        rank2 = data2.iloc[-16:, :].mul(decay_weights,
                                        axis=0).sum().rank(axis=0, pct=True)

        alpha = rank1 / rank2
        alpha = alpha.dropna()
        return alpha

    def alpha_126(self):
        """
             (CLOSE+HIGH+LOW)/3
        """
        #### (CLOSE + HIGH + LOW) / 3
        ##
        alpha = (self.close.iloc[-1, :] + self.high.iloc[-1, :] +
                 self.low.iloc[-1, :]) / 3
        alpha = alpha.dropna()
        return alpha

    def alpha_127(self):
        """
            (MEAN((100*(CLOSE-MAX(CLOSE,12))/(MAX(CLOSE,12)))^2))^(1/2)
        """
        return

    def alpha_128(self):
        """
            100-(100/(1+SUM(((HIGH+LOW+CLOSE)/3>DELAY((HIGH+LOW+CLOSE)/3,1)?(HIGH+LOW+CLOSE)/3*VOLUME:0),14)/SUM(((HIGH+LOW+CLOSE)/3<DELAY((HIGH+LOW+CLOSE)/3,1)?(HIGH+LOW+CLOSE)/3*VOLUME:0),14))) 
        """

        return

    def alpha_129(self):
        """
            SUM((CLOSE-DELAY(CLOSE,1)<0?ABS(CLOSE-DELAY(CLOSE,1)):0),12) 
        """
        #### SUM((CLOSE - DELAY(CLOSE, 1) < 0 ? ABS(CLOSE - DELAY(CLOSE, 1)):0), 12)
        ##
        data = self.close.diff(1)
        data[data >= 0] = 0
        data = abs(data)
        alpha = data.iloc[-12:, :].sum()
        alpha = alpha.dropna()
        return alpha

    def alpha_130(self):
        """
            (RANK(DECAYLINEAR(CORR(((HIGH + LOW) / 2), MEAN(VOLUME,40), 9), 10)) / RANK(DECAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 7),3)))
        """
        #### alpha_130
        #### (RANK(DELCAYLINEAR(CORR(((HIGH + LOW) / 2), MEAN(VOLUME, 40), 9), 10)) / RANK(DELCAYLINEAR(CORR(RANK(VWAP), RANK(VOLUME), 7), 3)))
        ##
        data1 = (self.high + self.low) / 2
        data2 = self.volume.rolling(40).mean()
        data3 = pd.rolling_corr(data1, data2, window=9)
        decay_weights = np.arange(1, 11, 1)[::-1]  # 倒序数组
        decay_weights = decay_weights / decay_weights.sum()
        rank1 = data3.iloc[-10:, :].mul(decay_weights,
                                        axis=0).sum().rank(axis=0, pct=True)

        data1 = self.avg_price.rank(axis=1, pct=True)
        data2 = self.volume.rank(axis=1, pct=True)
        data3 = pd.rolling_corr(data1, data2, window=7)
        decay_weights = np.arange(1, 4, 1)[::-1]  # 倒序数组
        decay_weights = decay_weights / decay_weights.sum()
        rank2 = data3.iloc[-3:, :].mul(decay_weights,
                                       axis=0).sum().rank(axis=0, pct=True)

        alpha = (rank1 / rank2).dropna()
        return alpha

    def alpha_131(self):
        """
            (RANK(DELAT(VWAP, 1))^TSRANK(CORR(CLOSE,MEAN(VOLUME,50), 18), 18))
        """
        return 0

    def alpha_132(self):
        """
            MEAN(AMOUNT,20)
        """
        #### MEAN(AMOUNT, 20)
        ##
        alpha = self.amount.iloc[-20:, :].mean()
        alpha = alpha.dropna()
        return alpha

    def alpha_133(self):
        """
            ((20-HIGHDAY(HIGH,20))/20)*100-((20-LOWDAY(LOW,20))/20)*100
        """
        #### alpha_133
        #### ((20 - HIGHDAY(HIGH, 20)) / 20)*100 - ((20 - LOWDAY(LOW, 20)) / 20)*100
        ##

        alpha = (20 - self.high.iloc[-20:,:].apply(self.func_highday))/20*100 \
                 - (20 - self.low.iloc[-20:,:].apply(self.func_lowday))/20*100
        alpha = alpha.dropna()
        return alpha

    def alpha_134(self):
        """
            (CLOSE-DELAY(CLOSE,12))/DELAY(CLOSE,12)*VOLUME 
        """
        #### (CLOSE - DELAY(CLOSE, 12)) / DELAY(CLOSE, 12) * VOLUME
        ##
        alpha = ((self.close.iloc[-1, :] / self.close.iloc[-13, :] - 1) *
                 self.volume.iloc[-1, :])
        alpha = alpha.dropna()
        return alpha

    def alpha_135(self):
        """
           SMA(DELAY(CLOSE/DELAY(CLOSE,20),1),20,1) 
        """

        #### SMA(DELAY(CLOSE / DELAY(CLOSE, 20), 1), 20, 1)
        ##
        def rolling_div(na):
            return na[-1] / na[-21]

        data1 = self.close.rolling(21).apply(rolling_div).shift(periods=1)
        alpha = pd.ewma(data1, com=19, adjust=False).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_136(self):
        """
            ((-1 * RANK(DELTA(RET, 3))) * CORR(OPEN, VOLUME, 10))
        """
        #### ((-1 * RANK(DELTA(RET, 3))) * CORR(OPEN, VOLUME, 10))
        ##
        data1 = -(self.close / self.prev_close - 1).diff(3).rank(axis=1,
                                                                 pct=True)
        data2 = self.open_price.iloc[-10:, :].corrwith(
            self.volume.iloc[-10:, :])
        alpha = (data1.iloc[-1, :] * data2).dropna()

        return alpha

    def alpha_137(self):
        """
            16*(CLOSE-DELAY(CLOSE,1)+(CLOSE-OPEN)/2+DELAY(CLOSE,1)-DELAY(OPEN,1))/((ABS(HIGH-DELAY(CLOSE,1))>ABS(LOW-DELAY(CLOSE,1)) & ABS(HIGH-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1))?ABS(HIGH-DELAY(CLOSE,1))+ABS(LOW-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:(ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(LOW,1)) & ABS(LOW-DELAY(CLOSE,1))>ABS(HIGH-DELAY(CLOSE,1))?ABS(LOW-DELAY(CLOSE,1))+ABS(HIGH-DELAY(CLOSE,1))/2+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4:ABS(HIGH-DELAY(LOW,1))+ABS(DELAY(CLOSE,1)-DELAY(OPEN,1))/4)))*MAX(ABS(HIGH-DELAY(CLOSE,1)),ABS(LOW-DELAY(CLOSE,1))) 
        """
        return

    def alpha_138(self):
        """
            ((RANK(DECAYLINEAR(DELTA((((LOW * 0.7) + (VWAP *0.3))), 3), 20)) - 
            TSRANK(DECAYLINEAR(TSRANK(CORR(TSRANK(LOW, 8), TSRANK(MEAN(VOLUME,60), 17), 5), 19), 16), 7)) * -1)
        """
        #### ((RANK(DECAYLINEAR(DELTA((((LOW * 0.7) + (VWAP * 0.3))), 3), 20)) - TSRANK(DECAYLINEAR(TSRANK(CORR(TSRANK(LOW, 8), TSRANK(MEAN(VOLUME, 60), 17), 5), 19), 16), 7)) * -1)
        ##
        data1 = (self.low * 0.7 + self.avg_price * 0.3).diff(3)
        decay_weights = np.arange(1, 21, 1)[::-1]  # 倒序数组
        decay_weights = decay_weights / decay_weights.sum()
        rank1 = data1.iloc[-20:, :].mul(decay_weights,
                                        axis=0).sum().rank(axis=0, pct=True)

        data1 = self.low.rolling(8).apply(self.func_rank)
        data2 = self.volume.rolling(60).mean().rolling(17).apply(
            self.func_rank)
        data3 = pd.rolling_corr(data1, data2,
                                window=5).rolling(19).apply(self.func_rank)
        rank2 = data3.rolling(16).apply(
            self.func_decaylinear).iloc[-7:, :].rank(axis=0,
                                                     pct=True).iloc[-1, :]

        alpha = (rank2 - rank1).dropna()
        return alpha

    def alpha_139(self):
        """
            (-1 * CORR(OPEN, VOLUME, 10))
        """
        #### (-1 * CORR(OPEN, VOLUME, 10))
        ##
        alpha = -self.open_price.iloc[-10:, :].corrwith(
            self.volume.iloc[-10:, :]).dropna()
        return alpha

    def alpha_140(self):
        """
            MIN(RANK(DECAYLINEAR(((RANK(OPEN) + RANK(LOW)) - (RANK(HIGH) + RANK(CLOSE))), 8)), 
            TSRANK(DECAYLINEAR(CORR(TSRANK(CLOSE, 8), TSRANK(MEAN(VOLUME,60), 20), 8), 7), 3))
        """
        #### MIN(RANK(DECAYLINEAR(((RANK(OPEN) + RANK(LOW)) - (RANK(HIGH) + RANK(CLOSE))), 8)), TSRANK(DECAYLINEAR(CORR(TSRANK(CLOSE, 8), TSRANK(MEAN(VOLUME, 60), 20), 8), 7), 3))
        ##
        data1 = self.open_price.rank(axis=1, pct=True) + self.low.rank(axis=1, pct=True) \
                - self.high.rank(axis=1, pct=True) - self.close.rank(axis=1, pct=True)
        rank1 = data1.iloc[-8:, :].apply(self.func_decaylinear).rank(pct=True)

        data1 = self.close.rolling(8).apply(self.func_rank)
        data2 = self.volume.rolling(60).mean().rolling(20).apply(
            self.func_rank)
        data3 = pd.rolling_corr(data1, data2, window=8)
        data3 = data3.rolling(7).apply(self.func_decaylinear)
        rank2 = data3.iloc[-3:, :].rank(axis=0, pct=True).iloc[-1, :]
        '''
        alpha = min(rank1, rank2)   NaN如何比较？
        '''
        return alpha

    def alpha_141(self):
        """
            (RANK(CORR(RANK(HIGH), RANK(MEAN(VOLUME,15)), 9))* -1)
        """
        #### (RANK(CORR(RANK(HIGH), RANK(MEAN(VOLUME, 15)), 9))* -1)
        ##
        df1 = self.high.rank(axis=1, pct=True)
        df2 = self.volume.rolling(15).mean().rank(axis=1, pct=True)
        alpha = -df1.iloc[-9:, :].corrwith(df2.iloc[-9:, :]).rank(pct=True)
        alpha = alpha.dropna()
        return alpha

    def alpha_142(self):
        """
            (((-1 * RANK(TSRANK(CLOSE, 10))) * RANK(DELTA(DELTA(CLOSE, 1), 1))) * RANK(TSRANK((VOLUME 
            /MEAN(VOLUME,20)), 5))) 
        """
        #### (((-1 * RANK(TSRANK(CLOSE, 10))) * RANK(DELTA(DELTA(CLOSE, 1), 1))) * RANK(TSRANK((VOLUME/MEAN(VOLUME, 20)), 5)))
        ##

        rank1 = self.close.iloc[-10:, :].rank(
            axis=0, pct=True).iloc[-1, :].rank(pct=True)
        rank2 = self.close.diff(1).diff(1).iloc[-1, :].rank(pct=True)
        rank3 = (self.volume /
                 self.volume.rolling(20).mean()).iloc[-5:, :].rank(
                     axis=0, pct=True).iloc[-1, :].rank(pct=True)

        alpha = -(rank1 * rank2 * rank3).dropna()
        alpha = alpha.dropna()
        return alpha

    def alpha_143(self):
        """
            CLOSE>DELAY(CLOSE,1)?(CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)*SELF:SELF
        """
        #### CLOSE > DELAY(CLOSE, 1)?(CLOSE - DELAY(CLOSE, 1)) / DELAY(CLOSE, 1) * SELF : SELF

        return 0

    def alpha_144(self):
        """
            SUMIF(ABS(CLOSE/DELAY(CLOSE,1)-1)/AMOUNT,20,CLOSE<DELAY(CLOSE,1))/COUNT(CLOSE<DELAY(CLOSE,
            1),20) 
        """
        #### SUMIF(ABS(CLOSE/DELAY(CLOSE, 1) - 1)/AMOUNT, 20, CLOSE < DELAY(CLOSE, 1))/COUNT(CLOSE < DELAY(CLOSE, 1), 20)
        ##
        df1 = self.close < self.prev_close
        sumif = ((abs(self.close / self.prev_close - 1) / self.amount) *
                 df1).iloc[-20:, :].sum()
        count = df1.iloc[-20:, :].sum()

        alpha = (sumif / count).dropna()
        alpha = alpha.dropna()
        return alpha

    def alpha_145(self):
        """
            (MEAN(VOLUME,9)-MEAN(VOLUME,26))/MEAN(VOLUME,12)*100
        """
        #### (MEAN(VOLUME, 9) - MEAN(VOLUME, 26)) / MEAN(VOLUME, 12) * 100
        ##

        alpha = (self.volume.iloc[-9:, :].mean() -
                 self.volume.iloc[-26:, :].mean()
                 ) / self.volume.iloc[-12:, :].mean() * 100
        alpha = alpha.dropna()
        return alpha

    def alpha_146(self):
        """
            MEAN((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1),61,2),20)*((
            CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1),61,2))/SMA(((CLOS
            E-DELAY(CLOSE,1))/DELAY(CLOSE,1)-((CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)-SMA((CLOSE-DELAY(CLOSE,
            1))/DELAY(CLOSE,1),61,2)))^2,60); 
        """
        return

    def alpha_147(self):
        """
            REGBETA(MEAN(CLOSE,12),SEQUENCE(12)) 
        """
        return

    def alpha_148(self):
        """
            ((RANK(CORR((OPEN), SUM(MEAN(VOLUME,60), 9), 6)) < RANK((OPEN - TSMIN(OPEN, 14)))) * -1)
        """
        #### ((RANK(CORR((OPEN), SUM(MEAN(VOLUME, 60), 9), 6)) < RANK((OPEN - TSMIN(OPEN, 14)))) * -1)
        ##
        df1 = self.volume.rolling(60).mean().rolling(9).sum()
        rank1 = self.open_price.iloc[-6:, :].corrwith(
            df1.iloc[-6:, :]).rank(pct=True)
        rank2 = (self.open_price -
                 self.open_price.rolling(14).min()).iloc[-1, :].rank(pct=True)

        alpha = -1 * (rank1 < rank2)
        alpha = alpha.dropna()
        return alpha

    def alpha_149(self):
        """
            REGBETA(FILTER(CLOSE/DELAY(CLOSE,1)-1,BANCHMARKINDEXCLOSE<DELAY(BANCHMARKINDEXCLOSE,1)
            ),FILTER(BANCHMARKINDEXCLOSE/DELAY(BANCHMARKINDEXCLOSE,1)-1,BANCHMARKINDEXCLOSE<DELA
            Y(BANCHMARKINDEXCLOSE,1)),252)
        """
        return

    def alpha_150(self):
        """
            (CLOSE+HIGH+LOW)/3*VOLUME 
        """
        #### (CLOSE + HIGH + LOW)/3 * VOLUME
        ##

        alpha = ((self.close + self.high + self.low) / 3 *
                 self.volume).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_151(self):
        """
            SMA(CLOSE-DELAY(CLOSE,20),20,1)
        """
        return 0

    ######################## alpha_152 #######################
    #
    def alpha_152(self):
        """
            SMA(MEAN(DELAY(SMA(DELAY(CLOSE/DELAY(CLOSE,9),1),9,1),1),12)-MEAN(DELAY(SMA(DELAY(CLOSE/DELAY
            (CLOSE,9),1),9,1),1),26),9,1) 
        """
        # SMA(MEAN(DELAY(SMA(DELAY(CLOSE/DELAY(CLOSE,9),1),9,1),1),12)-MEAN(DELAY(SMA(DELAY(CLOSE/DELAY(CLOSE,9),1),9,1),1),26),9,1) #
        #
        data1 = pd.rolling_mean((pd.ewma(
            ((self.close / self.close.shift(9)).shift()),
            span=17,
            adjust=False)).shift(), 12)
        data2 = pd.rolling_mean((pd.ewma(
            ((self.close / self.close.shift(9)).shift()),
            span=17,
            adjust=False)).shift(), 26)
        alpha = (pd.ewma(data1 - data2, span=17, adjust=False)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_153 #######################
    #
    def alpha_153(self):
        """
            (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/4
        """
        # (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/4 #
        alpha = (
            (pd.rolling_mean(self.close, 3) + pd.rolling_mean(self.close, 6) +
             pd.rolling_mean(self.close, 12) + pd.rolling_mean(self.close, 24))
            / 4).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_154 #######################
    #
    def alpha_154(self):
        """
            (((VWAP - MIN(VWAP, 16))) < (CORR(VWAP, MEAN(VOLUME,180), 18))) 

        """
        # (((VWAP-MIN(VWAP,16)))<(CORR(VWAP,MEAN(VOLUME,180),18))) #
        alpha = (self.avg_price - pd.rolling_min(self.avg_price, 16)
                 ).iloc[-1, :] < self.avg_price.iloc[-18:, :].corrwith(
                     (pd.rolling_mean(self.volume, 180)).iloc[-18:, :])
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_155 #######################
    #
    def alpha_155(self):
        """
            SMA(VOLUME,13,2)-SMA(VOLUME,27,2)-SMA(SMA(VOLUME,13,2)-SMA(VOLUME,27,2),10,2) 
        """
        # SMA(VOLUME,13,2)-SMA(VOLUME,27,2)-SMA(SMA(VOLUME,13,2)-SMA(VOLUME,27,2),10,2) #
        sma1 = pd.ewma(self.volume, span=12, adjust=False)
        sma2 = pd.ewma(self.volume, span=26, adjust=False)
        sma = pd.ewma(sma1 - sma2, span=9, adjust=False)
        alpha = sma.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_156 #######################
    def alpha_156(self):
        """
            (MAX(RANK(DECAYLINEAR(DELTA(VWAP, 5), 3)), RANK(DECAYLINEAR(((DELTA(((OPEN * 0.15) + (LOW *0.85)), 
            2) / ((OPEN * 0.15) + (LOW * 0.85))) * -1), 3))) * -1) 
        """
        # (MAX(RANK(DECAYLINEAR(DELTA(VWAP,5),3)),RANK(DECAYLINEAR(((DELTA(((OPEN*0.15)+(LOW*0.85)),2)/((OPEN*0.15)+(LOW*0.85)))*-1),3)))*-1 #
        rank1 = (pd.rolling_apply(self.avg_price - self.avg_price.shift(5), 3,
                                  self.func_decaylinear)).rank(axis=1,
                                                               pct=True)
        rank2 = pd.rolling_apply(
            -((self.open_price * 0.15 + self.low * 0.85) -
              (self.open_price * 0.15 + self.low * 0.85).shift(2)) /
            (self.open_price * 0.15 + self.low * 0.85), 3,
            self.func_decaylinear).rank(axis=1, pct=True)
        max_cond = rank1 > rank2
        result = rank2
        result[max_cond] = rank1[max_cond]
        alpha = (-result).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_157 #######################
    #
    def alpha_157(self):
        """
            (MIN(PROD(RANK(RANK(LOG(SUM(TSMIN(RANK(RANK((-1 * RANK(DELTA((CLOSE - 1), 5))))), 2), 1)))), 1), 5) + 
            TSRANK(DELAY((-1 * RET), 6), 5))
        """
        # (MIN(PROD(RANK(RANK(LOG(SUM(TSMIN(RANK(RANK((-1*RANK(DELTA((CLOSE-1),5))))),2),1)))),1),5)+TSRANK(DELAY((-1*RET),6),5)) #
        rank1 = (-((self.close - 1) -
                   (self.close - 1).shift(5)).rank(axis=1, pct=True)).rank(
                       axis=1, pct=True).rank(axis=1, pct=True)
        min1 = rank1.rolling(2).min()
        log1 = np.log(min1)
        rank2 = log1.rank(axis=1, pct=True).rank(axis=1, pct=True)
        cond_min = rank2 > 5
        rank2[cond_min] = 5
        tsrank1 = pd.rolling_apply(
            (-((self.close / self.prev_close) - 1)).shift(6), 5,
            self.func_rank)
        alpha = (rank2 + tsrank1).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    ######################## alpha_158 #######################
    #
    def alpha_158(self):
        """
            ((HIGH-SMA(CLOSE,15,2))-(LOW-SMA(CLOSE,15,2)))/CLOSE
        """
        # ((HIGH-SMA(CLOSE,15,2))-(LOW-SMA(CLOSE,15,2)))/CLOSE #
        alpha = (((self.high - pd.ewma(self.close, span=14, adjust=False)) -
                  (self.low - pd.ewma(self.close, span=14, adjust=False))) /
                 self.close).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_159(self):
        """
            ((CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),6))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,DELAY(CLOSE,1)),6)
            *12*24+(CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),12))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,DELAY(CL
            OSE,1)),12)*6*24+(CLOSE-SUM(MIN(LOW,DELAY(CLOSE,1)),24))/SUM(MAX(HGIH,DELAY(CLOSE,1))-MIN(LOW,D
            ELAY(CLOSE,1)),24)*6*24)*100/(6*12+6*24+12*24) 
        """
        #########((close-sum(min(low,delay(close,1)),6))/sum(max(high,delay(close,1))-min(low,delay(close,1)),6)*12*24+(close-sum(min(low,delay(close,1)),12))/sum(max(high,delay(close,1))-min(low,delay(close,1)),12)*6*24+(close-sum(min(low,delay(close,1)),24))/sum(max(high,delay(close,1))-min(low,delay(close,1)),24)*6*24)*100/(6*12+6*24+12*24)
        ###################
        data1 = self.low
        data2 = self.close.shift()
        cond = data1 > data2
        data1[cond] = data2
        data3 = self.high
        data4 = self.close.shift()
        cond = data3 > data4
        data3[~cond] = data4
        #计算出公式核心部分x
        x = ((self.close - pd.rolling_sum(data1, 6)) / pd.rolling_sum(
            (data2 - data1), 6)) * 12 * 24
        #计算出公式核心部分y
        y = ((self.close - pd.rolling_sum(data1, 12)) / pd.rolling_sum(
            (data2 - data1), 12)) * 6 * 24
        #计算出公式核心部分z
        z = ((self.close - pd.rolling_sum(data1, 24)) / pd.rolling_sum(
            (data2 - data1), 24)) * 6 * 24
        data5 = (x + y + z) * (100 / (6 * 12 + 12 * 24 + 6 * 24))
        alpha = data5.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_160(self):
        """
            SMA((CLOSE<=DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1) 
        """
        ################
        ############sma((close<=delay(close,1)?std(close,20):0),20,1)
        data1 = pd.rolling_std(self.close, 20)
        cond = self.close <= self.close.shift(0)
        data1[~cond] = 0
        data2 = pd.ewma(data1, span=39)
        alpha = data2.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_161(self):
        """
            MEAN(MAX(MAX((HIGH-LOW),ABS(DELAY(CLOSE,1)-HIGH)),ABS(DELAY(CLOSE,1)-LOW)),12)
        """
        ###########mean((max(max(high-low),abs(delay(close,1)-high)),abs(delay(close,1)-low)),12)
        ################
        data1 = (self.high - self.low)
        data2 = pd.Series.abs(self.close.shift() - self.high)
        cond = data1 > data2
        data1[~cond] = data2
        data3 = pd.Series.abs(self.close.shift() - self.low)
        cond = data1 > data3
        data1[~cond] = data3
        alpha = (pd.rolling_mean(data1, 12)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_162(self):
        """
            (SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100-MIN(SMA(MAX(CLOS
            E-DELAY(CLOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12))/(MAX(SMA(MAX(CLOSE-DELAY(C
            LOSE,1),0),12,1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12)-MIN(SMA(MAX(CLOSE-DELAY(CLOSE,1),0),12,
            1)/SMA(ABS(CLOSE-DELAY(CLOSE,1)),12,1)*100,12))
        """
        ###############(sma(max(close-delay(close,1),0),12,1)/sma(abs(close-delay(close,1)),12,1)*100-min(sma(max(close-delay(close,1),0),12,1)/sma(abs(close-delay(close,1)),12,1)*100,12))/(max(sma(max(close-delay(close,1),0),12,1)/sma(abs(close-delay(close,1)),12,1)*100),12)-min(sma(max(close-delay(close,1),0),12,1)/sma(abs(close-delay(close,1)),12,1)*100),12))
        #################
        #算出公式核心部分X
        data1 = self.close - self.close.shift()
        cond = data1 > 0
        data1[~cond] = 0
        x = pd.ewma(data1, span=23)
        data2 = pd.Series.abs(self.close - self.close.shift())
        y = pd.ewma(data2, span=23)
        z = (x / y) * 100
        cond = z > 12
        z[cond] = 12
        c = (x / y) * 100
        cond = c > 12
        c[~cond] = 12
        data3 = (x / y) * 100 - (z / c) - c
        alpha = data3.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_163(self):
        """
            RANK(((((-1 * RET) * MEAN(VOLUME,20)) * VWAP) * (HIGH - CLOSE)))
        """
        ################
        #######rank(((((-1*ret)*,ean(volume,20))*vwap)*(high-close)))
        data1 = (-1) * (self.close / self.close.shift() - 1) * pd.rolling_mean(
            self.volume, 20) * self.avg_price * (self.high - self.close)
        data2 = (data1.rank(axis=1, pct=True)).iloc[-1, :]
        alpha = data2
        alpha = alpha.dropna()
        return alpha

    def alpha_164(self):
        """
            SMA((((CLOSE>DELAY(CLOSE,1))?1/(CLOSE-DELAY(CLOSE,1)):1)-MIN(((CLOSE>DELAY(CLOSE,1))?1/(CLOSE-D
            ELAY(CLOSE,1)):1),12))/(HIGH-LOW)*100,13,2) 
        """
        ################
        ############sma((((close>delay(close,1))?1/(close-delay(close,1)):1)-min(((close>delay(close,1))?1/(close/delay(close,1)):1),12))/(high-low)*100,13,2)
        cond = self.close > self.close.shift()
        data1 = 1 / (self.close - self.close.shift())
        data1[~cond] = 1
        data2 = 1 / (self.close - self.close.shift())
        cond = data2 > 12
        data2[cond] = 12
        data3 = data1 - data2 / ((self.high - self.low) * 100)
        alpha = (pd.ewma(data3, span=12)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_165(self):
        """
            MAX(SUMAC(CLOSE-MEAN(CLOSE,48)))-MIN(SUMAC(CLOSE-MEAN(CLOSE,48)))/STD(CLOSE,48)
        """
        return 0

    def alpha_166(self):
        """
            -20*（）20-1^1.5*SUM(CLOSE/DELAY(CLOSE,1)-1-MEAN(CLOSE/DELAY(CLOSE,1)-1,20),20)/((20-1)*(20-2)(SUM((CLOSE/DELA
            Y(CLOSE,1),20)^2,20))^1.5) 
        """
        return 0

    def alpha_167(self):
        """
            SUM((CLOSE-DELAY(CLOSE,1)>0?CLOSE-DELAY(CLOSE,1):0),12)
        """
        ##
        ####sum(((close-delay(close,1)>0)?(close-delay(close,1)):0),12)####
        data1 = self.close - self.close.shift()
        cond = (data1 < 0)
        data1[cond] = 0
        data2 = (pd.rolling_sum(data1, 12)).iloc[-1, :]
        alpha = data2
        alpha = alpha.dropna()
        return alpha

    def alpha_168(self):
        """
            (-1*VOLUME/MEAN(VOLUME,20))
        """
        ##
        #####-1*volume/mean(volume,20)####
        data1 = (-1 * self.volume) / pd.rolling_mean(self.volume, 20)
        alpha = data1.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_169(self):
        """
            SMA(MEAN(DELAY(SMA(CLOSE-DELAY(CLOSE,1),9,1),1),12)-MEAN(DELAY(SMA(CLOSE-DELAY(CLOSE,1),9,1),1),
            26),10,1) 
        """
        ##
        ###sma(mean(delay(sma(close-delay(close,1),9,1),1),12)-mean(delay(sma(close-delay(close,1),1,1),1),26),10,1)#####
        data1 = self.close - self.close.shift()
        data2 = (pd.ewma(data1, span=17)).shift()
        data3 = pd.rolling_mean(data2, 12) - pd.rolling_mean(data2, 26)
        alpha = (pd.ewma(data3, span=19)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_170(self):
        """
            ((((RANK((1 / CLOSE)) * VOLUME) / MEAN(VOLUME,20)) * ((HIGH * RANK((HIGH - CLOSE))) / (SUM(HIGH, 5) / 
            5))) - RANK((VWAP - DELAY(VWAP, 5))))
        """
        ##
        #####((((rank((1/close))*volume)/mean(volume,20))*((high*rank((high-close)))/(sum(high,5)/5)))-rank((vwap-delay(vwap,5))))####
        data1 = (1 / self.close).rank(axis=0, pct=True)
        data2 = pd.rolling_mean(self.volume, 20)
        x = (data1 * self.volume) / data2
        data3 = (self.high - self.close).rank(axis=0, pct=True)
        data4 = pd.rolling_mean(self.high, 5)
        y = (data3 * self.high) / data4
        z = (self.avg_price.iloc[-1, :] - self.avg_price.iloc[-5, :]).rank(
            axis=0, pct=True)
        alpha = (x * y - z).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_171(self):
        """
            ((-1 * ((LOW - CLOSE) * (OPEN^5))) / ((CLOSE - HIGH) * (CLOSE^5)))
        """
        ##
        ####(((low-close)*open^5)*-1)/((close-high)*close^5)#####
        data1 = -1 * (self.low - self.close) * (self.open_price**5)
        data2 = (self.close - self.high) * (self.close**5)
        alpha = (data1 / data2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_172(self):
        """
            MEAN(ABS(SUM((LD>0& LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 &HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 &LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0& HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6)
        """
        # MEAN(ABS(SUM((LD>0&LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0&HD>LD)?HD:0,14)*100/(SUM((LD>0&LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM(TR,14)+SUM((HD>0&HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6) #
        hd = self.high - self.high.shift()
        ld = self.low.shift() - self.low
        temp1 = self.high - self.low
        temp2 = (self.high - self.close.shift()).abs()
        cond1 = temp1 > temp2
        temp2[cond1] = temp1[cond1]
        temp3 = (self.low - self.close.shift()).abs()
        cond2 = temp2 > temp3
        temp3[cond2] = temp2[cond2]
        tr = temp3  # MAX(MAX(HIGH-LOW,ABS(HIGH-DELAY(CLOSE,1))),ABS(LOW-DELAY(CLOSE,1)))
        sum_tr14 = pd.rolling_sum(tr, 14)
        cond3 = ld > 0
        cond4 = ld > hd
        cond3[~cond4] = False
        data1 = ld
        data1[~cond3] = 0
        sum1 = pd.rolling_sum(data1, 14) * 100 / sum_tr14
        cond5 = hd > 0
        cond6 = hd > ld
        cond5[~cond6] = False
        data2 = hd
        data2[~cond5] = 0
        sum2 = pd.rolling_sum(data2, 14) * 100 / sum_tr14
        alpha = pd.rolling_mean((sum1 - sum2).abs() / (sum1 + sum2) * 100,
                                6).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_173(self):
        """
            3*SMA(CLOSE,13,2)-2*SMA(SMA(CLOSE,13,2),13,2)+SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2);
        """
        ##
        ####3*sma(close,13,2)-2*sma(sma(close,13,2),13,2)+sma(sma(sma(log(close),13,2),13,2),13,2)#####
        data1 = pd.ewma(self.close, span=12)
        data2 = pd.ewma(data1, span=12)
        close_log = np.log(self.close)
        data3 = pd.ewma(close_log, span=12)
        data4 = pd.ewma(data3, span=12)
        data5 = pd.ewma(data4, span=12)
        alpha = (3 * data1 - 2 * data2 + data5).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_174(self):
        """
            SMA((CLOSE>DELAY(CLOSE,1)?STD(CLOSE,20):0),20,1)
        """
        ##
        ####sma((close>delay(close,1)?std(close,20):0),20,1)#####
        cond = self.close > self.prev_close
        data2 = pd.rolling_std(self.close, 20)
        data2[~cond] = 0
        alpha = (pd.ewma(data2, span=39, adjust=False)).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_175(self):
        """
            MEAN(MAX(MAX((HIGH-LOW),ABS(DELAY(CLOSE,1)-HIGH)),ABS(DELAY(CLOSE,1)-LOW)),6) 
        """
        ##
        #####mean(max(max(high-low),abs(delay(close,1)-high)),abs(delay(close,1)-low)),6)####
        data1 = self.high - self.low
        data2 = pd.Series.abs(self.close.shift() - self.high)
        cond = (data1 > data2)
        data2[cond] = data1[cond]
        data3 = pd.Series.abs(self.close.shift() - self.low)
        cond = (data2 > data3)
        data3[cond] = data2[cond]
        data4 = (pd.rolling_mean(data3, window=6)).iloc[-1, :]
        alpha = data4
        alpha = alpha.dropna()
        return alpha

    def alpha_176(self):
        """
            CORR(RANK(((CLOSE - TSMIN(LOW, 12)) / (TSMAX(HIGH, 12) - TSMIN(LOW,12)))), RANK(VOLUME), 6)
        """
        ##
        ######### #########corr(rank((close-tsmin(low,12))/(tsmax(high,12)-tsmin(low,12))),rank(volume),6)#############
        data1 = (self.close - pd.rolling_min(self.low, window=12)) / (
            pd.rolling_max(self.high, window=12) -
            pd.rolling_min(self.low, window=12))
        data2 = data1.rank(axis=0, pct=True)
        #获取数据求出rank2
        data3 = self.volume.rank(axis=0, pct=True)
        corr = data2.iloc[-6:, :].corrwith(data3.iloc[-6:, :])
        alpha = corr
        alpha = alpha.dropna()
        return alpha

    ################## alpha_177 ####################
    #
    def alpha_177(self):
        """
            ((20-HIGHDAY(HIGH,20))/20)*100 
        """
        ##### ((20-HIGHDAY(HIGH,20))/20)*100 #####
        alpha = (20 -
                 self.high.iloc[-20:, :].apply(self.func_highday)) / 20 * 100
        alpha = alpha.dropna()
        return alpha

    def alpha_178(self):
        """
            (CLOSE-DELAY(CLOSE,1))/DELAY(CLOSE,1)*VOLUME
        """
        ##### (close-delay(close,1))/delay(close,1)*volume ####
        ##
        alpha = ((self.close - self.close.shift()) / self.close.shift() *
                 self.volume).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_179(self):
        """
            (RANK(CORR(VWAP, VOLUME, 4)) *RANK(CORR(RANK(LOW), RANK(MEAN(VOLUME,50)), 12)))
        """
        #####（rank(corr(vwap,volume,4))*rank(corr(rank(low),rank(mean(volume,50)),12))####
        ##
        rank1 = (self.avg_price.iloc[-4:, :].corrwith(
            self.volume.iloc[-4:, :])).rank(axis=0, pct=True)
        data2 = self.low.rank(axis=0, pct=True)
        data3 = (pd.rolling_mean(self.volume, window=50)).rank(axis=0,
                                                               pct=True)
        rank2 = (data2.iloc[-12:, :].corrwith(data3.iloc[-12:, :])).rank(
            axis=0, pct=True)
        alpha = rank1 * rank2
        alpha = alpha.dropna()
        return alpha

    ##################### alpha_180 #######################
    #
    def alpha_180(self):
        """
            ((MEAN(VOLUME,20) < VOLUME) ? ((-1 * TSRANK(ABS(DELTA(CLOSE, 7)), 60)) * SIGN(DELTA(CLOSE, 7)) : (-1 *VOLUME)))
        """
        ##### ((MEAN(VOLUME,20)<VOLUME)?((-1*TSRANK(ABS(DELTA(CLOSE,7)),60))*SIGN(DELTA(CLOSE,7)):(-1*VOLUME))) #####
        ma = pd.rolling_mean(self.volume, window=20)
        cond = (ma < self.volume).iloc[-20:, :]
        sign = delta_close_7 = self.close.diff(7)
        sign[sign.iloc[:, :] < 0] = -1
        sign[sign.iloc[:, :] > 0] = 1
        sign[sign.iloc[:, :] == 0] = 0
        left = (
            ((self.close.diff(7).abs()).iloc[-60:, :].rank(axis=0, pct=True) *
             (-1)).iloc[-20:, :] * sign.iloc[-20:, :]).iloc[-20:, :]
        right = self.volume.iloc[-20:, :] * (-1)
        right[cond] = left[cond]
        alpha = right.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_181(self):
        """
            SUM(((CLOSE/DELAY(CLOSE,1)-1)-MEAN((CLOSE/DELAY(CLOSE,1)-1),20))-(BANCHMARKINDEXCLOSE-MEAN(BANCHMARKINDEXCLOSE,20))^2,20)/SUM((BANCHMARKINDEXCLOSE-MEAN(BANCHMARKINDEXCLOSE,20))^3) 
        """
        return 0

    ######################## alpha_182 #######################
    #
    def count_cond_182(self, x):
        """
           
        """
        num = 0
        for i in x:
            if i == np.True_:
                num += 1
        return num

    def alpha_182(self):
        """
            
            COUNT((CLOSE>OPEN & BANCHMARKINDEXCLOSE>BANCHMARKINDEXOPEN)OR(CLOSE<OPEN & BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN),20)/20 
        """
        ##### COUNT((CLOSE>OPEN & BANCHMARKINDEXCLOSE>BANCHMARKINDEXOPEN)OR(CLOSE<OPEN & BANCHMARKINDEXCLOSE<BANCHMARKINDEXOPEN),20)/20 #####
        cond1 = (self.close > self.open_price)
        cond2 = (self.benchmark_open_price > self.benchmark_close_price)
        cond3 = (self.close < self.open_price)
        cond4 = (self.benchmark_open_price < self.benchmark_close_price)
        func1 = lambda x: np.asarray(x) & np.asarray(cond2)
        func2 = lambda x: np.asarray(x) & np.asarray(cond4)
        cond = cond1.apply(func1) | cond3.apply(func2)
        count = pd.rolling_apply(cond, 20, self.count_cond_182)
        alpha = (count / 20).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_183(self):
        """
            MAX(SUMAC(CLOSE-MEAN(CLOSE,24)))-MIN(SUMAC(CLOSE-MEAN(CLOSE,24)))/STD(CLOSE,24)
        """
        return 0

    def alpha_184(self):
        #####(rank(corr(delay((open-close),1),close,200))+rank((open-close))) ####
        ##
        """
            (RANK(CORR(DELAY((OPEN - CLOSE), 1), CLOSE, 200)) + RANK((OPEN - CLOSE)))
        """
        data1 = self.open_price.shift() - self.close.shift()
        data2 = self.open_price.iloc[-1, :] - self.close.iloc[-1, :]
        corr = data1.iloc[-200:, :].corrwith(self.close.iloc[-200:, :])
        alpha = data2.rank(axis=0, pct=True) + corr.rank(axis=0, pct=True)
        alpha = alpha.dropna()
        return alpha

    def alpha_185(self):
        """
            RANK((-1 * ((1 - (OPEN / CLOSE))^2))) 
        """
        ##### RANK((-1 * ((1 - (OPEN / CLOSE))^2))) ####
        alpha = (-(1 - self.open_price / self.close)**2).rank(
            axis=1, pct=True).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    #
    def alpha_186(self):
        """
            (MEAN(ABS(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 & 
            HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 & 
            HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6)+DELAY(MEAN(ABS(SUM((LD>0 & 
            LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 & 
            LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6),6))/2 
        """
        # (MEAN(ABS(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6)+DELAY(MEAN(ABS(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)-SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))/(SUM((LD>0 & LD>HD)?LD:0,14)*100/SUM(TR,14)+SUM((HD>0 & HD>LD)?HD:0,14)*100/SUM(TR,14))*100,6),6))/2 #
        hd = self.high - self.high.shift()
        ld = self.low.shift() - self.low
        temp1 = self.high - self.low
        temp2 = (self.high - self.close.shift()).abs()
        cond1 = temp1 > temp2
        temp2[cond1] = temp1[cond1]
        temp3 = (self.low - self.close.shift()).abs()
        cond2 = temp2 > temp3
        temp3[cond2] = temp2[cond2]
        tr = temp3  # MAX(MAX(HIGH-LOW,ABS(HIGH-DELAY(CLOSE,1))),ABS(LOW-DELAY(CLOSE,1)))
        sum_tr14 = pd.rolling_sum(tr, 14)
        cond3 = ld > 0
        cond4 = ld > hd
        cond3[~cond4] = False
        data1 = ld
        data1[~cond3] = 0
        sum1 = pd.rolling_sum(data1, 14) * 100 / sum_tr14
        cond5 = hd > 0
        cond6 = hd > ld
        cond5[~cond6] = False
        data2 = hd
        data2[~cond5] = 0
        sum2 = pd.rolling_sum(data2, 14) * 100 / sum_tr14
        mean1 = pd.rolling_mean((sum1 - sum2).abs() / (sum1 + sum2) * 100, 6)
        alpha = ((mean1 + mean1.shift(6)) / 2).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_187(self):
        """
            SUM((OPEN<=DELAY(OPEN,1)?0:MAX((HIGH-OPEN),(OPEN-DELAY(OPEN,1)))),20)
        """
        ##### SUM((OPEN<=DELAY(OPEN,1)?0:MAX((HIGH-OPEN),(OPEN-DELAY(OPEN,1)))),20) ####

        cond = (self.open_price <= self.open_price.shift())
        data1 = self.high - self.low  # HIGH-LOW
        data2 = self.open_price - self.open_price.shift()  # OPEN-DELAY(OPEN,1)
        cond_max = data2 > data1
        data1[cond_max] = data2[cond_max]
        data1[cond] = 0
        alpha = data1.iloc[-20:, :].sum()
        alpha = alpha.dropna()
        return alpha

    def alpha_188(self):
        """
            ((HIGH-LOW–SMA(HIGH-LOW,11,2))/SMA(HIGH-LOW,11,2))*100 
        """
        ##### ((HIGH-LOW–SMA(HIGH-LOW,11,2))/SMA(HIGH-LOW,11,2))*100 #####

        sma = pd.ewma(self.high - self.low, span=10, adjust=False)
        alpha = ((self.high - self.low - sma) / sma * 100).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_189(self):
        """
            MEAN(ABS(CLOSE-MEAN(CLOSE,6)),6) 
        """
        ##### mean(abs(close-mean(close,6),6)) ####
        ma6 = pd.rolling_mean(self.close, window=6)
        alpha = pd.rolling_mean((self.close - ma6).abs(), window=6).iloc[-1, :]
        alpha = alpha.dropna()
        return alpha

    def alpha_190(self):
        """
            LOG((COUNT(CLOSE/DELAY(CLOSE)-1>((CLOSE/DELAY(CLOSE,19))^(1/20)-1),20)-1)*(SUMIF(((CLOSE/DELAY(C
            LOSE)-1-(CLOSE/DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)
            1))/((COUNT((CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)-1),20))*(SUMIF((CLOSE/DELAY(CLOS
            E)-1-((CLOSE/DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1>(CLOSE/DELAY(CLOSE,19))^(1/20)-1)))
            ) 
        """
        ##### LOG((COUNT(CLOSE/DELAY(CLOSE)-1>((CLOSE/DELAY(CLOSE,19))^(1/20)-1),20)-1)*(SUMIF(((CLOSE/DELAY(CLOSE)
        ##### -1-(CLOSE/DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)-1))/((
        ##### COUNT((CLOSE/DELAY(CLOSE)-1<(CLOSE/DELAY(CLOSE,19))^(1/20)-1),20))*(SUMIF((CLOSE/DELAY(CLOSE)-1-((CLOSE
        ##### /DELAY(CLOSE,19))^(1/20)-1))^2,20,CLOSE/DELAY(CLOSE)-1>(CLOSE/DELAY(CLOSE,19))^(1/20)-1)))) ####

        return 0

    def alpha_191(self):
        """
            ((CORR(MEAN(VOLUME,20), LOW, 5) + ((HIGH + LOW) / 2)) - CLOSE)
        """
        ##### (CORR(MEAN(VOLUME,20), LOW, 5) + ((HIGH + LOW) / 2)) - CLOSE ####
        # /chencheng
        volume_avg = pd.rolling_mean(self.volume, window=20)
        corr = volume_avg.iloc[-5:, :].corrwith(self.low.iloc[-5:, :])
        alpha = corr + (self.high.iloc[-1, :] +
                        self.low.iloc[-1, :]) / 2 - self.close.iloc[-1, :]
        alpha = alpha.dropna()
        return alpha


import jqfactor_analyzer as jqf

if __name__ == "__main__":

    index = '000300.XSHG'
    trade_list = jq.get_all_trade_days()
    yesterday_trdae_date = trade_list[np.argwhere(
        trade_list < dt.date.today())[-1]][0]  # 获取昨日交易日
    end_date = yesterday_trdae_date
    end_date = dt.date(2020, 5, 28)
    # security = get_index_stocks(index).index.to_list()
    security = [
        '000968.XSHE', '002130.XSHE', '002167.XSHE', '002370.XSHE',
        '002832.XSHE', '600297.XSHG', '600710.XSHG', '601717.XSHG',
        '603528.XSHG'
    ]
    #alpha_df = jq.alpha191.alpha_001()

    #security = jq.get_all_securities()
    # 使用前复权
    alpha191 = GTJA_191(end_date=end_date,
                        index=index,
                        stocks_pool=security,
                        count=350,
                        fq='post')

    print(alpha191.alpha_004())
