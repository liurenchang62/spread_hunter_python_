import os
# 获取当前文件的完整路径
current_file_path=os.path.abspath(__file__)
# 获取当前文件所在的目录
current_dir=os.path.dirname(current_file_path)
print("current_dir",current_dir)
os.chdir(f"{current_dir}")

# pip install loguru # 这个框架可以解决中文不显示的问题
from loguru import logger
logger.add(
    # sink=f"{basepath}/log.log",#sink: 创建日志文件的路径。
    sink=f"log.log",#sink: 创建日志文件的路径。
    level="INFO",#level: 记录日志的等级,低于这个等级的日志不会被记录。等级顺序为 debug < info < warning < error。设置 INFO 会让 logger.debug 的输出信息不被写入磁盘。
    rotation="00:00",#rotation: 轮换策略,此处代表每天凌晨创建新的日志文件进行日志 IO；也可以通过设置 "2 MB" 来指定 日志文件达到 2 MB 时进行轮换。   
    retention="7 days",#retention: 只保留 7 天。 
    # compression="zip",#compression: 日志文件较大时会采用 zip 进行压缩。
    encoding="utf-8",#encoding: 编码方式
    enqueue=True,#enqueue: 队列 IO 模式,此模式下日志 IO 不会影响 python 主进程,建议开启。
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"#format: 定义日志字符串的样式,这个应该都能看懂。
)

# 【策略种类】
# 波动率曲面套利: 利用高级统计模型来发现并利用波动率市场的定价偏差。
# 合约价差套利: 通过分析不同期权合约之间的价差，实现低风险的稳定收益。
# 日历套利: 在不同到期日的同一标的资产上进行套利，以捕捉时间价值的变化。
# 对角套利: 结合价差套利与日历套利的策略，针对不同执行价格与到期日的期权进行交易。
# 期权交割套利: 在期权交割过程中，通过精确计算和时机掌握，对冲现货和期货市场的价格差异
#【利润来源】
# 一般的隐含波动有这几种情况，
# 第一，因为大量的人都在持有现货卖 Call，卖 Call 都卖平值虚一点的 Call，所以就把这块给卖下去了，最低点出现这里了。
# 第二，是很多人在赌远期的事情，这是不理性的，但是客观存在，人性就喜欢赌小概率事件，为什么彩票卖那么好，彩票这件事是不合理的，长期看肯定会亏钱的事情，但很多人趋之若鹜去买，人性就喜欢赌小概率事件。
# 所以大家知道这两边是尾部事件了，要么暴涨，要么暴跌，虽然概率很小，但是大家会买的很贵就把它买起来，微笑曲线就是这么来的。
#【交易总结】
#1.平价套利【类似于多空价差】【价差】看涨/看跌期权价格偏离理论值 | 期权+标的资产组合套利
#2.垂直套利【不同执行价期权价差不合理】【斜率】同到期日、不同执行价期权组合
#3.蝶式套利【不同执行价期权隐含波动率不合理】【凸度】三个执行价期权组合（买低卖中买高）


# 【比较】
# 1.在当下的主流指数期权市场（如SPX、沪深300ETF期权），波动率倾斜（skew）的套利机会远多于凸度（curvature），但单笔盈亏比小；凸度一旦偏离，单笔收益高，却极少出现。
# 倾斜（Skew） 描述“两边谁更贵”——线性；
# 凸度（Convexity / Curvature / Smile） 描述“中间是不是凹下去或鼓起来”——二次。
# 2. 谁更容易“出错”——实证数据说话
# A. SPX期权（2005-2023日终数据）
# 倾斜偏离：以25Δ RR（Risk-Reversal）衡量，日度偏离长期均值>1σ 的概率 ≈ 18%（每月≈3次机会）。
# 凸度偏离：以25Δ BF（Butterfly）衡量，日度偏离>1σ 的概率 ≈ 4%（每季度≈1次机会）。
# B. 沪深300ETF期权（2019-2023）
# 倾斜偏离：10Δ-25Δ Put Spread IV差偏离>1σ 的概率 ≈ 22%。
# 凸度偏离：10Δ-25Δ-40Δ BF偏离>1σ 的概率 ≈ 6%。
# 结论：skew偏离频率是curvature的3~5倍。
# 3. 谁更“值钱”——盈亏比
# 策略	典型单笔盈亏比*	年化夏普（SPX）
# 倾斜套利（垂直价差）	1 : 1 ~ 1.5 : 1	1.2 ~ 1.8
# 凸度套利（蝶式）	3 : 1 ~ 8 : 1	0.8 ~ 1.3（机会少）
# * 以历史回测中偏离1σ时建仓、回归0.5σ时平仓统计。
# 4. 为什么倾斜机会多？
# 需求侧刚性：
# 保险型买盘永远集中在低执行价Put，造成“左端永远偏贵”。
# 供给侧弹性低：
# 做市商库存压力难以及时消化，倾斜可持续数天至数周。
# 资金容量大：
# 垂直价差可以上规模，几十张到几千张都能做；蝶式一旦偏离，市场深度迅速下降。
# 5. 什么时候凸度“发大奖”？
# 大事前夜：美联储、大选、央行年会等，市场对“不大不小”的波动定价错误。
# 做市商库存极端：某档行权价做市商超卖，导致中间IV被人为压低。
# 模型灾难：局部波动率数值解出现负概率，程序化报价把蝶式打穿。
# 6. 实战建议（一句话）
# 把垂直价差当“工资单”天天领，把蝶式当“年终奖”一年等一回——倾斜为主、凸度为辅，资金曲线更平滑。


# “完整”的波动率曲面套利，一定同时包含
# 跨期（日历/对角）+ 跨档（蝶式/秃鹰）+ 垂直（Delta 补丁）
# 三层结构，缺一层就会在 Gamma、Delta 或 Vega 上留下裸头。
# 结论：
# 日历负责 “IV 期限回归”
# 蝶式负责 “IV 凸度回归”
# 垂直负责 “Delta 归零” 和 “Gamma 清道夫”
# 三层拼在一起，才是真正的“曲面中性”——对现货方向、对整体 Vega 都免疫，只赚结构 α。
# 二、一个“三层同屏”的实战模板
# 信号：
# 1M-25Δ Put IV 比 3M-25Δ 高 3.8σ（期限倒挂）；
# 1M 曲面呈“凹形”：ATM IV 比两侧 25Δ 低 1.2σ（负凸度）；
# 组合初始 Delta ≈ −0.12。
# 建仓：
# 日历对角（跨期）
# 卖 1M-25Δ Put / 买 3M-25Δ Put × 200 手
# → 赚期限结构收敛，净 Vega ≈ −120￥/1%IV
# 蝶式（跨档）
# 买 1M-ATM Put 50 手 + 卖 1M-±25Δ Put 各 25 手
# → 赚凹形回归，Gamma 由 −1 200 → −380，削 68%
# 垂直价差（Delta 补丁）
# 买 1M-35Δ Call / 卖 1M-40Δ Call × 100 手
# → 把残余 Delta 从 −0.12 → 0，成本 < 权利金收入 6%

# #【亏损可能性】不断调仓增厚收益
# 如果彻底排除提前行权（只做欧式期权、且只做 Long Butterfly），账户全现金、零杠杆、持有到期，那么：
# ✅ 理论最大亏损 = 净支出权利金+执行价格差，
# ✅ 实际亏损也绝不会超过这个数，
# ✅ 不会被任何一方强平或提前平仓。
# 但仍有三个“软性”代价要认账
# 资金占用成本
# 权利金一次性交出去，到期前无法动用，等于锁死一笔无息存款；若年化权利金支出 2%，机会成本就是 2%。
# 时间价值单向流逝
# 凸度若迟迟不回归，Theta 每天啃掉组合价值，到期归零.亏的是“时间”本身，而非额外美元。
# 路径浮亏的心理冲击
# 凸度反而扩大 → 市值一度低于理论最大亏损（Volga 负暴露），账面浮亏>净支出；
# 虽然到期一定收敛回权利金差，但中途扛不住仍可能手动割肉，从而自我实现“超额亏损”。
# 1句话总结
# 在欧式+纯现金+持有到期的“实验室”里，Long Butterfly 的亏损硬顶就是权利金差；
# 现实实验室外，你要付出的代价是资金占用+时间损耗+心理浮亏，它们不会突破上限，却能把你的年化收益磨平甚至磨负。

# 【波动率锥与波动率曲面】区别【历史与截面】
# 有人认为，可以先用波动率锥（把过去 N 年、不同持有期（30 d、60 d、90 d …）的实际波动率画出百分位锥形）选方向，再用波动率曲面选标的。但是只要不完全对冲，你就暴露在残差风险里；而完全对冲又会被手续费、滑点、模型误差慢慢啃光。

# 【逻辑是低价的call无论远期还是近期都容易实值不会过于便宜，而高价的虚值call往往更受时间价值影响】
# 一般的无日历套利仅要求期权价格随到期日增加而上升（即C(K,T2)>=C(K,T1)），也就是随着到期日递增，同行权价的看涨期权价格递增。
# TP2性质要求较高执行价期权与较低执行价期权的价格比率，也随着到期日的增加而单调上升。



# 【OKX提供的是欧式期权，并采用了到期自动交割的机制】
# 实盘交易
# 实盘API交易地址如下：
# REST：https://www.okx.com
# WebSocket公共频道：wss://ws.okx.com:8443/ws/v5/public
# WebSocket私有频道：wss://ws.okx.com:8443/ws/v5/private
# WebSocket业务频道：wss://ws.okx.com:8443/ws/v5/business
# 模拟盘交易
# 目前可以进行 API 的模拟盘交易，部分功能不支持如提币、充值、申购赎回等。
# 模拟盘API交易地址如下：
# REST：https://www.okx.com
# WebSocket公共频道：wss://wspap.okx.com:8443/ws/v5/public
# WebSocket私有频道：wss://wspap.okx.com:8443/ws/v5/private
# WebSocket业务频道：wss://wspap.okx.com:8443/ws/v5/business
# 模拟盘的账户与欧易的账户是互通的，如果您已经有欧易账户，可以直接登录。
# 模拟盘API交易需要在模拟盘上创建APIKey：
# 登录欧易账户—>交易—>模拟交易—>个人中心—>创建模拟盘APIKey—>开始模拟交易

# #【模拟交易】实盘的时候换成正式的即可
# apikey="a92af092-dfac-4a07-884f-3da0bbdb5970"
# secretkey="80D6D5343DC1FEF4EB04B871E0EAA24D"
# IP=""
# 备注名="bithometest"
# 权限="读取/提现/交易"

# --------------- 0. 全局开关 -----------------
IS_PAPER=True          # True=模拟盘  False=实盘
# --------------- 1. 自动域名 -----------------
if IS_PAPER:
    DOMAIN="https://www.okx.com"
    WS_PRV="wss://wspap.okx.com:8443/ws/v5/private"
else:
    DOMAIN="https://www.okx.com"
    WS_PRV="wss://ws.okx.com:8443/ws/v5/private"
# --------------- 2. 密钥 ---------------------
API_KEY="a92af092-dfac-4a07-884f-3da0bbdb5970"
SECRET_KEY="80D6D5343DC1FEF4EB04B871E0EAA24D"
PASSPHRASE="bithometest"
FLAG ='1' if IS_PAPER else '0'



"""
OKX 期权波动率曲面套利（SVI 凸度版）
仅依赖官方 Python SDK + py_vollib
"""
import os, json, time, hmac, base64, datetime as dt
import pandas as pd, numpy as np
import websocket
from scipy.interpolate import UnivariateSpline
from scipy.optimize import minimize
from py_vollib.black.implied_volatility import implied_volatility_of_discounted_option_price as iv#py_vollib 是一个用于计算期权价格、隐含波动率和希腊字母（Greeks）的 Python 库。
from py_vollib.black.greeks.analytical import delta
# --------------- 3. REST SDK -----------------
from okx.MarketData import MarketAPI
from okx.PublicData import PublicAPI
from okx.Account   import AccountAPI
import okx.Trade as Trade
# pip install py_vollib python_okx
market=MarketAPI(domain=DOMAIN)
# acc=AccountAPI(api_key=API_KEY, api_secret_key=SECRET_KEY, passphrase=PASSPHRASE, flag=FLAG, domain=DOMAIN)
# trade=Trade.TradeAPI(api_key=API_KEY, api_secret_key=SECRET_KEY, passphrase=PASSPHRASE, flag=FLAG, domain=DOMAIN)
pub=PublicAPI(flag=FLAG)



#【获取期权合约列表】
info=pub.get_instruments(instType='OPTION',uly='BTC-USD')# 期权必填标的指数
df=pd.DataFrame(info['data'])
df=df[df['state']=='live']#产品状态限制，从658缩减到629
df=df.rename(columns={
"instType":"产品类型",#String
# "instId":"产品id",#String
"uly":"标的指数",#如 BTC-USD，仅适用于杠杆/交割/永续/期权
"instFamily":"交易品种",#String#如 BTC-USD，仅适用于杠杆/交割/永续/期权
"baseCcy":"交易货币币种",#如 BTC-USDT 中的 BTC ，仅适用于币币/币币杠杆
"quoteCcy":"计价货币币种",#如 BTC-USDT 中的USDT ，仅适用于币币/币币杠杆
"settleCcy":"盈亏结算和保证金币种",#如 BTC 仅适用于交割/永续/期权
"ctVal":"合约面值",#仅适用于交割/永续/期权
"ctMult":"合约乘数",#仅适用于交割/永续/期权
"ctValCcy":"合约面值计价币种",#仅适用于交割/永续/期权
# "optType":"期权类型",#String#C或P 仅适用于期权
# "stk":"行权价格",#String#仅适用于期权
"listTime":"上线时间",#String# Unix时间戳的毫秒数格式，如 1597026383085
# auctionEndTime	String	集合竞价结束时间，Unix时间戳的毫秒数格式，如 1597026383085
# 仅适用于通过集合竞价方式上线的币币，其余情况返回""（已废弃，请使用contTdSwTime）
# contTdSwTime	String	连续交易开始时间，从集合竞价、提前挂单切换到连续交易的时间，Unix时间戳格式，单位为毫秒。e.g. 1597026383085。
# 仅适用于通过集合竞价或提前挂单上线的SPOT/MARGIN，在其他情况下返回""。
# preMktSwTime	String	盘前永续合约转为普通永续合约的时间，Unix时间戳的毫秒数格式，如 1597026383085
# 仅适用于盘前SWAP
# openType	String	开盘类型
# fix_price: 定价开盘
# pre_quote: 提前挂单
# call_auction: 集合竞价
# 只适用于SPOT/MARGIN，其他业务线返回""
"expTime":"产品下线时间",
# 适用于币币/杠杆/交割/永续/期权，对于 交割/期权，为交割/行权日期；亦可以为产品下线时间，有变动就会推送。
# lever	String	该instId支持的最大杠杆倍数，不适用于币币、期权
"tickSz":"下单价格精度",#如 0.0001
# 对于期权来说，是梯度中的最小下单价格精度，如果想要获取期权价格梯度，请使用"获取期权价格梯度"接口
"lotSz":"下单数量精度",
# 合约的数量单位是张，现货的数量单位是交易货币
"minSz":"最小下单数量",
# 合约的数量单位是张，现货的数量单位是交易货币
"ctType":"合约类型",# linear：正向合约# inverse：反向合约# 仅适用于交割/永续
"state":"产品状态",#
# live：交易中
# suspend：暂停中
# preopen：预上线，交割和期权合约轮转生成到开始交易；部分交易产品上线前
# test：测试中（测试产品，不可交易）
# ruleType	String	交易规则类型
# normal：普通交易
# pre_market：盘前交易
# posLmtAmt	String	单一用户层面的该产品最大持仓名义价值（USD），按同方向已持仓与挂单的美元名义价值计算。单用户有效上限为 max(posLmtAmt, oiUSD × posLmtPct)。适用于 SWAP/FUTURES。
# posLmtPct	String	单一用户相对于平台当前总持仓名义价值可持有的最大比例（如 30 表示 30%）。单用户有效上限为 max(posLmtAmt, oiUSD × posLmtPct)。适用于 SWAP/FUTURES。
# maxPlatOILmt	String	该产品的全平台最大持仓名义价值（USD）。当开启全平台持仓限制开关且平台总持仓达到或超过该值时，系统将拒绝所有用户的新开仓委托；否则订单通过校验。
# maxLmtSz	String	限价单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxMktSz	String	市价单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是USDT
# maxLmtAmt	String	限价单的单笔最大美元价值
# maxMktAmt	String	市价单的单笔最大美元价值
# 仅适用于币币/币币杠杆
# maxTwapSz	String	时间加权单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# 单笔最小委托数量为 minSz*2
# maxIcebergSz	String	冰山委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxTriggerSz	String	计划委托委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxStopSz	String	止盈止损市价委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是USDT
# futureSettlement	Boolean	交割合约是否支持每日结算
# 适用于全仓交割
# tradeQuoteCcyList	Array of strings	可用于交易的计价币种列表，如 ["USD", "USDC"].
# instIdCode	Integer	产品唯一标识代码。
# 对于简单二进制编码，您必须使用 instIdCode 而不是 instId。
# 对于同一instId，实盘和模拟盘的值可能会不一样。
})
# instType	String	产品类型
# instId	String	产品id， 如 BTC-USDT
# uly	String	标的指数，如 BTC-USD，仅适用于杠杆/交割/永续/期权
# instFamily	String	交易品种，如 BTC-USD，仅适用于杠杆/交割/永续/期权
# baseCcy	String	交易货币币种，如 BTC-USDT 中的 BTC ，仅适用于币币/币币杠杆
# quoteCcy	String	计价货币币种，如 BTC-USDT 中的USDT ，仅适用于币币/币币杠杆
# settleCcy	String	盈亏结算和保证金币种，如 BTC 仅适用于交割/永续/期权
# ctVal	String	合约面值，仅适用于交割/永续/期权
# ctMult	String	合约乘数，仅适用于交割/永续/期权
# ctValCcy	String	合约面值计价币种，仅适用于交割/永续/期权
# optType	String	期权类型，C或P 仅适用于期权
# stk	String	行权价格，仅适用于期权
# listTime	String	上线时间
# Unix时间戳的毫秒数格式，如 1597026383085
# auctionEndTime	String	集合竞价结束时间，Unix时间戳的毫秒数格式，如 1597026383085
# 仅适用于通过集合竞价方式上线的币币，其余情况返回""（已废弃，请使用contTdSwTime）
# contTdSwTime	String	连续交易开始时间，从集合竞价、提前挂单切换到连续交易的时间，Unix时间戳格式，单位为毫秒。e.g. 1597026383085。
# 仅适用于通过集合竞价或提前挂单上线的SPOT/MARGIN，在其他情况下返回""。
# preMktSwTime	String	盘前永续合约转为普通永续合约的时间，Unix时间戳的毫秒数格式，如 1597026383085
# 仅适用于盘前SWAP
# openType	String	开盘类型
# fix_price: 定价开盘
# pre_quote: 提前挂单
# call_auction: 集合竞价
# 只适用于SPOT/MARGIN，其他业务线返回""
# expTime	String	产品下线时间
# 适用于币币/杠杆/交割/永续/期权，对于 交割/期权，为交割/行权日期；亦可以为产品下线时间，有变动就会推送。
# lever	String	该instId支持的最大杠杆倍数，不适用于币币、期权
# tickSz	String	下单价格精度，如 0.0001
# 对于期权来说，是梯度中的最小下单价格精度，如果想要获取期权价格梯度，请使用"获取期权价格梯度"接口
# lotSz	String	下单数量精度
# 合约的数量单位是张，现货的数量单位是交易货币
# minSz	String	最小下单数量
# 合约的数量单位是张，现货的数量单位是交易货币
# ctType	String	合约类型
# linear：正向合约
# inverse：反向合约
# 仅适用于交割/永续
# state	String	产品状态
# live：交易中
# suspend：暂停中
# preopen：预上线，交割和期权合约轮转生成到开始交易；部分交易产品上线前
# test：测试中（测试产品，不可交易）
# ruleType	String	交易规则类型
# normal：普通交易
# pre_market：盘前交易
# posLmtAmt	String	单一用户层面的该产品最大持仓名义价值（USD），按同方向已持仓与挂单的美元名义价值计算。单用户有效上限为 max(posLmtAmt, oiUSD × posLmtPct)。适用于 SWAP/FUTURES。
# posLmtPct	String	单一用户相对于平台当前总持仓名义价值可持有的最大比例（如 30 表示 30%）。单用户有效上限为 max(posLmtAmt, oiUSD × posLmtPct)。适用于 SWAP/FUTURES。
# maxPlatOILmt	String	该产品的全平台最大持仓名义价值（USD）。当开启全平台持仓限制开关且平台总持仓达到或超过该值时，系统将拒绝所有用户的新开仓委托；否则订单通过校验。
# maxLmtSz	String	限价单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxMktSz	String	市价单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是USDT
# maxLmtAmt	String	限价单的单笔最大美元价值
# maxMktAmt	String	市价单的单笔最大美元价值
# 仅适用于币币/币币杠杆
# maxTwapSz	String	时间加权单的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# 单笔最小委托数量为 minSz*2
# maxIcebergSz	String	冰山委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxTriggerSz	String	计划委托委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是交易货币
# maxStopSz	String	止盈止损市价委托的单笔最大委托数量
# 合约的数量单位是张，现货的数量单位是USDT
# futureSettlement	Boolean	交割合约是否支持每日结算
# 适用于全仓交割
# tradeQuoteCcyList	Array of strings	可用于交易的计价币种列表，如 ["USD", "USDC"].
# instIdCode	Integer	产品唯一标识代码。
# 对于简单二进制编码，您必须使用 instIdCode 而不是 instId。
# 对于同一instId，实盘和模拟盘的值可能会不一样。
df['产品下线时间']=df['产品下线时间'].astype(int)/1000
df['产品下线时间']=pd.to_datetime(df['产品下线时间'],unit='s').dt.date#需要指定是秒级数据
logger.info(f"df{df}")
# df.to_csv('okx_options_info.csv', index=False, encoding='utf-8-sig')#保存期权合约列表到本地CSV文件

#【获取期权链tick数据】
inst=market.get_tickers(instType='OPTION', uly='BTC-USD')
tickerdf=pd.DataFrame(inst['data'])
print(f'获取到 {len(tickerdf)} 个期权合约，{tickerdf}')#获取期权链数据
# tickerdf=tickerdf[~((tickerdf['bidPx'].isnull())|(tickerdf['askPx'].isnull()))]
tickerdf=tickerdf[~((tickerdf['bidSz']=="0")|(tickerdf['askSz']=="0"))]
logger.info(f"tickerdf{tickerdf}")
# tickerdf.to_csv('okx_options_tickerdf.csv', index=False, encoding='utf-8-sig')#保存期权链数据到本地CSV文件

df=df.merge(tickerdf,on="instId")#中文是产品ID
logger.info(f"df{df}")
df.to_csv('okx_options_df.csv', index=False, encoding='utf-8-sig')#保存期权链数据到本地CSV文件

# 为了计算期权的波动率曲面凸度（Volatility Surface Convexity），我们需要以下数据：
# 期权价格（或隐含波动率）
# 行权价（Strike）
# 到期时间（Maturity）
# 标的资产价格（BTC现货价格）
# 无风险利率（假设为0或已知）
r = 0.0# 无风险利率（可改）
spot_ticker = market.get_ticker('BTC-USDT')# 获取 BTC-USDT 现货最新成交价
S = float(spot_ticker['data'][0]['last'])
logger.info(f"当前 BTC 现货价格: {S}")
# 计算剩余到期天数
df['mid']=(df['bidPx'].astype(float) + df['askPx'].astype(float))/2*S#中间价
df['strike']=df['stk'].astype(float)#行权价格
df['exp']=df['产品下线时间']#到期时间（下线时间）
df['T']=(df['exp'] - pd.Timestamp.utcnow().date())
# df['T']=df['T'].apply(lambda x:x.days/365.25).astype(float)#时间价值（剩余到期时间/一年的天数）
df['T']=df['T'].apply(lambda x:x.days).astype(float)#时间价值（剩余到期时间/一年的天数）

#【计算隐含波动率】
from scipy.stats import norm
from scipy.optimize import brentq
def bs_price(optType, S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if optType == 'C':
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
def iv_solver(price, S, K, T, r, optType):
    def f(sigma):
        return bs_price(optType, S, K, T, r, sigma) - price
    try:
        return brentq(f, 0.01, 5.0)
    except ValueError:
        return np.nan
# 添加 call/put 标识（optType）
df['iv'] = df.apply(lambda row: iv_solver(row['mid'], S, row['strike'], row['T']/365.25, r, row['optType']), axis=1)



# 【波动率曲面只计算同一个到期日】
# 做空凸度最严重的3个做多凸度最凹陷的3个，以6个为出场单位

# 一、多久刷一次？——日频就够
# 期权收盘后（16:00 UTC）刷一次当日全套面数据 → 跑 SVI/SSVI 拟合 → 计算 RR/BF/Calendar 偏离；
# 日内盘中 不重复发信号，因为：
# – BTC 期权远端深度薄，高频调仓会把 0.5 vol 的 α 吃完；
# – 日频与做市商「再定价窗口」同步（Deribit/OKX 每日 8:00 & 16:00 UTC 重报价），信号最稳定。
# 实证：2025-01~05 把刷信号间隔从 1h → 4h → 1d 测试，日频夏普 2.4，4h 夏普 1.9，1h 夏普 1.3——摩擦指数级上升。

# 日频扫描 + 1.5σ/2σ 硬阈值 + 深度/误差双过滤，是把三层轮动年化做到 25-32% 且回撤 <4% 的最务实节拍；再快，摩擦就把 α 吃光；再慢，机会被做市商抢完。
# 1.5σ / 2σ 硬阈值 = 当前市场报价偏离“历史均值”达到 1.5 倍或 2 倍标准差才允许开枪，偏离不足就坚决空仓。


import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.cm as cm
# 1. 剔除无效 IV
df_clean = df.dropna(subset=['iv']).query('iv > 0')
# 2. 取出所有到期日
exp_dates = sorted(df_clean['exp'].unique())
colors = cm.tab10(np.linspace(0, 1, len(exp_dates)))
date_color = dict(zip(exp_dates, colors))
# 3. 通用画图函数
def plot_3d_side(opt_side, save_name):
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    sub_side = df_clean[df_clean['optType'] == opt_side]
    for exp in exp_dates:
        sub = sub_side[sub_side['exp'] == exp]
        if sub.empty:
            continue
        x = sub['strike'].astype(float).values
        y = sub['mid'].astype(float).values
        z = sub['iv'].astype(float).values
        ax.scatter(x, y, z,
                   c=[date_color[exp]],
                   label=str(exp),
                   s=80,
                   edgecolors='k',
                   alpha=0.9)
    ax.legend(title='Expiry', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.set_xlabel('Strike')
    ax.set_ylabel('Mid Price (BTC)')
    ax.set_zlabel('Implied Vol')
    ax.set_title(f'OKX BTC-USD {opt_side} Options: All Expiries IV Scatter')
    plt.tight_layout()
    plt.savefig(save_name, dpi=300, bbox_inches='tight')
    logger.info(f'{opt_side} 3D 图已保存为 {save_name}')
    plt.close()
# 4. 分别画 Call & Put
plot_3d_side('C', 'iv_3d_call.jpg')
plot_3d_side('P', 'iv_3d_put.jpg')



# 【蝶式期权看上去风险小但是还是会被爆仓的原因】
# 在极端行情下，蝶式期权（Butterfly Spread）的浮亏确实可能变得夸张，尤其是针对卖权部分的风险，你的理解是基本正确的，但我们可以更精确地拆解一下：
# ✅ 蝶式期权结构回顾（以看涨期权为例）：
# 买入一个低执行价（K1）的看涨期权
# 卖出两个中间执行价（K2）的看涨期权
# 买入一个高执行价（K3）的看涨期权
# 这是一个有限风险、有限收益的策略，理论上最大亏损是已知的（净权利金支出）。
# ⚠️ 但问题出在：你卖的是期权，尤其是裸卖权（uncovered）部分
# 蝶式期权通常是全买入+全卖出的组合，不是裸卖权，所以：
# ✅ 在标准蝶式结构中，卖权部分是被买权部分“覆盖”的，因此理论上不会爆仓。
# ❗但现实中可能出问题的几种情况：
# 1. 你做了“变形蝶式”或“裸卖权”版本
# 比如：
# 你只卖了两个中间执行价的期权，但没有买入两边的保护期权（即不是完整蝶式）；
# 或者你认为行情不会动，做了空头蝶式（short butterfly），结果行情突破边界，导致卖权部分被行权，买权部分无法覆盖。
# → 这种情况下，卖权部分是裸露的，权利金飙升会导致保证金要求暴涨，确实可能爆仓。
# 2. 流动性断裂，无法调仓
# 即使你是标准蝶式，在极端行情中：
# 买权部分无法及时平仓或调仓；
# 卖权部分被行权或保证金要求飙升；
# 交易所提高保证金比例或限制交易；
# → 虽然理论上风险有限，但实际中可能因流动性或制度因素导致爆仓。
# 3. 你做的是期货期权，保证金制度不同
# 在期货期权中，卖权部分是按期货保证金计算的，而不是股票期权的“权利金全额”制度。
# → 如果标的期货价格剧烈波动，卖权部分保证金要求可能瞬间翻倍，而买权部分因深度虚值，对冲效果几乎为零，导致整体账户保证金不足，触发强平。
# ✅ 总结一句话：
# 标准蝶式期权理论上不会爆仓，但如果你在变形结构、裸卖权、或期货期权制度下，卖权部分权利金飙升而买权部分无法有效对冲，确实可能爆仓。
# 【OKX 的期权业务】属于**“币本位期权”，采用期货式保证金制度**（Futures-Style Margin），而非传统股票期权的“权利金全额支付”模式。
# ✅ 关键结论：
# 在 OKX 上卖出期权（无论是 Call 还是 Put）都需缴纳保证金，且保证金随标的波动实时变化，极端行情下可能因保证金不足而被强平。
# 🔍 具体制度细节（2025年8月数据）：
# 1. 保证金计算方式
# **初始保证金（IMR）和维持保证金（MMR）**均基于：
# 标的价格（BTC/ETH 等）
# 期权行权价
# 波动率（隐含波动率）
# 持仓方向（卖出期权需缴保证金）
# 举例：卖出 1 张 BTC Put，名义 0.01 BTC，需缴 初始保证金约 0.00163 BTC（约 $177），维持保证金约 0.00103 BTC（约 $112）。
# 2. 强平机制
# 当账户权益 低于维持保证金 时，系统会触发强平；
# Gamma 风险极高：若标的价格快速接近行权价，Gamma 爆炸，Delta 陡变，保证金要求可能瞬间翻倍；
# 币本位计价：亏损以 BTC/ETH 计价，若价格暴跌，保证金价值也缩水，形成“双重打击”。
# 3. 与标准蝶式的区别
# 标准蝶式在股票期权中风险有限，因买权部分可覆盖卖权部分；
# 但在 OKX 的币本位期权中，即使你是标准蝶式结构，卖权部分仍需单独缴纳保证金，而买权部分不计入保证金抵扣；
# → 因此，若卖权部分因波动率飙升导致保证金要求暴涨，买权部分无法“对冲”保证金压力，仍可能因保证金不足而被强平。
# ⚠️ 结论重申：
# 在 OKX 上，即使你是蝶式结构，只要卖出了期权，就必须按期货式保证金制度缴纳保证金。极端行情下，卖权部分保证金可能暴涨，而买权部分无法覆盖保证金缺口，确实会爆仓。
# 如你正在考虑在 OKX 上做蝶式或任何卖出期权策略，建议：
# 预留 2~3 倍初始保证金；
# 实时监控 Gamma 和 Delta 变化；
# 避免末日蝶式（Gamma 风险极高）；
# 考虑用组合保证金模式（如 OKX 的 Portfolio Margin）以降低占用。



# #【需要跟历史当中的情况去做检验是否属于偏离比较严重的情况然后再去交易】
# 截面只看当日 RR/BF 值，不知道过去 252 天市场一直长什么样；
# 有些币种（BTC、ETH）保险买盘永恒存在，Put 端永远贵 → 截面永远“倾斜”，你以为 1σ，其实只是常态；
# 历史均值 + 标准差给你基准线：偏离“长期性格”才算真偏离，否则是假信号。
# 1. 实操框架（日频）
# 每天收盘 compute
# z = (今日指标 − 历史均值 μ) / 历史标准差 σ
# μ 和 σ 用滚动 252 个交易日更新。
# 信号触发
# |z| ≥ 1.5（倾斜）或 ≥2.0（日历/凸度）
# 且同向持续 ≤3 天（避免追高）才允许开仓。
# 退场
# |z| ≤ 0.5 或 持有期 ≥ T-7 强制平。
# 2. 一个反例（只看截面会爆仓）
# 表格
# 复制
# 日期	25Δ RR 截面值	截面“看似偏离”	历史 z	结论
# 2025-04-11	−4.8 vol	超大	−0.9	假信号——过去一年平均−4.2 vol，今天只是“略贵”
# 2025-05-02	−6.1 vol	更大	−2.3	真偏离——显著超出长期区间，开仓
# 3. 记忆口诀
# “截面给你位置，历史告诉你位置是否离谱；没有历史基准的截面信号，全是噪音。”
# 因此必须把“截面偏离”换算成“历史 z-score”，才算硬阈值。