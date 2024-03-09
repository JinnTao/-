#!/usr/bin/python3
__author__ = "liyong"


import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
from Common import Tao
import json
import time
import datetime
import pandas as pd
import traceback
from contextlib import closing
from threading import Timer
import math

from Common import mysqlConfig, Tao, CapitalManager, orderManager
from tqsdk import TqApi, TqAuth, TargetPosTask, TqKq, TqAccount, tafunc, TqChan
from tqsdk.ta import ATR

import random
from asyncio import gather
from inspect import isfunction

# 策略所用账户
ACC = Tao.REAL_ACC # 天勤账号
PWD = Tao.REAL_PWD # 天勤密码

LG_ACC = Tao.SIM_ACC # 登陆所用账号
LG_PWD = Tao.SIM_PWD # 登陆所用密码

# 交易模式
TRADE_MODE = Tao.TRADE_MODE.REAL
# 配置loggging


logger = Tao.setup_logging(default_path="../../config/test.yml")



def init_auto_encoder():
    # 模型建立
    model = tf.keras.models.Sequential(layers=[
        tf.keras.layers.Conv2D(filters=16, kernel_size=(3, 3), padding="same", activation=tf.nn.relu,
                               input_shape=(28, 28, 1)),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        tf.keras.layers.Conv2D(filters=8, kernel_size=(3, 3), padding="same", activation=tf.nn.relu),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        tf.keras.layers.Conv2D(filters=8, kernel_size=(3, 3), padding="same", activation=tf.nn.relu),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        # encode 4,4,8
        # let us decode
        # 中间缩小到很小。。表达的是基本结构。
        # 然后下面再给他还原回去。
        tf.keras.layers.Conv2D(8, (3, 3), activation="relu", padding="same"),
        tf.keras.layers.UpSampling2D((2, 2)),
        tf.keras.layers.Conv2D(8, (3, 3), activation="relu", padding="same"),
        tf.keras.layers.UpSampling2D((2, 2)),
        tf.keras.layers.Conv2D(16, (3, 3), activation="relu"),
        tf.keras.layers.UpSampling2D((2, 2)),
        tf.keras.layers.Conv2D(1, (3, 3), activation="sigmoid", padding="same"),
    ], name="AutoEncoder")

    return model

def init_all_connect():

    # 模型建立
    model = tf.keras.models.Sequential(layers=[
        tf.keras.layers.Conv2D(filters=16, kernel_size=(3, 3), padding="same", activation=tf.nn.relu,
                               input_shape=(28, 28, 1)),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        tf.keras.layers.Conv2D(filters=8, kernel_size=(3, 3), padding="same", activation=tf.nn.relu),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        tf.keras.layers.Conv2D(filters=8, kernel_size=(3, 3), padding="same", activation=tf.nn.relu),
        tf.keras.layers.MaxPooling2D(pool_size=(2, 2), padding="same"),
        # Flatten 变成784 的输入
        tf.keras.layers.Flatten(),
        # 512的全连接层
        tf.keras.layers.Dense(512, activation=tf.nn.relu),
        # droput 0.2  这个 以后再做讨论 主要是用来防止过拟合
        tf.keras.layers.Dropout(0.2),
        # 全连接层 10
        tf.keras.layers.Dense(2, activation=tf.nn.softmax)

    ], name="AutoEncoder")

def generate_x_factor(input : pd.DataFrame,klines: pd.DataFrame):

    output = pd.DataFrame();
    output.loc[:,"date"] = input.loc[:,"datetime"].map(Tao.convert_2_date)
    output.loc[:,'datetime'] = input.loc[:,'datetime'].map(Tao.convert_dt)
    output.loc[:,'last_price'] = input.loc[:,'last_price']
    # output.loc[:, 'open'] = input.loc[:, 'open']
    # output.loc[:, 'high'] = input.loc[:, 'highest']# 未来函数 在实际使用中用处不大
    # output.loc[:, 'low'] = input.loc[:, 'lowest'] #
    output.loc[:, 'prc_spread'] = input.loc[:, 'bid_price1'] - input.loc[:, 'ask_price1']
    output.loc[:, 'vol_spread'] = input.loc[:, 'bid_volume1'] - input.loc[: , 'ask_volume1']
    output.loc[:, 'vol_spread'] = input.loc[:, 'bid_volume1'] + input.loc[:, 'ask_volume1']
    output.loc[:, 'ln_vol_sprd'] = (input.loc[:, 'bid_volume1'] / input.loc[: , 'ask_volume1']).map(math.log)
    output.loc[:, 'day_vol'] =  input.loc[:,'volume']
    output.loc[:, 'diff_vol'] = input.loc[:,'volume'].diff()
    output.loc[:, 'avg_spread'] = (input.loc[:, 'bid_price1'] + input.loc[:, 'ask_price1']) / 2.0
    output.loc[:, 'amount'] = input.loc[:,'amount']
    output.loc[:, 'amount_diff'] = input.loc[:, 'amount'].diff()
    output.loc[:, 'open_interest'] = input.loc[:, 'open_interest']
    output.loc[:, 'open_interest_diff'] = input.loc[:, 'open_interest'].diff()
    for explode in range(20):

        output.loc[:, "yd_close_price"] = output.loc[:,"date"].apply(lambda x:obtain_day_data(klines,x,"close"))
        output.loc[:, "yd_open_price"] = output.loc[:, "date"].apply(lambda x: obtain_day_data(klines, x, "open"))
        output.loc[:, "yd_high_price"] = output.loc[:, "date"].apply(lambda x: obtain_day_data(klines, x, "high"))

    return output.dropna()


def prepareData():
    pass


def obtain_day_data(klines,date, tag:str):
    return klines.loc[date, :][tag]


if __name__ == "__main__":
    logger.info("***************************  strategy start  *******************************")

    # 指定交易所合约，这里以主力fb铅板为例子
    api = TqApi(account=TqAccount(Tao.BROKER_10008,ACC,PWD),auth=TqAuth(LG_ACC,LG_PWD))
    underlying_symbol = Tao.MAIN_DCE_FB
    quote = api.get_quote(underlying_symbol)
    if quote.underlying_symbol == '':
        symbol = quote.instrument_id
    else:
        symbol = quote.underlying_symbol
    exchange = symbol.split(".")[0]

    # 获取klines数据和ticks数据，最大长度目前为8964
    klines = api.get_kline_serial(symbol, 24 * 60 * 60, data_length=21 * 6)
    ticks = api.get_tick_serial(symbol, 60000)
    klines.loc[:,'datetime'] = klines.loc[:,'datetime'].map(Tao.convert_2_date)
    trade_date_lit = klines.loc[:,'datetime'].copy()
    klines.set_index("datetime",inplace=True)

    # print(ticks)
    # ticks 和 kLines 分开处理 送入神经网络更合理一点你
    factor_df = generate_x_factor(ticks,klines)
    # factor_df.apply(lambda x:)


    # convert to Return proleptic Gregorian ordinal for the year
    # factor_df.datetime.to_list()[1].date().toordinal()

    # x = [1,2,3]
    # y = [2,3,4]
    # plt.plot(x,y)
    # plt.show()

    # factor_df.head(100).plot(figsize=(20,10))
    # plt.show()


