# -*- coding:utf-8 -*-
# -*- coding: utf-8 -*-
#
#author: Jinntao
#描述: A brief description of the file.
#
#
import sys

sys.path.append("D:\quant\promise\python-strategy")
from Common import Tao
from Common import AllEnum
from Common import mysqlConfig
import numpy as np
import pandas as pd
import pymysql
import matplotlib as mpl
import matplotlib.pyplot as plt
import jqdatasdk as jq
# import jqfactor_analyzer as jqf
from alpha191 import alpha191 as a191
import datetime as dt
import tqdm

mysqlUtil = mysqlConfig.MysqlDataConn(Tao.MYSQL_HOST, Tao.MYSQL_ACC,
                                      Tao.MYSQL_PWD, Tao.MYSQL_DB, 3306)

g_stock_pool_size = 0


def prepare_date(st_dt, ed_dt):
    # 票池不同 factorValue也不一样
    df = mysqlUtil.execute(
        f"SELECT raw_code FROM world.security_basic_info where type = {AllEnum.secType.STOCK.value} and status = {AllEnum.securityStatus.ON.value} ;"
    )
    data = pd.DataFrame()
    global g_stock_pool_size
    for row in tqdm.tqdm(df.itertuples()):
        g_stock_pool_size += 1
        data = pd.concat([data, get_hist_by_code(row.raw_code, ed_dt, st_dt)])

    # 创建一个空字典来存储结果
    result_dict = {}
    data.dropna(how='all', inplace=True)  # 暂时不知道为什么会出现空数据
    # 遍历除了'code'和'index'之外的每一列
    for col in data.columns[1:]:  # 假设'code'和'date'分别是第一列和第二列
        # 创建一个新的DataFrame，以'code'为列，'index'（日期）为行
        new_df = data.pivot(columns='code', values=col)
        # 将新的DataFrame添加到字典中，键为当前列名
        result_dict[col] = new_df

    return result_dict


def get_hist_by_code(code: str, ed_date, st_date) -> pd.DataFrame:
    """
        Dict<key, pd.DataFrame> The key includes the required data, such as close, open, high, low, volume, etc.

        The key's value is a wide table dataframe, where columns are stocks, rows are dates. (Faster than some groupby methods.)
    """
    # 构建基础日历Index
    connection = pymysql.connect(host=Tao.MYSQL_HOST,
                                 user=Tao.MYSQL_ACC,
                                 passwd=Tao.MYSQL_PWD,
                                 db=Tao.MYSQL_DB,
                                 charset='utf8')

    # 获取标准的交易日历
    with connection.cursor() as cursor:

        sql = f"SELECT * FROM world.tradingdays where date > '{st_date}' order by date desc;"
        # sql = f"SELECT * FROM security_daily_frmbao where code = '{code}' and date < '{ed_date}' and date > '{st_date}'"
        cursor.execute(sql)  # 参数化查询，防止SQL注入

        # 获取所有记录列表
        results = cursor.fetchall()
        tradingDayDF = pd.DatetimeIndex([day[1] for day in results])

    # 执行SQL查询语句
    try:
        with connection.cursor() as cursor:

            sql = f"SELECT date,code,open,high,low,close,volume,amount,turn FROM security_daily_frmbao where date > '{st_date}' and code  = '{code}'"
            # sql = f"SELECT * FROM security_daily_frmbao where code = '{code}' and date < '{ed_date}' and date > '{st_date}'"
            cursor.execute(sql)  # 参数化查询，防止SQL注入

            # 获取所有记录列表
            results = cursor.fetchall()

    except Exception as e:
        print(f"Error:{e}")
    finally:
        connection.close()  # 关闭数据库连接
    # 构造
    df = pd.DataFrame(results, columns=[col[0] for col in cursor.description])
    df.set_index('date', inplace=True)
    # 重置索引
    df = df.reindex(tradingDayDF)
    rows_all_nan = df.isnull().all(axis=1)
    if rows_all_nan.any():
        df_all_nan = df[rows_all_nan]
        # print(code, df_all_nan.index.values)
    # 补全
    df.fillna(method='ffill', inplace=True)
    # 转换
    cols2Convert = ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn']
    df[cols2Convert] = df[cols2Convert].astype(float)
    # df.reset_index(inplace=True)
    return df


def get_factor_value(save):
    alphaName = "AlphaName"
    alphaDesc = "GTJA_Alpha199"
    alpha191 = a191.Alpha191(alphaName, alphaDesc)
    ed_dt = dt.datetime.now().date()
    st_dt = ed_dt - dt.timedelta(days=600)
    df = prepare_date(st_dt, ed_dt)
    alpha191.init(df, 10, False, 1, 191, True)
    alphaValues = alpha191.cal()
    if save:
        alpha191ToDb(alphaValues)


def alpha191ToDb(alphaValues):
    global g_stock_pool_size
    for alphaName, alphaDf in tqdm.tqdm(alphaValues.items()):
        try:
            # query = """
            #     INSERT INTO security_daily_factor(date,code,factor_name,factor_id,factor_value,base_on)
            #     VALUES (%s,%s,%s,%s,%s,%s)
            #     ON DUPLICATE KEY UPDATE
            #     date = VALUES(date),
            #     code = VALUES(code),
            #     factor_name = VALUES(factor_name),
            #     factor_id = VALUES(factor_id),
            #     factor_value = VALUES(factor_value),
            #     base_on = VALUES(base_on)
            #     """
            query = """
                INSERT INTO security_daily_factor(date,code,factor_name,factor_id,factor_value,source,pool_size)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """
            # 初始化参数列表
            insertDf = alphaDf.dropna(how='all', axis=0)
            args = []
            insertDf = insertDf.fillna(np.nan)
            for factorDate, row in insertDf.iterrows():
                for code, factorValue in row.items():
                    factorDateIn = factorDate
                    codeIn = code
                    factorName = "GTJA_ALPHA191"
                    factorId = alphaName
                    factorValueIn = factorValue
                    if np.isnan(factorValueIn):
                        factorValueIn = None
                    source = AllEnum.DataSource.BaoStock.value  # BaoStock
                    pool_size = g_stock_pool_size
                    args.append((factorDateIn, codeIn, factorName, factorId,
                                 factorValueIn, source, pool_size))

            mysqlUtil.executemany(query, args)
        except Exception as e:
            print(e)


def main():
    get_factor_value(True)


if __name__ == '__main__':
    # index = jq.get_all_securities() rror:inf can not be used with MySQL
    main()
