use world;
/*
	  tag:成交列表记录
    createTime:2021/05/10
    author:jinntao
*/
drop table if exists `tradelist`;
CREATE TABLE `tradelist` (
  `trade_id` varchar(255) PRIMARY KEY comment '成交ID, 对于一个用户的所有成交，这个ID都是不重复的',
  `order_id` varchar(255) NOT NULL comment '订单iD, 对于一个用户的所有成交，这个ID都是不重复的',
  `exchange_trade_id` varchar(255) NOT NULL comment '交易所成交编号',
  `account` varchar(45) NOT NULL,
  `exchange_id` varchar(45) DEFAULT NULL,
  `inst` varchar(45) NOT NULL,
  `trade_date_time` datetime NOT NULL,
  `direction` varchar(45) NOT NULL,
  `offset` varchar(45) DEFAULT NULL,
  `vol` int NOT NULL,
  `price` decimal(10,0) NOT NULL,
  `is_deleted` int NOT NULL DEFAULT '0',
  `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- drop table if exists `stock_data`;
-- CREATE TABLE `stock_data` (
--   `id` int NOT NULL AUTO_INCREMENT,
--   `state_dt` date NOT NULL,
--   `stock_code` varchar(10) NOT NULL,
--   `open` decimal(10,2) DEFAULT NULL,
--   `high` decimal(10,2) DEFAULT NULL,
--   `low` decimal(10,2) DEFAULT NULL,
--   `close` decimal(10,2) DEFAULT NULL,
--   `pre_close` bigint DEFAULT NULL,
--   `change` decimal(20,2) DEFAULT NULL,
--   `pct_chg` decimal(10,2) DEFAULT NULL,
--   `vol` decimal(10,2) DEFAULT NULL,
--   `amount` decimal(10,2) DEFAULT NULL,
--   `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
--   `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
--   PRIMARY KEY (`id`),
--   UNIQUE KEY `idx_unique_stock_code_state_dt` (`stock_code`,`state_dt`),
--   KEY `idx_stock_code` (`stock_code`),
--   KEY `idx_state_dt` (`state_dt`)
-- ) ENGINE=InnoDB AUTO_INCREMENT=13729 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;



drop table if exists `security_basic_info`;
CREATE TABLE `security_basic_info` (  
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `code` VARCHAR(256) NOT NULL COMMENT "证券代码",   
  `raw_code` VARCHAR(256) NOT NULL COMMENT "原证券代码",       
  `code_name` VARCHAR(512) DEFAULT NULL COMMENT '证券名称',  
  `ipoDate` date DEFAULT  NULL  COMMENT '上市日期',       --   
  `outDate` date DEFAULT  NULL  COMMENT '退市日期', --   
  `type` INT NOT NULL COMMENT '证券类型，其中1：股票，2：指数，3：其它，4：可转债，5：ETF',  -- 
  `market` INT NOT NULL COMMENT '市场',  
  `status` INT NOT NULL COMMENT '上市状态，其中1：上市，0：退市',      --   
  `source` INT NOT NULL COMMENT '来源 ',                --   
  `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `idx_code_market` (`code`,`market`),
  INDEX idx_code (code), -- 为stock_code创建索引  
  INDEX idx_raw_code (raw_code)      -- 为state_dt创建索引  
)ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- # 日线指标参数（包含停牌证券）
drop table if exists `security_daily_frmbao`;
CREATE TABLE `security_daily_frmbao` (
  `date` date NOT NULL COMMENT '交易所行情日期',
  `code` varchar(128) NOT NULL COMMENT '证券代码，包含交易所前缀 格式：sh.600000。sh：上海，sz：深圳',
  `open` decimal(24,6) DEFAULT NULL COMMENT '精度：小数点后4位；单位：人民币元',
  `high` decimal(24,6) DEFAULT NULL COMMENT '精度：小数点后4位；单位：人民币元',
  `low` decimal(24,6) DEFAULT NULL COMMENT '精度：小数点后4位；单位：人民币元',
  `close` decimal(24,6) DEFAULT NULL COMMENT '精度：小数点后4位；单位：人民币元',
  `preclose` decimal(24,6) DEFAULT NULL COMMENT '精度：小数点后4位；单位：人民币元',
  `volume` bigint DEFAULT NULL COMMENT '成交数量 单位：股',
  `amount` decimal(24,6) DEFAULT NULL COMMENT '成交金额 精度：小数点后4位；单位：人民币元',
  `adjustflag` int DEFAULT NULL COMMENT '复权状态 	不复权、前复权、后复权',
  `turn` decimal(24,6) DEFAULT NULL COMMENT '换手率 	精度：小数点后6位；单位：%',
  `tradestatus` int DEFAULT NULL COMMENT '交易状态 1：正常交易 0：停牌',
  `pctChg` decimal(24,6) DEFAULT NULL COMMENT '涨跌幅百分比 精度：小数点后6位',
  `peTTM` decimal(24,6) DEFAULT NULL COMMENT '滚动市盈率 精度：小数点后6位',
  `psTTM` decimal(24,6) DEFAULT NULL COMMENT '滚动市销率 精度：小数点后6位',
  `pcfNcfTTM` decimal(24,6) DEFAULT NULL COMMENT '滚动市现率 精度：小数点后6位',
  `pbMRQ` decimal(24,6) DEFAULT NULL COMMENT '市净率 精度：小数点后6位',
  `isST` int DEFAULT NULL COMMENT '是否ST股',
  `remark` text COMMENT '备注',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`date`,`code`),
  INDEX `IDX_CODE` (`code`),
  INDEX `IDX_DATE` (`date`),
  INDEX `IDX_ISST` (`isST`)
) ENGINE=InnoDB AUTO_INCREMENT=1050037 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;






-- 交易所表 (Exchanges)
drop table if exists `Exchanges`;
CREATE TABLE `Exchanges` (  
  `exchange_id` INT AUTO_INCREMENT PRIMARY KEY,  
  `exchange_name` VARCHAR(255) NOT NULL,  
  `sname` VARCHAR(255) NOT NULL,  
  `country` VARCHAR(255) NOT NULL,  
  `timezone` VARCHAR(50) NOT NULL,  
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci; 
INSERT INTO `Exchanges`(`exchange_name`,`sname`,`country`,`timezone`) values('上海证券交易所','sh','china','Asia/Shanghai');
INSERT INTO `Exchanges`(`exchange_name`,`sname`,`country`,`timezone`) values('深圳证券交易所','sh','china','Asia/Shanghai');

-- 交易日历表 (TradingDays)
drop table if exists `TradingDays`;
CREATE TABLE `TradingDays` (  
  `exchange_id` INT,  
  `date` DATE NOT NULL,  
  `is_trading_day` BOOLEAN NOT NULL,  
  `remarks` TEXT, 
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`exchange_id`,`date`)
)ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci; 


-- # 个股日线基础因子数据表
drop table if exists `security_daily_factor`;
CREATE TABLE `security_daily_factor` (
  `date` date NOT NULL COMMENT '交易所行情日期',
  `code` varchar(128) NOT NULL COMMENT '证券代码，包含交易所前缀 格式：sh.600000。sh：上海，sz：深圳',
  `factor_name` varchar(256) NOT NULL COMMENT '因子名称', 
  `factor_id` varchar(256) NOT NULL COMMENT '因子id',
  `factor_value` double DEFAULT NULL COMMENT '因子值',
  `source` int DEFAULT NULL COMMENT '因子值基于什么行情源计算',
  `pool_size` int NOT NULL COMMENT '计算该因子时股票池子大小',
  `update_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `create_time` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  -- PRIMARY KEY (`date`,`code`,`factor_id`,`factor_name`,`pool_size`),
  INDEX `IDX_DATE` (`date`),
  INDEX `IDX_FACTOR_NAME` (`factor_name`),
  INDEX `IDX_FACTOR_ID` (`factor_id`),
  INDEX `IDX_CODE` (`code`)

) ENGINE=InnoDB AUTO_INCREMENT=1 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
PARTITION BY RANGE ( YEAR(date) * 12 + MONTH(date) ) (  
    PARTITION p202212 VALUES LESS THAN (2022 * 12 + 13),  
    PARTITION p202301 VALUES LESS THAN (2023 * 12 + 2),  
    PARTITION p202302 VALUES LESS THAN (2023 * 12 + 3),  
    PARTITION p202303 VALUES LESS THAN (2023 * 12 + 4),  
    PARTITION p202304 VALUES LESS THAN (2023 * 12 + 5),  
    PARTITION p202305 VALUES LESS THAN (2023 * 12 + 6),  
    PARTITION p202306 VALUES LESS THAN (2023 * 12 + 7),  
    PARTITION p202307 VALUES LESS THAN (2023 * 12 + 8),  
    PARTITION p202308 VALUES LESS THAN (2023 * 12 + 9),  
    PARTITION p202309 VALUES LESS THAN (2023 * 12 + 10),  
    PARTITION p202310 VALUES LESS THAN (2023 * 12 + 11),  
    PARTITION p202311 VALUES LESS THAN (2023 * 12 + 12),  
    PARTITION p202312 VALUES LESS THAN (2023 * 12 + 13),  
    PARTITION p202401 VALUES LESS THAN (2024 * 12 + 2),  
    PARTITION p202402 VALUES LESS THAN (2024 * 12 + 3),  
    PARTITION p202403 VALUES LESS THAN (2024 * 12 + 4),  
    PARTITION p202404 VALUES LESS THAN (2024 * 12 + 5),  
    -- 添加一个MAXVALUE分区，以捕获未来所有的数据  
    PARTITION pmax VALUES LESS THAN MAXVALUE  
);

====================================20240418 已上线