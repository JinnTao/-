# Schedule

####  2021-05-21 19:38:32

* json模式
    - 修改保存数据到一个json file中
    - 观察保存数据是否是持仓数据，如果是则直接用持仓数据进行 则省略了创建文件的难点

* mysql 模式

#### 订单管理

1. 把订单流管理用tqsdk做一遍，方便以后:
    - 根据当前持仓 生产订单list，记录报单id。
    - 依据报单顺序
    
#### 2021-05-23 23:07:08

1. 订单工厂，实现对报单控制，用海归策略模拟/实盘测试一下
    - 订单管理能用就好，还缺一个riskcontrol这个用tqsdk自带的
    -  成交ok，订单ok，风控：tqsdk，日志：tqsdk
    - 貌似还是应该用个成交定时器 crontab做一个？目前不做也可以
    - 假设测试成功的话，就直接上高频策略吧 别墨迹了
    
2. 风控，日志 2d

#### 2021-05-24 21:37:18

```
回访
ws://139.196.53.95:27961/t/rmd/front/mobile
回测
wss://otg-sim.shinnytech.com/trade 
仿真
wss://free-api.shinnytech.com/t/nfmd/front/mobile
downLoader:
2021-03-28 12:56:47 -     INFO - 通知: 与 wss://otg-sim.shinnytech.com/trade 的网络连接已建立
2021-03-28 12:56:47 -     INFO - 通知: 与 wss://free-api.shinnytech.com/t/nfmd/front/mobile 的网络连接已建立
```

####  2021-05-25 23:07:45 

1. 日志：用logging做好了，实盘和模拟盘分别存在不同目录下
    - bug:TimedRotatingFileHandler logging这个handle不生效 就比较晕
    - 用test.yml是可以成功的 难道按日切割应该用when:H？每天自动切割，原来不懂
    
2. 风控：受阻:测试账户没法设置风控规则
    - 用Timer每隔60s输出一边规则？
    - 用风控RC控制交易策略，如果发现出问题，则停止交易kill thread
    - 也就是用另一个风控脚本控制
    
---
** TODO: 深度学习之股指期货日内交易策略 复现 **
>> 纵使再努力，也应坦然接受不好的结果。


#### 2021-05-27 23:39:32

The below was Tensorflow Neural NetWorks training template,Below 
template can copy for most of deep learning , if you are under the TF.

```python
# !/usr/bin/env python
#  -*- coding: utf-8 -*-

import tensorflow as tf

# 初始化 batch大小
batch_size = 100
# 特征值
x = tf.placeholder(tf.float32,shape=(batch_size,2),name='x-input')
# 真实值
y_ = tf.placeholder(tf.float32,shape=(batch_size,1),name='y-input')

# define loss fun
loos = ... #tf.reduce_mean

# train
with tf.Session() as sess:
    # param init
    ...
    for i in range(STEPS):
        # prepare batch_size train data.random flutter data for better training result
        current_X, Current_Y = ...
        sess.run(train_step, feed_dict={x:current_X, y_:current_Y})

```

## 2023-08-15 轮回


    这次又开始做Quant了，这算是小时候的梦，可是总有无形的力量阻止我这么去做，或许是保护我？或许是我本不应该这样子？就像我脑子里想的和现实中去做的，差距总是很大。为什么我如今一致单身，为什么一直处在这种漩涡中？我不可得知，人生总是缺少某些力量，或者我本应该经历这一切？太多的问题了，时不时被各种欲望所拉扯，回过神又会感到后悔，但是如今这种后悔的感觉在衰退，或者说我已经逐渐感到能控制自己的身体和思想了。这是知行合一的说法吧？无论如何，这种力量在恢复，我感到有些开心。但是不能开心，应该保持这种状态。不是你选择了某事，而是某事选择了你；不是我选择了这命运，而是这命运选择了我？

## 2023-09-25

    总有写惊奇的相遇；
## 2023-10-03
    LDA - 线性判别分析 Linear Discriminant Analysis:
     对D维数据进行标准化处理
     对于每一类别，计算d维的均值向量
     构造类间的散步矩阵Sb以及类内的散步矩阵Sw
     计算矩阵Sw-Sb的特征值以及对应的构造向量
     选取前K个特征值对应的特征向量，构造一个dxK维的转换矩阵W,其中特征向量以列的形式排列
     使用转换矩阵W将羊背映射到新的特征子空间上

    Tag:散度矩阵 = 类内离散度矩阵 = 类内离差阵 = 协方差矩阵 x (n-1)

# 2024-03-09
免费的行情源：Tushare AKshare baostock Ashare Pytdx

    

