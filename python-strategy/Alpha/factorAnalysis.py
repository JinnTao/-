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

mysqlUtil = mysqlConfig.MysqlDataConn(Tao.MYSQL_HOST, Tao.MYSQL_ACC,
                                      Tao.MYSQL_PWD, Tao.MYSQL_DB, 3306)


def main():
    pass


if __name__ == "__main__":
    main()
