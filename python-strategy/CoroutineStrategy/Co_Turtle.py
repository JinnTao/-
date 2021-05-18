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
from  tqsdk import objs
from tqsdk import TqApi, TqAuth, TargetPosTask, TqKq, TqChan, TqAccount
import pandas as pd
from tqsdk.ta import ATR
from Common import Tao, CapitalManager
from contextlib import closing
from Common import mysqlConfig
import traceback
from tqsdk import tafunc

# 策略所用账户
ACC = Tao.ACC  # 天勤账号
PWD = Tao.PWD  # 天勤密码

LG_ACC = Tao.SIM_ACC  # 登陆所用账号
LG_PWD = Tao.SIM_PWD  # 登陆所用密码

# 交易模式
TRADE_MODE = Tao.TRADE_MODE.SIM

data = {
    "position": 0,
    "last_price": 0
}

turtle_state_dir = "../userdata/"

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

        self.api = api
        self.quote = self.api.get_quote(self.underlying_symbol)
        if self.quote.underlying_symbol == '':
            self.symbol = self.quote.instrument_id
        else:
            self.symbol = self.quote.underlying_symbol

        # print("Time : %s Trade Inst : %s" %(self.quote.datetime,self.symbol))
        # 由于ATR是路径依赖函数，因此使用更长的数据序列进行计算以便使其值稳定下来
        kline_length = max(donchian_channel_open_position + 1, donchian_channel_stop_profit + 1, atr_day_length * 5)
        self.klines = self.api.get_kline_serial(self.symbol, 24 * 60 * 60, data_length=kline_length)
        self.klines_10s = self.api.get_kline_serial(self.symbol, 10, data_length=kline_length)
        self.account = self.api.get_account()


        # 成交chan和订单chan
        self.on_trade_chan = TqChan(api, True,chan_name="on_trade")
        self.on_order_chan = TqChan(api, True,chan_name="on_order")

        self.target_pos = TargetPosTask(self.api, self.symbol,trade_chan = self.on_trade_chan,price="PASSIVE")

        self.trades = self.api.get_trade()
        self.orders = self.api.get_order()


        # 持仓引用
        self.position = self.api.get_position(self.symbol)

        self.json_file = None
        self.save_trades()
        self.init_by_load_trades()

        api.create_task(self.on_trade())
        api.create_task(self.on_order())

    async def on_trade(self):
        async for lastest in self.on_trade_chan:
            print(self.on_trade_chan.recv_latest(lastest))
        # async with api.register_update_notify(self.trades,self.on_trade_chan) as update_chan:
        #     async for _ in update_chan:
                # print("this is last  trades")
                # print(self.trades)

    async def on_order(self):
        async with api.register_update_notify(self.orders,self.on_order_chan) as update_chan:
            async for _ in update_chan:
                print("this is last  orders")
                print(self.orders)


    def get_net_position(self) -> int:

        return self.position.pos_long_his + self.position.pos_long_today - \
               self.position.pos_short_his - self.position.pos_short_today

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
            print("error")
        finally:
            mysql.close()

    def init(self, json_file, data):
        try:
            f = open(json_file, 'r')
            f.close()
        except IOError:
            f = open(json_file, 'w+')
            json.dump(data, f)
            f.close()
        finally:
            # 如果持仓为0 用账户数据跟新
            self.state = json.load(open(json_file, "r"))
            self.json_file = json_file

    def init_by_load_trades(self):
        # sql = "SELECT * FROM trade_db.tradelist WHERE account = \"%s\" and is_deleted = %d and 1=1" % \
        #       (ACC, 0)
        # dict_trade = self.mysql.get_dict_data_sql(sql)
        #
        # df_trade = pd.DataFrame.from_dict(dict_trade)
        try:
            mysql = mysqlConfig.MysqlDataConn(Tao.MYSQL_HOST, Tao.MYSQL_USER, Tao.MYSQL_PSWD, Tao.MYSQL_DB, 3306)
            sql = "SELECT * FROM trade_db.tradelist WHERE account = \"%s\" and is_deleted = %d  and inst like \"%s\"" \
                  " and offset = \"%s\" order by trade_date_time desc limit 1" % \
                  (ACC, 0, self.symbol.split('.')[1], "OPEN")
            #print(sql)
            dict_trade = mysql.get_dict_data_sql(sql)
            df_trade = pd.DataFrame.from_dict(dict_trade)
            self.state['last_price'] = 0
            self.state['position'] = 0
            if not df_trade.empty:
                #print(df_trade)
                latest_trade = df_trade.loc[0, :].to_dict();
                self.state['last_price'] = latest_trade['price']
                self.state['position'] = self.get_net_position()

            print(self.state)

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
            # margin_ratio = 10
            self.unit = int((self.account.available * 0.60) / (self.quote.volume_multiple * self.n ))
            # 唐奇安通道上轨：前N个交易日的最高价
            self.donchian_channel_high = max(self.klines.high[-self.donchian_channel_open_position - 1:-1])
            # 唐奇安通道下轨：前N个交易日的最低价
            self.donchian_channel_low = min(self.klines.low[-self.donchian_channel_open_position - 1:-1])
            # print("账户可用资金 %f " % self.account.available)
            print("%s 唐其安通道 合约:%14s 上下轨:%8s, %8s N值: %6.2f Unit:%4s 可用:%10s" %
                  (self.quote.datetime, self.symbol, self.donchian_channel_high, self.donchian_channel_low, self.n,
                   self.unit, self.account.available))
            return True
        except Exception as e:
            print(e)
            return False

    def set_position(self, pos):
        self.state["position"] = pos
        self.state["last_price"] = self.quote["last_price"]
        self.target_pos.set_target_volume(self.state["position"])
        # self.save_trades()

    async def try_open(self, updateChan: TqChan):
        """开仓策略"""
        # while self.state["position"] == 0:
        # self.api.wait_update()
        async for _ in updateChan:
            # 在14:55 到 15:00之间进行保存状态
            # self.try_save_state(self.quote, 14, 55)
            import random
            # 每隔10s下个单
            kline_time = tafunc.time_to_datetime(self.klines_10s.iloc[-1]["datetime"])
            print("curr : %s"%(kline_time))
            if self.api.is_changing(self.klines_10s.iloc[-1],'datetime'):
                self.set_position(random.randint(1, 6))

            if self.state["position"] != 0:
                break;
            # 除了新K线 还应包括持仓变动
            if self.api.is_changing(self.klines.iloc[-1], "datetime"):  # 如果产生新k线,则重新计算唐奇安通道及买卖单位
                self.recalc_paramter()
            if self.api.is_changing(self.quote, "last_price"):

                # print("最新价: %f" % self.quote.last_price)
                if self.quote.last_price > self.donchian_channel_high and self.unit != 0:  # 当前价>唐奇安通道上轨，买入1个Unit；(持多仓)
                    print("合约: %s 当前价>唐奇安通道上轨，买入1个Unit(持多仓): %d 手" % (self.symbol, self.unit))
                    self.set_position(self.state["position"] + self.unit)
                elif self.quote.last_price < self.donchian_channel_low and self.unit != 0:  # 当前价<唐奇安通道下轨，卖出1个Unit；(持空仓)
                    print("合约: %s 当前价<唐奇安通道下轨，卖出1个Unit(持空仓): %d 手" % (self.symbol, self.unit))
                    self.set_position(self.state["position"] - self.unit)

    async def try_close(self, updateChan: TqChan):
        """交易策略"""
        # while self.state["position"] != 0:
        # self.api.wait_update()
        async for _ in updateChan:
            self.try_save_state(self.quote, 14, 55)
            if self.state['position'] == 0:
                break;
            if self.api.is_changing(self.quote, "last_price"):
                # print("最新价: ", self.quote.last_price)
                if self.state["position"] > 0:  # 持多单
                    # 加仓策略: 如果是多仓且行情最新价在上一次建仓（或者加仓）的基础上又上涨了0.5N，
                    # 就再加一个Unit的多仓,并且风险度在设定范围内(以防爆仓)
                    if self.quote.last_price >= \
                            self.state["last_price"] + 0.5 * self.n and self.account.risk_ratio <= self.max_risk_ratio:
                        print("加仓:加1个Unit的多仓")
                        self.set_position(self.state["position"] + self.unit)
                    # 止损策略: 如果是多仓且行情最新价在上一次建仓（或者加仓）的基础上又下跌了2N，就卖出全部头寸止损
                    elif self.quote.last_price <= self.state["last_price"] - 2 * self.n:
                        print("止损:卖出全部头寸")
                        self.set_position(0)
                    # 止盈策略: 如果是多仓且行情最新价跌破了10日唐奇安通道的下轨，就清空所有头寸结束策略,离场
                    if self.quote.last_price <= min(self.klines.low[-self.donchian_channel_stop_profit - 1:-1]):
                        print("止盈:清空所有头寸结束策略,离场")
                        self.set_position(0)

                elif self.state["position"] < 0:  # 持空单
                    # 加仓策略: 如果是空仓且行情最新价在上一次建仓（或者加仓）的基础上又下跌了0.5N，就再加一个Unit的空仓,并且风险度在设定范围内(以防爆仓)
                    if self.quote.last_price <= \
                            self.state["last_price"] - 0.5 * self.n and self.account.risk_ratio <= self.max_risk_ratio:
                        print("加仓:加1个Unit的空仓")
                        self.set_position(self.state["position"] - self.unit)
                    # 止损策略: 如果是空仓且行情最新价在上一次建仓（或者加仓）的基础上又上涨了2N，就平仓止损
                    elif self.quote.last_price >= self.state["last_price"] + 2 * self.n:
                        print("止损:卖出全部头寸")
                        self.set_position(0)
                    # 止盈策略: 如果是空仓且行情最新价升破了10日唐奇安通道的上轨，就清空所有头寸结束策略,离场
                    if self.quote.last_price >= max(self.klines.high[-self.donchian_channel_stop_profit - 1:-1]):
                        print("止盈:清空所有头寸结束策略,离场")
                        self.set_position(0)

    async def strategy(self):
        """海龟策略"""
        # print("等待K线及账户数据...")

        async with self.api.register_update_notify([self.quote, self.klines,self.klines_10s]) as update_chan:
            # 确保收到了所有订阅的数据
            while not api.is_serial_ready(self.klines):
                await update_chan.recv()

            while not api.is_serial_ready(self.klines_10s):
                await update_chan.recv()

            deadline = time.time() + 5
            while not self.recalc_paramter():
                if not self.api.wait_update(deadline=deadline):
                    raise Exception("获取数据失败，请确认行情连接正常并已经登录交易账户")
            # while True:
            #     self.try_open(update_chan)
            #     self.try_close(update_chan)
            # print("进入策略循环: ", self.symbol)
            while True:
                await self.try_open(update_chan)
                await self.try_close(update_chan)

    def try_save_state(self, quote, close_hour, close_minute) -> bool:
        # 每个交易日 临近
        if api.is_changing(quote, "datetime"):
            now_time = datetime.datetime.strptime(quote.datetime, "%Y-%m-%d %H:%M:%S.%f")  # 获取当前的行情时间
            if now_time.hour == close_hour and now_time.minute >= close_minute:  # 到达平仓时间: 平仓
                print("临近本交易日收盘: 保存状态")
                json.dump(self.state, open(self.json_file, "w"))  #
                # deadline = time.time() + 60  # 设置截止时间为当前时间的60秒以后
                # while self.api.wait_update(deadline=deadline):  # 等待60秒
                #     pass
                # self.api.close()  # 关闭api
                # break  # 退出while循环
                return True
        return False


async def coroutine_turtle(api: TqApi, symbol: str) -> None:
    global turtle_state_dir
    turtle = Turtle(symbol, api)
    # json_file = turtle_state_dir + symbol + ".json"
    # check json file
    # turtle.init(json_file, data)
    # turtle.init_by_load_trades()
    # run turtle


    await turtle.strategy()


def orgin():
    # turtle = Turtle("SHFE.au2006")
    # turtle = Turtle(Tao.MAIN_SHFE_AU,account=TqKq(),auth=TqAuth(Tao.ACC,Tao.PWD))
    turtle = Turtle()
    turtle_state_dir = "../userdata/turtle_state.json"
    print("策略开始运行")
    try:
        turtle.state = json.load(open(turtle_state_dir, "r"))  # 读取数据: 本策略目标净持仓数,上一次开仓价
    except FileNotFoundError:
        pass
    print("当前持仓数: %d, 上次调仓价: %f" % (turtle.state["position"], turtle.state["last_price"]))
    try:
        turtle.strategy()
    finally:
        turtle.api.close()
        json.dump(turtle.state, open(turtle_state_dir, "w"))  #
    return


def init_turtle(api: TqApi, s: pd.Series):
    # print("trade:",s['quote_inst'],",pos:",s['pos'])
    # coroutine_turtle(api, s['quote_inst'])
    api.create_task(coroutine_turtle(api, s['quote_inst']))
    return


# 1 修改保存数据到一个json file中
# 2 观察保存数据是否是持仓数据，如果是则直接用持仓数据进行 则省略了创建文件的难点

if __name__ == "__main__":
    api = TqApi(account=TqKq(), auth=TqAuth(LG_ACC, LG_PWD))
    # 这里修改为动态的
    cm = CapitalManager.CapitalManager(api, 10000, 0.80)

    # 根据资金情况 调整初始化建仓单位？
    # quoteList = cm.query_quotes([Tao.EXCHANGE_SHFE
    #                                 , Tao.EXCHANGE_DCE
    #                                 , Tao.EXCHANGE_CZCE
    #                              ])
    quoteList = [Tao.SHFE_AU_2106]
    pos_pd = cm.calc_pos_list_by_turle(quoteList, 20)
    print(pos_pd)
    pos_pd.apply(lambda x: init_turtle(api, x), axis=1)

    with closing(api):
        while True:
            api.wait_update()
