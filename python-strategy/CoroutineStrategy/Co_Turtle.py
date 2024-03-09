#!/usr/bin/env python
#  -*- coding: utf-8 -*-
__author__ = 'limin'

'''
海龟策略 (难度：中级)
参考: https://www.shinnytech.com/blog/turtle/
注: 该示例策略仅用于功能示范, 实盘时请根据自己的策略/经验进行修改
'''
import json
import time
import datetime
import pandas as pd
import traceback
from contextlib import closing
from threading import Timer

from Common import mysqlConfig, Tao, CapitalManager, orderManager
from tqsdk import TqApi, TqAuth, TargetPosTask, TqKq, TqAccount, tafunc, TqChan
from tqsdk.ta import ATR

import random
from asyncio import gather
from inspect import isfunction

# 策略所用账户
ACC = Tao.ACC  # 天勤账号
PWD = Tao.PWD  # 天勤密码

LG_ACC = Tao.SIM_ACC  # 登陆所用账号
LG_PWD = Tao.SIM_PWD  # 登陆所用密码

# 交易模式
TRADE_MODE = Tao.TRADE_MODE.SIM
# 配置loggging
logger = Tao.setup_logging(default_path="../config/config.yml")


class Turtle:
    def __int__(self):
        pass

    def __init__(self, underlying_symbol: str, api: TqApi, donchian_channel_open_position=20,
                 donchian_channel_stop_profit=10,
                 atr_day_length=20, max_risk_ratio=0.9):
        self.underlying_symbol = underlying_symbol  # 合约代码
        self.donchian_channel_open_position = donchian_channel_open_position  # 唐奇安通道的天数周期(开仓)
        self.donchian_channel_stop_profit = donchian_channel_stop_profit  # 唐奇安通道的天数周期(止盈)
        self.atr_day_length = atr_day_length  # ATR计算所用天数
        self.max_risk_ratio = max_risk_ratio  # 最高风险度
        self.state = {
            "position": 0,  # 本策略净持仓数(正数表示多头，负数表示空头，0表示空仓)
            "last_price": float("nan"),  # 上次调仓价
        }

        self.n = 0  # 平均真实波幅(N值)
        self.unit = 0  # 买卖单位
        self.donchian_channel_high = 0  # 唐奇安通道上轨
        self.donchian_channel_low = 0  # 唐奇安通道下轨

        self._api = api
        self._quote = self._api.get_quote(self.underlying_symbol)
        if self._quote.underlying_symbol == '':
            self._symbol = self._quote.instrument_id
        else:
            self._symbol = self._quote.underlying_symbol
        self._exchange = self._symbol.split(".")[0]

        # logger.info("Time : %s Trade Inst : %s" %(self.quote.datetime,self.symbol))
        # 由于ATR是路径依赖函数，因此使用更长的数据序列进行计算以便使其值稳定下来
        kline_length = max(donchian_channel_open_position + 1, donchian_channel_stop_profit + 1, atr_day_length * 5)
        self.klines = self._api.get_kline_serial(self._symbol, 24 * 60 * 60, data_length=kline_length)
        self.account = self._api.get_account()
        self.order_pool = []
        self._price = 0
        # 订单
        self._order_factory = orderManager.OrderFactory(self._api)
        self._order_vilid_time = Tao.ORDER_LIVE_TIME  # 半个小时 seconds

        # 持仓引用
        self._pos = self._api.get_position(self._symbol)
        # 保存历史成交
        self.trades = self._api.get_trade()
        self.save_trades()
        self.init_by_load_trades()

    def save_trades(self):
        # 初始化mysql 链接
        mysql = mysqlConfig.MysqlDataConn(Tao.MYSQL_HOST, Tao.MYSQL_USER, Tao.MYSQL_PSWD, Tao.MYSQL_DB, 3306)
        try:

            data = {}
            for k, v in self.trades.items():
                data['trade_id'] = v['trade_id']
                data['order_id'] = v['order_id']
                data['exchange_trade_id'] = v['exchange_trade_id']
                data['account'] = ACC
                data['exchange_id'] = v['exchange_id']
                data['inst'] = v['instrument_id']
                data['trade_date_time'] = Tao.convert_dt2str(v['trade_date_time'])
                data['direction'] = v['direction']
                data['offset'] = v['offset']
                data['vol'] = v['volume']
                data['price'] = v['price']
                data['is_deleted'] = 0
                data['mode'] = TRADE_MODE.name
                mysql.write('tradelist', data)

        except:
            logger.info("error")
        finally:
            mysql.close()

    def init_by_load_trades(self):
        mysql = None
        try:
            mysql = mysqlConfig.MysqlDataConn(Tao.MYSQL_HOST, Tao.MYSQL_USER, Tao.MYSQL_PSWD, Tao.MYSQL_DB, 3306)
            sql = "SELECT * FROM trade_db.tradelist WHERE account = \"%s\" and is_deleted = %d  and inst like \"%s\"" \
                  " and offset = \"%s\" order by trade_date_time desc limit 1" % \
                  (ACC, 0, self._symbol.split('.')[1], "OPEN")
            # logger.info(sql)
            dict_trade = mysql.get_dict_data_sql(sql)
            df_trade = pd.DataFrame.from_dict(dict_trade)
            self.state['last_price'] = 0
            self.state['position'] = 0
            if not df_trade.empty:
                # logger.info(df_trade)
                latest_trade = df_trade.loc[0, :].to_dict();
                self.state['last_price'] = latest_trade['price']
                self.state['position'] = self._pos.pos

            # logger.info("当前持仓数:{0},上一笔成交价".format())

        except Exception as e:
            traceback.print_exc()
        finally:
            mysql.close()

    def recalc_paramter(self):
        try:
            # 平均真实波幅(N值)
            self.n = ATR(self.klines, self.atr_day_length)["atr"].iloc[-1]
            # 买卖单位
            #: 账户权益 （账户权益 = 动态权益 = 静态权益 + 平仓盈亏 + 持仓盈亏 - 手续费 + 权利金 + 期权市值）

            self.unit = max(int((self.account.available * 0.06) / (self._quote.volume_multiple * self.n)), 0)
            margin_ratio = 0.1
            while self.unit > 0:
                if self.unit * margin_ratio * self._quote.last_price * self._quote.volume_multiple < self.account.available:
                    break;
                else:
                    # 调整unit的之
                    self.unit -= 1

            # 唐奇安通道上轨：前N个交易日的最高价
            self.donchian_channel_high = max(self.klines.high[-self.donchian_channel_open_position - 1:-1])
            # 唐奇安通道下轨：前N个交易日的最低价
            self.donchian_channel_low = min(self.klines.low[-self.donchian_channel_open_position - 1:-1])
            # logger.info("账户可用资金 %f " % self.account.available)
            logger.info("Pos:%4s,Last_price:%9.2f,Inst:%12s 上下轨:%8s, %8s N值: %6.2f Unit:%4s 可用:%10.2f,QuoteTime:%s" %
                        (self.state['position'], self.state['last_price'], self._symbol,
                         self.donchian_channel_high, self.donchian_channel_low, self.n,
                         self.unit, self.account.available, self._quote.datetime))
            return True
        except Exception as e:
            logger.info(e)
            return False

    def is_finish_order(self) -> bool:
        order_flow = self._order_factory.get_order_flow()
        trade_price = []
        is_finish = True
        for order in order_flow:
            logger.info("OrderId:{0} {1} {2} vol_ori:{3} vol_left:{4} is_dead:{5} is_error:{6} is_error:{7} is_online:{8} msg:{9}".format(
                order.order_id,order.instrument_id,order.direction,order.offset,order.volume_orign,order.volume_left,
                order.is_dead,order.is_error,order.is_online,order.last_msg
            ))
            if not order.is_dead:
                is_finish = False
            # 挂单超时 撤单
            self._order_factory.cancel_over_time(order,
                                                 tafunc.time_to_datetime(self._quote.datetime),
                                                 datetime.timedelta(seconds=self._order_vilid_time))
            trade_price.append(order.trade_price)
        # 可能部分成交
        if not pd.isna(pd.Series(trade_price, dtype='float64').mean()):
            self.state["last_price"] = self._quote["last_price"]
            self.state["position"] = self._pos.pos
        return is_finish

    def set_position(self, pos):
        self._order_factory.set_target_position(self._symbol, pos, "PASSIVE")

    async def try_open(self, updateChan: TqChan):
        """开仓策略"""
        async for _ in updateChan:
            if self.state["position"] != 0:
                break;
            # 除了新K线 还应包括持仓变动
            if self._api.is_changing(self.klines.iloc[-1], "datetime"):  # 如果产生新k线,则重新计算唐奇安通道及买卖单位
                self.recalc_paramter()
            if self._api.is_changing(self._quote, "last_price"):
                # 存在未成交订单
                if not self.is_finish_order():
                    continue
                # 清空订单状态
                self._order_factory.clear_order()

                # 可用资金不足
                if self.account.available < 0:
                    continue

                # logger.info("最新价: %f" % self.quote.last_price)
                if self._quote.last_price > self.donchian_channel_high and self.unit != 0:  # 当前价>唐奇安通道上轨，买入1个Unit；(持多仓)
                    logger.info("合约: %s 当前价>唐奇安通道上轨，买入1个Unit(持多仓): %d 手" % (self._symbol, self.unit))
                    self.set_position(self.state["position"] + self.unit)
                elif self._quote.last_price < self.donchian_channel_low and self.unit != 0:  # 当前价<唐奇安通道下轨，卖出1个Unit；(持空仓)
                    logger.info("合约: %s 当前价<唐奇安通道下轨，卖出1个Unit(持空仓): %d 手" % (self._symbol, self.unit))
                    self.set_position(self.state["position"] - self.unit)

    async def try_close(self, updateChan: TqChan):
        """交易策略"""
        async for _ in updateChan:
            if self.state['position'] == 0:
                break;
            if self._api.is_changing(self._quote, "last_price"):
                # 存在未成交订单
                if not self.is_finish_order():
                    continue
                # 全部成交 清空订单状态
                self._order_factory.clear_order()

                if self.state["position"] > 0:  # 持多单
                    # 加仓策略: 如果是多仓且行情最新价在上一次建仓（或者加仓）的基础上又上涨了0.5N，
                    # 就再加一个Unit的多仓,并且风险度在设定范围内(以防爆仓)
                    if self._quote.last_price >= \
                            self.state["last_price"] + 0.5 * self.n and self.account.risk_ratio <= self.max_risk_ratio\
                            and self.unit != 0:
                        msg = "加仓:加1个Unit的多仓"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        logger.info(self._symbol," ",self._quote.last_price," ",self._pos.pos," ",self.account.available)
                        self.set_position(self.state["position"] + self.unit)
                    # 止损策略: 如果是多仓且行情最新价在上一次建仓（或者加仓）的基础上又下跌了2N，就卖出全部头寸止损
                    elif self._quote.last_price <= self.state["last_price"] - 2 * self.n:
                        msg = "止损:卖出全部头寸"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        self.set_position(0)
                    # 止盈策略: 如果是多仓且行情最新价跌破了10日唐奇安通道的下轨，就清空所有头寸结束策略,离场
                    if self._quote.last_price <= min(self.klines.low[-self.donchian_channel_stop_profit - 1:-1]):
                        msg = "止盈:清空所有头寸结束策略,离场"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        self.set_position(0)

                elif self.state["position"] < 0:  # 持空单
                    # 加仓策略: 如果是空仓且行情最新价在上一次建仓（或者加仓）的基础上又下跌了0.5N，就再加一个Unit的空仓,并且风险度在设定范围内(以防爆仓)
                    if self._quote.last_price <= \
                            self.state["last_price"] - 0.5 * self.n and self.account.risk_ratio <= self.max_risk_ratio\
                            and self.unit != 0:
                        msg = "加仓:加1个Unit的空仓"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        self.set_position(self.state["position"] - self.unit)
                    # 止损策略: 如果是空仓且行情最新价在上一次建仓（或者加仓）的基础上又上涨了2N，就平仓止损
                    elif self._quote.last_price >= self.state["last_price"] + 2 * self.n:
                        msg = "止损:卖出全部头寸"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        self.set_position(0)
                    # 止盈策略: 如果是空仓且行情最新价升破了10日唐奇安通道的上轨，就清空所有头寸结束策略,离场
                    if self._quote.last_price >= max(self.klines.high[-self.donchian_channel_stop_profit - 1:-1]):
                        msg = "止盈:清空所有头寸结束策略,离场"
                        logger.info("{0} {1} {2} {3} {4}".format(self._symbol,self._quote.last_price,self._pos.pos,
                                                                         self.account.available,msg))
                        self.set_position(0)

    async def strategy(self):
        """海龟策略"""
        # logger.info("等待K线及账户数据...")

        async with self._api.register_update_notify([self._quote, self.klines]) as update_chan:
            # 确保收到了所有订阅的数据
            while not api.is_serial_ready(self.klines):
                await update_chan.recv()

            deadline = time.time() + 5
            while not self.recalc_paramter():
                if not self._api.wait_update(deadline=deadline):
                    raise Exception("获取数据失败，请确认行情连接正常并已经登录交易账户")

            while True:
                await self.try_open(update_chan)
                await self.try_close(update_chan)


async def coroutine_turtle(api: TqApi, symbol: str) -> None:
    global turtle_state_dir
    turtle = Turtle(symbol, api)
    await turtle.strategy()


def init_turtle(api: TqApi, s: pd.Series):
    api.create_task(coroutine_turtle(api, s['quote_inst']))
    return


def risk_controller(api):
    try:
        # api = TqApi(account=TqKq(), auth=TqAuth(LG_ACC, LG_PWD))
        rule = api.get_risk_management_rule(exchange_id="SSE")
        logger.info(rule)
        logger.info("自成交限制:", rule.self_trade)
        logger.info("频繁报撤单限制:", rule.frequent_cancellation)
        logger.info("成交持仓比限制:", rule.trade_position_ratio)
    except Exception as e:
        logger.info(e)


if __name__ == "__main__":

    logger.info("***************************  strategy start  *******************************")
    api = TqApi(account=TqKq(), auth=TqAuth(LG_ACC, LG_PWD))
    # api.set_risk_management_rule(exchange_id="SSE", enable=True)
    # # 等待发送数据
    # api.wait_update()
    # tr = Timer(10,risk_controller,(api,))
    # 资金管理
    cm = CapitalManager.CapitalManager(api, 10000, 0.80)

    # 根据资金情况 调整初始化建仓单位？
    quoteList = cm.query_quotes([Tao.EXCHANGE_SHFE
                                    , Tao.EXCHANGE_DCE
                                    , Tao.EXCHANGE_CZCE
                                 ])
    im = Tao.InstManager(api)
    invalid_pos = im.enable_trade_inst(quoteList)
    if len(invalid_pos) > 0:
        logger.info("Non main-inst:{0} in position".format(invalid_pos))

    pos_pd = cm.calc_pos_list_by_turle(quoteList, 20)
    pos_pd.apply(lambda x: init_turtle(api, x), axis=1)

    with closing(api):
        while True:
            api.wait_update()
