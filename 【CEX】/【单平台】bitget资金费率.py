# #【八小时结算资金费率的是0，8，16】执行恰好是0，8，16点20分或者30分钟左右执行错开结算时间，除了bitget以外gate的资金费率利润也挺高，基本上二线交易所的资金费率还没那么卷
import pandas as pd
import datetime
import math
# pip install python-bitget
# 【参考文档】https://bitgetlimited.github.io/apidoc/en/mix/#get-account-list
from pybitget import Client
from pybitget.utils import *
from pybitget.enums import *
from pybitget import logger

logger.add(
    sink=f"log.log",#sink:创建日志文件的路径。
    level="INFO",#level:记录日志的等级,低于这个等级的日志不会被记录。等级顺序为 debug < info < warning < error。设置 INFO 会让 logger.debug 的输出信息不被写入磁盘。
    rotation="00:00",#rotation:轮换策略,此处代表每天凌晨创建新的日志文件进行日志 IO；也可以通过设置 "2 MB" 来指定 日志文件达到 2 MB 时进行轮换。   
    retention="7 days",#retention:只保留 7 天。 
    encoding="utf-8",#encoding:编码方式
    enqueue=True,#enqueue:队列 IO 模式,此模式下日志 IO 不会影响 python 主进程,建议开启。
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"#format:定义日志字符串的样式,这个应该都能看懂。
)

#【bitget理财大概一个小时一结算利息】
# 配置您的Bitget API密钥和密码短语
api_key="bg_5e69f9e32e87c9bb8087f97cc6adb910"
api_secret='b0682a6e4a0e0c50493a4be19b4f56de4fa81f07d6e7d010a71e1971a7c3bbb4'#默认HMAC方式解码
api_passphrase="wthWTH00"
client=Client(api_key,api_secret,passphrase=api_passphrase)

#【获取现货账户余额】
def getspotbalance(coin):
    request_path="/api/v2/spot/account/assets"
    params={"coin":coin}
    res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
    # logger.info(f"res,{type(res)},{res}")
    return res
# spotbalance=getspotbalance(coin="USDT")
# usdtbalance=[balance for balance in spotbalance if balance["coin"]=="USDT"][0]["available"]
# logger.info(f"usdtbalance,{usdtbalance},{type(usdtbalance)}")

#【获取理财产品列表】这里只要活期存款
def getsavingslist(coin):#10次/1s (Uid)
    request_path="/api/v2/earn/savings/product"
    params={"filter":"all",#筛选条件是否可申购
            # available: 可申购的
            # held: 持有中
            # available_and_held: 申购和持有中
            # all: 查询全部 包含下架的
            "coin":coin#需要查询的代币
            }
    res=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
    res=[r for r in res if r["periodType"]=="flexible"]#只要活期存款
    # logger.info(f"res,{type(res)},{res}")
    return res
# savingslist=getsavingslist(coin="USDT")#10次/1s (Uid)
# logger.info(f"savingslist,{savingslist},{type(savingslist)}")
# usdtproductId=str(savingslist[0]["productId"])#取出来产品ID
# logger.info(f"usdtproductId,{usdtproductId},{type(usdtproductId)}")



#【注意事项】
#1.资金费率有个可能是挂单在资金结算完才成交，所以需要提前停止下单【比如3秒超时自动撤单就提前4秒停止下单】，避免成交较晚
#2.可以尝试直接做合约的盘口价差套利，就是提供流动性的策略

droplist=[]#仓位过重不再执行开仓的标的
holdnum=3#【持仓数量】选择需要交易标的的总数量
trademoneyholdrate=holdnum*4#【最大持仓倍数】{持仓数量*4.如果单标的仓位等于总资产的话则总仓位是4倍的总资产}单个交易对的持仓金额超过trademoneyrate*trademoney后就不再执行交易
traderate=1/2#【单次下单倍数】单笔下单金额的最大倍数原则上小于总资产*杠杆倍数，实际希望干脆小于总资产，也就是这个倍数小于1


thisproductType="USDT-FUTURES"#【实盘】
absrate=0.003#【实盘】
# thisproductType="SUSDT-FUTURES"#【模拟盘】
# absrate=-10#【模拟盘】之前这个值为0的时候容易遇到盘口价差过大导致默认不执行交易的问题


# #【设置保证金模式】逐仓还是全仓{下单的时候可以单独指定，无需在这里设置}
# request_path="/api/v2/mix/account/set-margin-mode"
# params={
#     "symbol":"",
#     "assetMode":"crossed",保证金模式、isolated: 逐仓模式、crossed: 全仓模式
#     "productType":thisproductType,
#     #【productType参数说明】
#     # USDT-FUTURES USDT专业合约
#     # COIN-FUTURES 混合合约
#     # USDC-FUTURES USDC专业合约
#     # SUSDT-FUTURES USDT专业合约模拟盘
#     # SCOIN-FUTURES 混合合约模拟盘
#     # SUSDC-FUTURES USDC专业合约模拟盘
#     }
# res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
# logger.info(f"修改逐仓全仓模式,{res},{len(res)}")

#【设置U本位合约联合保证金模式】单币种保证金还是多币种联合保证金
request_path="/api/v2/mix/account/set-asset-mode"
params={
    "assetMode":"union",#保证金模式、single 单币种保证金模式、union 多币种联合保证金模式
    # "assetMode":"single",#保证金模式、single 单币种保证金模式、union 多币种联合保证金模式
    "productType":thisproductType,
    #【productType参数说明】
    # USDT-FUTURES USDT专业合约
    # COIN-FUTURES 混合合约
    # USDC-FUTURES USDC专业合约
    # SUSDT-FUTURES USDT专业合约模拟盘
    # SCOIN-FUTURES 混合合约模拟盘
    # SUSDC-FUTURES USDC专业合约模拟盘
    }
res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
logger.info(f"修改单币种保证金多币种保证金模式,{res},{len(res)}")

# #【设置单双向持仓模式】单向持仓还是双向持仓{需要空仓时才能调整}
# request_path="/api/v2/mix/account/set-position-mode"
# params={
#     "assetMode":"one_way_mode",#保证金模式、one_way_mode 单向持仓、hedge_mode 双向持仓
#     "productType":thisproductType,
#     #【productType参数说明】
#     # USDT-FUTURES USDT专业合约
#     # COIN-FUTURES 混合合约
#     # USDC-FUTURES USDC专业合约
#     # SUSDT-FUTURES USDT专业合约模拟盘
#     # SCOIN-FUTURES 混合合约模拟盘
#     # SUSDC-FUTURES USDC专业合约模拟盘
#     }
# res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
# logger.info(f"修改单双向持仓模式,{res},{len(res)}")

# #【一键平仓】可以个别交易对，可以全部交易对{如果不纠结是taker还是maker的话这个函数可以极为方便的执行清仓计划}
# request_path="/api/v2/mix/order/close-positions"
# params={
#     # "symbol":"",#可选择具体交易对
#     # "holdSide":"long",#持仓方向，long：多仓 ，short：空仓。1.买卖（单向持仓）模式下：可不填，若填则忽略。2.开平仓模式（双向持仓）下： 若不传，则平全部方向；若传，则平指定方向。
#     "productType":thisproductType,
#     #【productType参数说明】
#     # USDT-FUTURES USDT专业合约
#     # COIN-FUTURES 混合合约
#     # USDC-FUTURES USDC专业合约
#     # SUSDT-FUTURES USDT专业合约模拟盘
#     # SCOIN-FUTURES 混合合约模拟盘
#     # SUSDC-FUTURES USDC专业合约模拟盘
#     }
# res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
# logger.info(f"全部持仓执行平仓,{res},{len(res)}")

#【获取合约详情】
request_path="/api/v2/mix/market/contracts"
params={
    "symbol":"",
    "productType":thisproductType,
    #【productType参数说明】
    # USDT-FUTURES USDT专业合约
    # COIN-FUTURES 混合合约
    # USDC-FUTURES USDC专业合约
    # SUSDT-FUTURES USDT专业合约模拟盘
    # SCOIN-FUTURES 混合合约模拟盘
    # SUSDC-FUTURES USDC专业合约模拟盘
    }
bitget_mix_info=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
logger.info(f"bitget_mix_info所有合约交易对信息,{bitget_mix_info},{len(bitget_mix_info)}")
bitget_mix_info=pd.DataFrame(bitget_mix_info)
bitget_mix_info=bitget_mix_info[(bitget_mix_info["offTime"]=="-1"#下架时间为-1才正常可以执行交易
        )&(bitget_mix_info["limitOpenTime"]=='-1'#可开仓时间为-1才正常可以执行交易
        )&(bitget_mix_info["symbolStatus"]=='normal'#交易对状态【正常】
        )
        ]
bitget_mix_info=bitget_mix_info.rename(columns={
    "baseCoin":"基础币",#String
    "quoteCoin":"计价币",#String
    "buyLimitPriceRatio":"买价限价比例",
    "sellLimitPriceRatio":"卖价限价比例",
    "feeRateUpRatio":"手续费上浮比例",
    "makerFeeRate":"market手续费率",
    "takerFeeRate":"taker手续费率",
    "openCostUpRatio":"开仓成本上浮比例",
    "supportMarginCoins":"支持保证金币种",#	List<String>	
    "minTradeNum":"最小开单数量",#(基础币)
    "priceEndStep":"价格步长",
    "volumePlace":"数量小数位",
    "pricePlace":"价格小数位",
    "sizeMultiplier":"数量乘数",# 下单数量要大于 minTradeNum 并且满足 sizeMulti 的倍数
    "symbolType":"合约类型",#perpetual 永续,delivery交割
    "minTradeUSDT":"最小USDT交易额",
    "maxSymbolOrderNum":"最大持有订单数",#（symbol维度）
    "maxProductOrderNum":"最大持有订单数",#（产品类型维度）
    "maxPositionNum":"最大持有仓位数量",
    "symbolStatus":"交易对状态",#listed 上架,normal 正常/开盘,maintain 禁止交易(禁止开平仓),limit_open 限制下单(可平仓),restrictedAPI API限制下单,off 下架
    "offTime":"下架时间",# '-1' 表示正常
    "limitOpenTime":"可开仓时间",# '-1' 表示正常; 其它值表示symbol正在/计划维护，指定时间后禁止交易
    "deliveryTime":"交割时间",
    "deliveryStartTime":"交割开始时间",
    "deliveryPeriod":"交割周期",#"this_quarter":"当季""next_quarter"："次季"
    "launchTime":"上架时间",
    "fundInterval":"资金费结算周期",#每4小时/每8小时【大部分都是8小时】
    "minLever":"最小杠杆",
    "maxLever":"最大杠杆",
    "posLimit":"持仓限制",
    "maintainTime":"维护时间",#（状态处于维护/即将维护时会有值）
})#没单独标注的都是字符串
bitget_mix_info.to_csv("bitget币种信息mix.csv")
while True:#暂时只做八小时一次的，方便后期维护
    #获取全部合约的仓位信息
    params={
        "productType":thisproductType,
        #【productType参数说明】
        # USDT-FUTURES USDT专业合约
        # COIN-FUTURES 混合合约
        # USDC-FUTURES USDC专业合约
        # SUSDT-FUTURES USDT专业合约模拟盘
        # SCOIN-FUTURES 混合合约模拟盘
        # SUSDC-FUTURES USDC专业合约模拟盘
        }
    request_path="/api/v2/mix/position/all-position"
    mixpositions=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
    # logger.info(f"mixpositions,{mixpositions}")#返回值是个列表，列表当中每个元素里都有一个键名为autoMargin是否自动追加保证金，目前设置的大部分都是否off
    # [{'marginCoin': 'SUSDT','symbol': 'SBTCSUSDT','holdSide': 'long','openDelegateSize': '0','marginSize': '369.12291','available': '0.039','locked': '0','total': '0.039','leverage': '10','achievedProfits': '0','openPriceAvg': '94646.9','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '0.6396','liquidationPrice': '18801.660351978073','keepMarginRate': '0.004','markPrice': '94663.3','marginRatio': '0.01749097777','breakEvenPrice': '94760.544466680009','totalFee': '','deductedFee': '2.21473746','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735394735040','uTime': '1735394735040'},{'marginCoin': 'SUSDT','symbol': 'SETHSUSDT','holdSide': 'long','openDelegateSize': '0','marginSize': '632.92456','available': '1.88','locked': '0','total': '1.88','leverage': '10','achievedProfits': '0','openPriceAvg': '3366.62','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '0.2632','liquidationPrice': '1791.45190866726','keepMarginRate': '0.005','markPrice': '3366.76','marginRatio': '0.01749097777','breakEvenPrice': '3369.314912947769','totalFee': '','deductedFee': '1.26584912','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735394707905','uTime': '1735394708143'}]            
    logger.info(f"mixpositions,{mixpositions}")#验证一下买入过程当中的仓位变化
    # positiondf=pd.DataFrame(mixpositions)
    # positiondf.to_csv("positiondf.csv")

    #【时间验证用于判断是开仓还是清仓】
    thisnow=(datetime.datetime.utcnow()+datetime.timedelta(hours=8)).time()#获取标准时间，换算成东八区
    #thisnow=datetime.datetime.now().time()#直接获取东八区时间（同花顺使用的就是使用的东八区的上海时间，但是怕他换服务器）
    logger.info(f"当前小时分钟数,{str(thisnow)},如果卡在这里了说明没到交易时间或者时区不对")
    if (#【延迟30秒再清仓避免没拿到资金费率】
        ((thisnow>datetime.time(8,00,30))and(thisnow<datetime.time(15,50)))
        or
        ((thisnow>datetime.time(16,00,30))and(thisnow<datetime.time(23,50)))
        or
        ((thisnow>datetime.time(0,00,30))and(thisnow<datetime.time(7,50)))
    ):#【在这三个时间段直接清仓USDT存理财】
        # try:
            try:
                droplist=[]#仓位过重不再执行开仓的标的【重置】
                for mixposition in mixpositions:
                    logger.info(f"mixposition,{mixposition}")
                    # try:

                    # #从持仓信息处获取建仓时间【如果存过理财则会返回从理财划转会现货账户的时间{链上转入同理}】
                    # thisuTime=mixposition["uTime"]#1733983259291
                    # logger.info(f"thisuTime,{thisuTime},{type(thisuTime)}")
                    # holdtime=datetime.datetime.utcfromtimestamp(int(thisuTime)/1000)#时间戳转datetime格式
                    # logger.info(f"建仓时间holdtime,{holdtime.strftime('%Y-%m-%d %H:%M:%S')}")

                    #标的信息和可用余额
                    thissymbol=mixposition["symbol"]
                    sellvolume=mixposition["available"]#总持仓数量【目标代币{已经乘以杠杆倍数了}】

                    #【交易精度】#20次/1s (IP)
                    # params={"symbol":thissymbol,}
                    # request_path="/api/v2/spot/public/symbols"#现货
                    params={"symbol":thissymbol,
                        "productType":thisproductType,
                        #【productType参数说明】
                        # USDT-FUTURES USDT专业合约
                        # COIN-FUTURES 混合合约
                        # USDC-FUTURES USDC专业合约
                        # SUSDT-FUTURES USDT专业合约模拟盘
                        # SCOIN-FUTURES 混合合约模拟盘
                        # SUSDC-FUTURES USDC专业合约模拟盘
                        }
                    request_path="/api/v2/mix/market/contracts"#合约
                    thisinfo=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
                    logger.info(f"thisinfo,{thisinfo}")# [{'symbol': 'BGBUSDT','baseCoin': 'BGB','quoteCoin': 'USDT','minTradeAmount': '0','maxTradeAmount': '10000000000','takerFeeRate': '0.001','makerFeeRate': '0.001','pricePrecision': '4','quantityPrecision': '4','quotePrecision': '8','status': 'online','minTradeUSDT': '1','buyLimitPriceRatio': '0.05','sellLimitPriceRatio': '0.05','areaSymbol': 'no','orderQuantity': '200'}]
                    # [{'symbol': 'SBTCSUSDT','baseCoin': 'SBTC','quoteCoin': 'SUSDT','buyLimitPriceRatio': '0.01','sellLimitPriceRatio': '0.01','feeRateUpRatio': '0.1','makerFeeRate': '0.0002','takerFeeRate': '0.0006','openCostUpRatio': '0.1','supportMarginCoins': ['SUSDT'],'minTradeNum': '0.001','priceEndStep': '1','volumePlace': '3','pricePlace': '1','sizeMultiplier': '0.001','symbolType': 'perpetual','minTradeUSDT': '5','maxSymbolOrderNum': '200','maxProductOrderNum': '400','maxPositionNum': '150','symbolStatus': 'normal','offTime': '-1','limitOpenTime': '-1','deliveryTime': '','deliveryStartTime': '','deliveryPeriod': '','launchTime': '','fundInterval': '8','minLever': '1','maxLever': '125','posLimit': '0.05','maintainTime': '','openTime': ''}]
                    # minTradeAmount=float(thisinfo[0]["minTradeAmount"])#最小交易数量
                    # maxTradeAmount=float(thisinfo[0]["maxTradeAmount"])#最大交易数量
                    # quantityPrecision=int(thisinfo[0]["quantityPrecision"])#代币精度
                    # pricePrecision=int(thisinfo[0]["pricePrecision"])#价格精度
                    # #【合约】
                    minTradeAmount=float(thisinfo[0]["minTradeNum"])#最小开单数量(基础币)下单的时候两者都要超过
                    minTradeAmountUSDT=float(thisinfo[0]["minTradeUSDT"])#最小开单数量(USDT)下单的时候两者都要超过
                    quantityPrecision=int(thisinfo[0]["volumePlace"])#数量小数位数【类似于数量精度】
                    pricePrecision=int(thisinfo[0]["pricePlace"])#价格小数位数【类似于价格精度】
                    sizeMultiplier=float(thisinfo[0]["sizeMultiplier"])#数量乘数【买入时不用考虑卖出时需要考虑】下单数量要大于 minTradeNum 并且满足 sizeMulti 的倍数
                    minLever=int(thisinfo[0]["minLever"])#	String	最小杠杆
                    maxLever=int(thisinfo[0]["maxLever"])#	String	最大杠杆
                    # 持仓限制【还有一个限制条件】
                    logger.info(f"quantityPrecision,{quantityPrecision},{type(quantityPrecision)},pricePrecision,{pricePrecision},{type(pricePrecision)}")#字符串
                    # {'code': '00000','msg': 'success','requestTime': 1732951086595,'data': {'symbol': 'BTCUSDT_SPBL','symbolName': 'BTCUSDT','symbolDisplayName': 'BTCUSDT','baseCoin': 'BTC','baseCoinDisplayName': 'BTC','quoteCoin': 'USDT','quoteCoinDisplayName': 'USDT','minTradeAmount': '0','maxTradeAmount': '0','takerFeeRate': '0.002','makerFeeRate': '0.002','priceScale': '2','quantityScale': '6','quotePrecision': '8','status': 'online','minTradeUSDT': '1','buyLimitPriceRatio': '0.05','sellLimitPriceRatio': '0.05','maxOrderNum': '500'}}
                    
                    #【因为下单精度问题很多零碎的代币都没卖掉】
                    sellvolume=round(math.floor(float(sellvolume)*(10**quantityPrecision))/(10**quantityPrecision),
                                    quantityPrecision)#为防止余额不足需要先乘后除再取位数
                    logger.info(f"{thissymbol},sellvolume,{sellvolume},{type(sellvolume)}")

                    # 【盘口深度】#20次/1s (IP)
                    # params={"symbol":str(thissymbol+"USDT"),"limit":'150',"type":'step0'}
                    # request_path="/api/v2/spot/market/orderbook"#现货
                    params={
                        "productType":thisproductType,
                        #【productType参数说明】
                        # USDT-FUTURES USDT专业合约
                        # COIN-FUTURES 混合合约
                        # USDC-FUTURES USDC专业合约
                        # SUSDT-FUTURES USDT专业合约模拟盘
                        # SCOIN-FUTURES 混合合约模拟盘
                        # SUSDC-FUTURES USDC专业合约模拟盘
                        "symbol":str(thissymbol),"limit":'150',"type":'step0'}
                    request_path="/api/v2/mix/market/orderbook"#合约
                    thisdepth=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
                    # logger.info(thisdepth)#【能够获取合约深度数据】
                    bid1=thisdepth["bids"][0][0]#买一
                    bid1v=thisdepth["bids"][0][1]
                    ask1=thisdepth["asks"][0][0]#卖一
                    ask1v=thisdepth["asks"][0][1]
                    logger.info(f"""卖出
                        {bid1},{type(bid1)},bid1
                        {bid1v},{type(bid1v)},bid1v
                        {ask1},{type(ask1)},ask1
                        {ask1v},{type(ask1v)},ask1v
                        """
                        )
                    #【针对现货】
                    if sellvolume>0:#现货有余额才下单
                        # #【现货下单】#10次/1s (UID)
                        # # symbol,quantity,side,orderType,force,price='',clientOrderId=None)
                        # params={
                        #     "symbol":str(thissymbol+"USDT"),#"SBTCSUSDT_SUMCBL"
                        #     "side":"sell",#方向：PS_BUY现货买入，PS_SELL现货卖出
                        #     #【限价单】
                        #     "orderType":"limit",#订单类型"limit"、"market"
                        #     "price":str(sellprice),#限价价格# 价格小数位、价格步长可以通过获取交易对信息接口获取
                        #     "size":str(sellvolume),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                        #     #【市价单】判断剧烈行情是否一定能够成交
                        #     # "orderType":"market",#订单类型"limit"、"market"
                        #     # "size":str(buyusdt),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                        #     "force":"gtc",#执行策略（orderType为market时无效）# gtc：普通限价单，一直有效直至取消# post_only：只做 maker 订单# fok：全部成交或立即取消# ioc：立即成交并取消剩余
                        #     # "clientOrderId":str(random_string("Cuongitl"))#自定义订单ID
                        #     "tpslType":"normal",# normal：普通单（默认值）# tpsl：止盈止损单
                        # }
                        # request_path="/api/v2/spot/trade/place-order"
                        if mixposition["holdSide"]=='short':
                            logger.info(f"当前持仓为空头")
                            thisside="sell"
                            sellprice=round(float(bid1),pricePrecision)
                            logger.info(f"sellprice,{sellprice}")
                        elif mixposition["holdSide"]=='long':
                            logger.info(f"当前持仓为空头")
                            thisside="buy"
                            sellprice=round(float(ask1),pricePrecision)
                            logger.info(f"sellprice,{sellprice}")

                        # 目标下单金额跟最大最小下单金额【含USDT的最小下单金额】对比
                        if sellvolume<float(minTradeAmountUSDT/sellprice):#这个sellvolume是原始代币的数量，所以后面的float应该是这个USDT/代币本身
                            logger.info(f"【跳过后续任务】目标下单金额小于最小下单金额USDT[{minTradeAmountUSDT}]/[{sellprice}]")
                            continue
                        else:
                            logger.info(f"【目标下单金额正常】大于最小下单金额USDT[{minTradeAmountUSDT}]/[{sellprice}]")
                        if sellvolume<float(minTradeAmount):
                            logger.info(f"【跳过后续任务】目标下单金额小于最小下单金额[{minTradeAmount}]")
                            continue
                        else:
                            logger.info(f"【目标下单金额正常】大于最小下单金额[{minTradeAmount}]")

                        # {'marginCoin': 'SUSDT','symbol': 'SEOSSUSDT','holdSide': 'short','openDelegateSize': '0','marginSize': '167.5439','available': '2071','locked': '0','total': '2071','leverage': '10','achievedProfits': '0','openPriceAvg': '0.809','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '-3.7278','liquidationPrice': '2.244419487762','keepMarginRate': '0.01','markPrice': '0.8108','marginRatio': '0.023008182661','breakEvenPrice': '0.80802978213','totalFee': '','deductedFee': '1.0052634','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735460075396','uTime': '1735460075396'}
                        # #【合约下单】# 开多规则为：side=buy,tradeSide=open；开空规则为：side=sell,tradeSide=open；平多规则为：side=buy,tradeSide=close；平空规则为：side=sell,tradeSide=close
                        if thisproductType=="USDT-FUTURES":
                            logger.info(f"当前为实盘，交易抵押物为USDT")
                            marginCoin='USDT'
                        elif thisproductType=="SUSDT-FUTURES":
                            logger.info(f"当前为模拟盘，交易抵押物为SUSDT")
                            marginCoin='SUSDT'
                        params={
                            "productType":thisproductType,
                            #【productType参数说明】
                            # USDT-FUTURES USDT专业合约
                            # COIN-FUTURES 混合合约
                            # USDC-FUTURES USDC专业合约
                            # SUSDT-FUTURES USDT专业合约模拟盘
                            # SCOIN-FUTURES 混合合约模拟盘
                            # SUSDC-FUTURES USDC专业合约模拟盘
                            "marginMode":"crossed",#仓位模式\isolated: 逐仓\crossed: 全仓【使用逐仓模式避免爆仓，只有全仓状态可以使用联合保证金模式】
                            "marginCoin":marginCoin,#保证金币种
                            "tradeSide":"close",#交易类型(仅限双向持仓)\双向持仓模式下必填，单向持仓时不要填\open: 开仓\close: 平仓
                            # "stpMode":"cancel_taker",#STP模式（自成交预防）\none：不设置STP（默认值）\cancel_taker：取消taker单\cancel_maker：取消maker单\cancel_both：两者都取消
                            "symbol":str(thissymbol),#"SBTCSUSDT_SUMCBL"
                            "side":thisside,#方向：PS_BUY现货买入，PS_SELL现货卖出
                            #【限价单】
                            "orderType":"limit",#订单类型"limit"、"market"
                            "price":str(sellprice),# 限价价格# 价格小数位、价格步长可以通过获取交易对信息接口获取
                            "size":str(sellvolume),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                            #【市价单】判断剧烈行情是否一定能够成交
                            # "orderType":"market",#订单类型"limit"、"market"
                            # "size":str(buyusdt),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                            "force":"gtc",#执行策略（orderType为market时无效）# gtc：普通限价单，一直有效直至取消# post_only：只做 maker 订单# fok：全部成交或立即取消# ioc：立即成交并取消剩余
                            # "clientOrderId":str(random_string("Cuongitl"))#自定义订单ID
                            "tpslType":"normal",# normal：普通单（默认值）# tpsl：止盈止损单
                            # "presetStopSurplusPrice":"",#str止盈值，针对tpsl：止盈止损单
                            # "presetStopLossPrice":"",#str止损值，针对tpsl：止盈止损单
                        }
                        request_path="/api/v2/mix/order/place-order"
                        #最小下单金额为1USDT
                        thisorder=client._request_with_params(params=params,request_path=request_path,method="POST")
                        logger.info(f"thisorder,{thisorder}")#如果执行了下单这里返回一个order详情{包含下单是否成功的返回值}
            except Exception as e:
                logger.info(f"清仓卖出模块报错{e}")

            # #【空闲时余额转到现货进行理财】
            try:
                if thisproductType=="USDT-FUTURES":#只在实盘申购理财产品
                    params = {
                        # "symbol":str(thissymbol),
                        "productType":thisproductType,
                        #【productType参数说明】
                        # USDT-FUTURES USDT专业合约
                        # COIN-FUTURES 混合合约
                        # USDC-FUTURES USDC专业合约
                        # SUSDT-FUTURES USDT专业合约模拟盘
                        # SCOIN-FUTURES 混合合约模拟盘
                        # SUSDC-FUTURES USDC专业合约模拟盘
                        "marginCoin":marginCoin}
                    request_path="/api/v2/mix/account/accounts"#合约资产余额
                    res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
                    logger.info(f"总账户合约资产余额,{type(res)},{res}")#unrealizedPL未实现盈亏
                    # available#账户可用数量{应该是计提损益之前的账户权益}比权益小比保证金大
                    # accountEquity#账户权益
                    # crossedMaxAvailable#可用全仓保证金
                    # isolatedMaxAvailable#可用逐仓保证金
                    mixbalance=[re["available"] for re in res if re["marginCoin"]==marginCoin][0]#返回的数据为字符串需要提前转float
                    logger.info(f"mixbalance,{mixbalance},{type(mixbalance)}")
                    if float(mixbalance)>=1:
                        request_path="/api/v2/spot/wallet/transfer"
                        params={
                            "fromType":"usdt_futures",
                            "toType":"spot",
                            # 转入账户类型
                            # spot 现货账户
                            # p2p P2P/资金账户
                            # coin_futures 币本位合约账户
                            # usdt_futures U本位合约账户
                            # usdc_futures USDC合约账户
                            # crossed_margin 全仓杠杆账户
                            # isolated_margin 逐仓杠杆账户
                            "amount":mixbalance,
                            "coin":"USDT",
                            }
                        res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
                        logger.info(f"资产划转,{float(mixbalance)},{res},{len(res)}")
                    else:
                        logger.info(f"余额不足不进行资产划转【合约转现货】,{float(mixbalance)}")
                    #【查询现货余额并转入理财账户】卖出大概一秒左右就转到理财账户了
                    spotbalance=getspotbalance(coin="USDT")
                    usdtbalance=[balance for balance in spotbalance if balance["coin"]=="USDT"][0]["available"]
                    logger.info(f"{usdtbalance},{type(usdtbalance)}")
                    if float(usdtbalance)>=1:#现货资产余额大于等于1的时候进行活期理财申购{避免余额不足报错}【验证后是对的，usdtbalance="0"时usdtbalance="0"验证为False】
                        logger.info(f"余额大于1USDT执行理财申购")
                        #【获取理财产品列表】#10次/1s (Uid)
                        savingslist=getsavingslist(coin="USDT")
                        logger.info(f"{savingslist},{type(savingslist)}")
                        usdtproductId=str(savingslist[0]["productId"])#取出来产品ID
                        logger.info(f"{usdtproductId},{type(usdtproductId)}")
                        #【申购理财产品】10次/1s (Uid)转回来申购理财产品的时候容易余额不足
                        request_path="/api/v2/earn/savings/subscribe"
                        params={"productId":usdtproductId,
                                "periodType":"flexible",#只要活期存款
                                "amount":usdtbalance
                                }
                        res=client._request_with_params(params=params,request_path=request_path,method="POST")
                        res=res["data"]
                        logger.info(f"申购理财产品,{res}")
                    else:
                        logger.info(f"余额不足不进行申购")
            except Exception as e:#【理财申购后现货余额需要一定时间才能改变因而这里可能因为重复执行而报错】
                logger.info(f"闲置资金活期理财报错,{e}")
            time.sleep(0.5)#避免重复申购导致报错
        # except Exception as e:
        #     logger.info(f"清仓处理整体报错,{e}")

    else:#不在目标时间内则执行选股任务【与交易时间空出来10分钟，所有交易在这10分钟内完成即可】
        #【计算当前总资产作为单标的最大仓位】
        if thisproductType=="USDT-FUTURES":
            logger.info(f"当前为实盘，交易抵押物为USDT")
            marginCoin='USDT'
        elif thisproductType=="SUSDT-FUTURES":
            logger.info(f"当前为模拟盘，交易抵押物为SUSDT")
            marginCoin='SUSDT'
        params = {
            # "symbol":str(thissymbol),
            "productType":thisproductType,
            #【productType参数说明】
            # USDT-FUTURES USDT专业合约
            # COIN-FUTURES 混合合约
            # USDC-FUTURES USDC专业合约
            # SUSDT-FUTURES USDT专业合约模拟盘
            # SCOIN-FUTURES 混合合约模拟盘
            # SUSDC-FUTURES USDC专业合约模拟盘
            "marginCoin":marginCoin}
        request_path="/api/v2/mix/account/accounts"#合约资产余额
        res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
        logger.info(f"总账户合约资产余额,{type(res)},{res}")#unrealizedPL未实现盈亏
        # available#账户可用数量{应该是计提损益之前的账户权益}比权益小比保证金大
        # accountEquity#账户权益
        # crossedMaxAvailable#可用全仓保证金
        # isolatedMaxAvailable#可用逐仓保证金
        # usdtEquity#折算USDT权益
        mixbalance=[re["available"] for re in res if re["marginCoin"]==marginCoin][0]#返回的数据为字符串需要提前转float
        logger.info(f"mixbalance,{mixbalance},{type(mixbalance)}")
        # 【放到代码一开始进行初始化会因为默认余额为0导致后续交易金额为0因而无法交易】
        trademoney=float(mixbalance)#【实盘】trademoney*trademoneytraderate就是单次下单最大金额USDT{一般低于总资产的余额}，trademoney*trademoneyhorate是最大持仓金额
        try:
            if thisproductType=="USDT-FUTURES":#只在实盘赎回理财产品
                logger.info(f"赎回活期理财产品执行开仓")
                #【理财资产信息】10次/1s (Uid)查询活期存款持仓对其进行赎回
                request_path="/api/v2/earn/savings/assets"
                params = {"periodType":"flexible",}#只要活期存款
                savingsList=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]["resultList"]
                logger.info(f"{savingsList}")
                for savings in savingsList:
                    thisproductId=savings['productId']
                    thisorderId=savings['orderId']
                    thisholdAmount=savings["holdAmount"]
                    logger.info(f"thisproductId,{thisproductId},{type(thisproductId)},thisholdAmount,{thisholdAmount},{type(thisholdAmount)}")
                    #【赎回理财产品】10次/1s (Uid)
                    request_path="/api/v2/earn/savings/redeem"
                    params = {"productId":thisproductId,
                            "orderId":thisorderId,
                            "periodType":"flexible",#只要活期存款
                            "amount":thisholdAmount,
                            }
                    res=client._request_with_params(params=params,request_path=request_path,method="POST")
                    res=res["data"]
                    logger.info(f"赎回理财产品,{res}")
                #【查询现货USDT余额】对赎回后的USDT余额进行统计方便后面计算下单金额
                spotbalance=getspotbalance(coin="USDT")
                usdtbalance=[balance for balance in spotbalance if balance["coin"]=="USDT"][0]["available"]
                logger.info(f"usdtbalance,{usdtbalance},{type(usdtbalance)}")
                if float(usdtbalance)>=1:#只有有余额才划转没余额不必划转
                    #【划转回期货账户】            
                    request_path="/api/v2/spot/wallet/transfer"
                    params={
                        "fromType":"spot",
                        "toType":"usdt_futures",
                        # 转入账户类型
                        # spot 现货账户
                        # p2p P2P/资金账户
                        # coin_futures 币本位合约账户
                        # usdt_futures U本位合约账户
                        # usdc_futures USDC合约账户
                        # crossed_margin 全仓杠杆账户
                        # isolated_margin 逐仓杠杆账户
                        "amount":usdtbalance,
                        "coin":"USDT",
                        }
                    res=client._request_with_params(params=params,request_path=request_path,method="POST")["data"]#quantityScale可能是精度
                    logger.info(f"资产划转,{float(usdtbalance)},{res},{len(res)}")
                else:
                    logger.info(f"余额不足不进行资产划转【现货转合约】,{float(usdtbalance)}")
        except Exception as e:
            logger.info(f"理财赎回并划转期货账户报错{e}")
            
        # #【获取现货行情】这个是比对期现价差用的
        # request_path="/api/v2/spot/market/tickers"
        # params={"symbol":""}
        # bitget_spottickers=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
        # bitget_spottickers=pd.DataFrame(bitget_spottickers)
        # bitget_spottickers=bitget_spottickers[["symbol","bidPr","askPr","bidSz","askSz"]]#只保留基础的买卖盘数据
        # bitget_spottickers=bitget_spottickers.rename(columns={
        #     # "symbol":"交易对名称",
        #     "high24h":"24小时最高价",
        #     "open":"24小时开盘价",
        #     "lastPr":"最新成交价",
        #     "low24h":"24小时最低价",
        #     "quoteVolume":"计价币成交额",
        #     "baseVolume":"基础币成交额",
        #     "usdtVolume":"USDT成交额",
        #     "bidPr":"现货买一价",
        #     "askPr":"现货卖一价",
        #     "bidSz":"现货买一量",
        #     "askSz":"现货卖一量",
        #     "openUtc":"零时区开盘价",
        #     "ts":"当前时间",#。Unix毫秒时间戳，例如1690196141868
        #     "changeUtc24h":"UTC0时涨跌幅",# 0.01表示1%
        #     "change24h":"24小时涨跌幅",# 0.01表示1%
        #     # 返回字段	参数类型	字段说明
        #     # symbol	String	交易对名称
        #     # high24h	String	24小时最高价
        #     # open	String	24小时开盘价
        #     # lastPr	String	最新成交价
        #     # low24h	String	24小时最低价
        #     # quoteVolume	String	计价币成交额
        #     # baseVolume	String	基础币成交额
        #     # usdtVolume	String	USDT成交额
        #     # bidPr	String	买一价
        #     # askPr	String	卖一价
        #     # bidSz	String	买一量
        #     # askSz	String	卖一量
        #     # openUtc	String	零时区 开盘价
        #     # ts	String	当前时间。Unix毫秒时间戳，例如1690196141868
        #     # changeUtc24h	String	UTC0时涨跌幅,0.01表示1%
        #     # change24h	String	24小时涨跌幅,0.01表示1%
        #     })
        # bitget_spottickers.to_csv("bitget现货行情信息.csv")

        #【获取合约行情】
        request_path="/api/v2/mix/market/tickers"
        params={
            "productType":thisproductType,
            #【productType参数说明】
            # USDT-FUTURES USDT专业合约
            # COIN-FUTURES 混合合约
            # USDC-FUTURES USDC专业合约
            # SUSDT-FUTURES USDT专业合约模拟盘
            # SCOIN-FUTURES 混合合约模拟盘
            # SUSDC-FUTURES USDC专业合约模拟盘
            }
        bitget_mixtickers=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
        bitget_mixtickers=pd.DataFrame(bitget_mixtickers)
        bitget_mixtickers=bitget_mixtickers.rename(columns={
            # "symbol":"交易对名称",
            "high24h":"24小时最高价",
            "open":"24小时开盘价",
            "lastPr":"最新成交价",
            "low24h":"24小时最低价",
            "quoteVolume":"计价币成交额",
            "baseVolume":"基础币成交额",
            "usdtVolume":"USDT成交额",
            "bidPr":"买一价",
            "askPr":"卖一价",
            "bidSz":"买一量",
            "askSz":"卖一量",
            "openUtc":"零时区开盘价",
            "ts":"当前时间",#。Unix毫秒时间戳，例如1690196141868
            "changeUtc24h":"UTC0时涨跌幅",# 0.01表示1%
            "change24h":"24小时涨跌幅",# 0.01表示1%
            "indexPrice":"指数价格",
            "fundingRate":"资金费率",
            "holdingAmount":"全市场当前持仓",#单位是交易币数量【当前全市场总持仓量】
            "open24h":"开盘价24小时",
            "markPrice":"标记时间",
            "deliveryStartTime":"交割开始时间",
            "deliveryTime":"交割时间",
            "deliveryStatus":"交割状态",# delivery_config_period: 新上币对配置中,delivery_normal: 交易中,delivery_before: 交割前10分钟，禁止开仓,delivery_period: 交割中，禁止开平仓、撤单
            # 返回字段	参数类型	字段说明
            # > baseVolume	String	交易币交易量
            # > quoteVolume	String	计价币交易量
            # > usdtVolume	String	usdt成交量
            # > openUtc	String	开盘价(UTC+0时区)
            # > changeUtc24h	String	24小时价格涨跌幅(UTC+0时区)
            # > indexPrice	String	指数价格
            # > fundingRate	String	资金费率
            # > holdingAmount	String	当前持仓,单位是交易币数量
            # > open24h	String	开盘价 24小时
            # 开盘时间为24小时相对比，即：现在为2号19点，那么开盘时间对应为1号19点。
            # > deliveryStartTime	String	交割开始时间（仅限交割合约）
            # > deliveryTime	String	交割时间（仅限交割合约）
            # > deliveryStatus	String	交割状态,仅限交割合约
            # delivery_config_period: 新上币对配置中
            # delivery_normal: 交易中
            # delivery_before: 交割前10分钟，禁止开仓
            # delivery_period: 交割中，禁止开平仓、撤单
            # > markPrice	String	标记价格
            # symbol	String	交易对名称
            # high24h	String	24小时最高价
            # open	String	24小时开盘价
            # lastPr	String	最新成交价
            # low24h	String	24小时最低价
            # quoteVolume	String	计价币成交额
            # baseVolume	String	基础币成交额
            # usdtVolume	String	USDT成交额
            # bidPr	String	买一价
            # askPr	String	卖一价
            # bidSz	String	买一量
            # askSz	String	卖一量
            # openUtc	String	零时区 开盘价
            # ts	String	当前时间。Unix毫秒时间戳，例如1690196141868
            # changeUtc24h	String	UTC0时涨跌幅,0.01表示1%
            # change24h	String	24小时涨跌幅,0.01表示1%
            })
        bitget_mixtickers["USDT成交额"]=bitget_mixtickers["USDT成交额"].astype(float)
        #【成交额限制】
        bitget_mixtickers=bitget_mixtickers[bitget_mixtickers["USDT成交额"]>500000]#24小时成交额50wUSDT以上才进入观察吃，且对手盘厚度要够且盘口价差不那么大【计算价差的时候盘口价差需要扣除资金费率】【尽量taker买入，maker卖出】
        bitget_mixtickers["买一价"]=bitget_mixtickers["买一价"].astype(float)
        bitget_mixtickers["买一量"]=bitget_mixtickers["买一量"].astype(float)
        bitget_mixtickers["卖一价"]=bitget_mixtickers["卖一价"].astype(float)
        bitget_mixtickers["卖一量"]=bitget_mixtickers["卖一量"].astype(float)
        bitget_mixtickers["买一额"]=bitget_mixtickers["买一量"]*bitget_mixtickers["买一价"]
        bitget_mixtickers["卖一额"]=bitget_mixtickers["卖一量"]*bitget_mixtickers["卖一价"]
        #实际交易要承担双向价差（一买一卖）
        bitget_mixtickers["盘口价差"]=(bitget_mixtickers["卖一价"]-bitget_mixtickers["买一价"])/((bitget_mixtickers["卖一价"]+bitget_mixtickers["买一价"])/2)
        #【盘口价差限制、买卖一档总金额限制】
        # bitget_mixtickers=bitget_mixtickers[bitget_mixtickers["买一额"]>100]
        # bitget_mixtickers=bitget_mixtickers[bitget_mixtickers["卖一额"]>100]
        bitget_mixtickers=bitget_mixtickers[(bitget_mixtickers["卖一额"]+bitget_mixtickers["买一额"])>200]#【实盘要用】【盘口的挂单金额严重影响收益率】买卖总金额大于500还能有不少标的可以选择
        bitget_mixtickers=bitget_mixtickers[bitget_mixtickers["盘口价差"]<0.002]#【实盘要用】
        bitget_mixtickers["资金费率"]=bitget_mixtickers["资金费率"].astype(float)
        bitget_mixtickers["资金费率绝对值"]=abs(bitget_mixtickers["资金费率"])
        bitget_mixtickers["套利利润"]=bitget_mixtickers["资金费率绝对值"]-bitget_mixtickers["盘口价差"]
        bitget_mixtickers=bitget_mixtickers[bitget_mixtickers["套利利润"]>0]#【实盘要用】优先做费率利润大于盘口价差+手续费的
        bitget_mixtickers=bitget_mixtickers.sort_values(by="套利利润")#有一些标的的费率小于盘口价差（滑点），所以这里总共可交易的标的数量比实际的少

        # #【结合期货现货价差看期货资金费率】
        # bitget_mixtickers=bitget_spottickers.merge(bitget_mixtickers,on="symbol")
        # bitget_mixtickers["现货买一价"]=bitget_mixtickers["现货买一价"].astype(float)
        # # bitget_mixtickers["现货买一量"]=bitget_mixtickers["现货买一量"].astype(float)
        # bitget_mixtickers["现货卖一价"]=bitget_mixtickers["现货卖一价"].astype(float)
        # # bitget_mixtickers["现货卖一量"]=bitget_mixtickers["现货卖一量"].astype(float)
        # bitget_mixtickers["期多现空价差"]=bitget_mixtickers["买一价"]/bitget_mixtickers["现货卖一价"]-1#而且这个交易需要承担双向价差
        # bitget_mixtickers["期空现多价差"]=bitget_mixtickers["现货买一价"]/bitget_mixtickers["卖一价"]-1#而且这个交易需要承担双向价差
        # bitget_mixtickers.loc[(bitget_mixtickers["资金费率"]>0)&(bitget_mixtickers["期空现多价差"]>-0.001),"做空期货"]=1
        # bitget_mixtickers.loc[(bitget_mixtickers["资金费率"]<0)&(bitget_mixtickers["期多现空价差"]>-0.001),"做多期货"]=1
        # #【单看期货资金费率】
        # bitget_mixtickers.loc[(bitget_mixtickers["资金费率"]>0),"做空期货"]=1
        # bitget_mixtickers.loc[(bitget_mixtickers["资金费率"]<0),"做多期货"]=1
        # bitget_mixtickers.to_csv("bitget_mixtickers.csv")

        # #【只要套利利润值最大的holdnum个标的】
        if len(bitget_mixtickers)>=holdnum:
            logger.info(f"只保留套利利润最大的{holdnum}个数据")
            bitget_mixtickers=bitget_mixtickers.nlargest(holdnum,'套利利润')
        bitget_mixtickers.to_csv("bitget合约行情信息.csv")
        logger.info(f"bitget_mixtickers,{bitget_mixtickers}")
        #【做多逻辑】
        for index,info in bitget_mixtickers.iterrows():
            thissymbol=info["symbol"]
            rate=info["资金费率"]
            logger.info(f"thissymbol,{thissymbol},资金费率绝对值,rate,{rate},{type(rate)},abs(rate),{abs(rate)},{type(abs(rate))}")
            #【资金费率绝对值的底线】之前的交易没有执行核心原因就是这个absrate设置的太高临近交易的时候实现不了
            if (abs(rate)>absrate):#只做资金费率绝对值大于某个值的标的
                #【仓位控制模块】
                try:# 这个仓位管理模块可以单独执行，在这里根据当前仓位填充droplist，卖出的部分重置droplist，买入的部分验证droplist，如果在开仓时间内才计算仓位进行填充，空仓时间内只减仓不验证影响不大
                    #获取单个标的的仓位信息
                    if thisproductType=="USDT-FUTURES":
                        logger.info(f"当前为实盘，交易抵押物为USDT")
                        marginCoin='USDT'
                    elif thisproductType=="SUSDT-FUTURES":
                        logger.info(f"当前为模拟盘，交易抵押物为SUSDT")
                        marginCoin='SUSDT'
                    params={
                        "productType":thisproductType,
                        #【productType参数说明】
                        # USDT-FUTURES USDT专业合约
                        # COIN-FUTURES 混合合约
                        # USDC-FUTURES USDC专业合约
                        # SUSDT-FUTURES USDT专业合约模拟盘
                        # SCOIN-FUTURES 混合合约模拟盘
                        # SUSDC-FUTURES USDC专业合约模拟盘
                        "symbol":str(thissymbol),
                        "marginCoin":marginCoin,
                        }
                    request_path="/api/v2/mix/position/single-position"#【单个标的的持仓信息】
                    mixposition=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
                    logger.info(f"thismixposition,{mixposition}")# [{'marginCoin': 'SUSDT','symbol': 'SBTCSUSDT','holdSide': 'long','openDelegateSize': '0','marginSize': '369.12291','available': '0.039','locked': '0','total': '0.039','leverage': '10','achievedProfits': '0','openPriceAvg': '94646.9','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '0.6396','liquidationPrice': '18801.660351978073','keepMarginRate': '0.004','markPrice': '94663.3','marginRatio': '0.01749097777','breakEvenPrice': '94760.544466680009','totalFee': '','deductedFee': '2.21473746','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735394735040','uTime': '1735394735040'},{'marginCoin': 'SUSDT','symbol': 'SETHSUSDT','holdSide': 'long','openDelegateSize': '0','marginSize': '632.92456','available': '1.88','locked': '0','total': '1.88','leverage': '10','achievedProfits': '0','openPriceAvg': '3366.62','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '0.2632','liquidationPrice': '1791.45190866726','keepMarginRate': '0.005','markPrice': '3366.76','marginRatio': '0.01749097777','breakEvenPrice': '3369.314912947769','totalFee': '','deductedFee': '1.26584912','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735394707905','uTime': '1735394708143'}]            
                    if len(mixposition)>0:
                        thisposition=mixposition[0]
                        thisleverage=int(thisposition["leverage"])#杠杆倍数
                        thisavailable=float(thisposition["available"])#可用余额【已经乘以杠杆倍数了】
                        thisopenPriceAvg=float(thisposition["openPriceAvg"])#开仓均价
                        if (thisavailable*thisopenPriceAvg)>trademoney*trademoneyholdrate:#另外需要考虑仓位问题，这个是一倍杠杆下的金额，实际上是多倍杠杆，因而可用扩大很多倍数
                            droplist.append(str(thissymbol))#总仓位达到余额的一半则将该标的列为不可交易标的，不再进行开仓
                            logger.info(f"【仓位已满】,{thissymbol},标的余额,{thisavailable}*{thisopenPriceAvg},最大持仓金额设置为,{trademoney*trademoneyholdrate},droplist,{droplist}")
                    else:
                        thisavailable=0
                        logger.info(f"【没有持仓】,{thissymbol},标的余额【默认为0】,{thisavailable}")
                except Exception as e:
                    logger.info(f"仓位管理报错,{e}")
                if(thissymbol not in droplist):#如果仓位已满则不再进行交易
                    #【交易精度】#20次/1s (IP)
                    # params={"symbol":thissymbol,}
                    # request_path="/api/v2/spot/public/symbols"#现货
                    params={"symbol":thissymbol,
                        "productType":thisproductType,
                        #【productType参数说明】
                        # USDT-FUTURES USDT专业合约
                        # COIN-FUTURES 混合合约
                        # USDC-FUTURES USDC专业合约
                        # SUSDT-FUTURES USDT专业合约模拟盘
                        # SCOIN-FUTURES 混合合约模拟盘
                        # SUSDC-FUTURES USDC专业合约模拟盘
                        }
                    request_path="/api/v2/mix/market/contracts"#合约
                    thisinfo=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
                    logger.info(f"thisinfo,{thisinfo}")# [{'symbol': 'BGBUSDT','baseCoin': 'BGB','quoteCoin': 'USDT','minTradeAmount': '0','maxTradeAmount': '10000000000','takerFeeRate': '0.001','makerFeeRate': '0.001','pricePrecision': '4','quantityPrecision': '4','quotePrecision': '8','status': 'online','minTradeUSDT': '1','buyLimitPriceRatio': '0.05','sellLimitPriceRatio': '0.05','areaSymbol': 'no','orderQuantity': '200'}]
                    # [{'symbol': 'SBTCSUSDT','baseCoin': 'SBTC','quoteCoin': 'SUSDT','buyLimitPriceRatio': '0.01','sellLimitPriceRatio': '0.01','feeRateUpRatio': '0.1','makerFeeRate': '0.0002','takerFeeRate': '0.0006','openCostUpRatio': '0.1','supportMarginCoins': ['SUSDT'],'minTradeNum': '0.001','priceEndStep': '1','volumePlace': '3','pricePlace': '1','sizeMultiplier': '0.001','symbolType': 'perpetual','minTradeUSDT': '5','maxSymbolOrderNum': '200','maxProductOrderNum': '400','maxPositionNum': '150','symbolStatus': 'normal','offTime': '-1','limitOpenTime': '-1','deliveryTime': '','deliveryStartTime': '','deliveryPeriod': '','launchTime': '','fundInterval': '8','minLever': '1','maxLever': '125','posLimit': '0.05','maintainTime': '','openTime': ''}]
                    if len(thisinfo)>0:#对于绝大部分可交易标的都存在其详情数据的len(thisinfo)>0，如果不存在则说明该标的不可交易
                        # #【现货】
                        # minTradeAmount=float(thisinfo[0]["minTradeAmount"])#最小交易数量
                        # maxTradeAmount=float(thisinfo[0]["maxTradeAmount"])#最大交易数量
                        # quantityPrecision=int(thisinfo[0]["quantityPrecision"])#代币精度
                        # pricePrecision=int(thisinfo[0]["pricePrecision"])#价格精度
                        # #【合约】
                        minTradeAmount=float(thisinfo[0]["minTradeNum"])#最小开单数量(基础币)下单的时候两者都要超过
                        minTradeAmountUSDT=float(thisinfo[0]["minTradeUSDT"])#最小开单数量(USDT)下单的时候两者都要超过
                        quantityPrecision=int(thisinfo[0]["volumePlace"])#数量小数位数【类似于数量精度】
                        pricePrecision=int(thisinfo[0]["pricePlace"])#价格小数位数【类似于价格精度】
                        sizeMultiplier=float(thisinfo[0]["sizeMultiplier"])#数量乘数【买入时不用考虑卖出时需要考虑】下单数量要大于 minTradeNum 并且满足 sizeMulti 的倍数
                        minLever=int(thisinfo[0]["minLever"])#String最小杠杆
                        maxLever=int(thisinfo[0]["maxLever"])#String最大杠杆
                        if (minLever<10)and(maxLever>10):
                            thisLever=int(10)
                            logger.info(f"默认10倍杠杆,{thisLever}")
                        elif (minLever<5)and(maxLever>5):
                            thisLever=int(5)
                            logger.info(f"默认5倍杠杆,{thisLever}")
                        else:
                            thisLever=minLever
                            logger.info(f"默认最小杠杆,{thisLever}")
                        # 持仓限制【还有一个限制条件】
                        logger.info(f"quantityPrecision,{quantityPrecision},{type(quantityPrecision)},pricePrecision,{pricePrecision},{type(pricePrecision)}")#字符串
                        # {'code': '00000','msg': 'success','requestTime': 1732951086595,'data': {'symbol': 'BTCUSDT_SPBL','symbolName': 'BTCUSDT','symbolDisplayName': 'BTCUSDT','baseCoin': 'BTC','baseCoinDisplayName': 'BTC','quoteCoin': 'USDT','quoteCoinDisplayName': 'USDT','minTradeAmount': '0','maxTradeAmount': '0','takerFeeRate': '0.002','makerFeeRate': '0.002','priceScale': '2','quantityScale': '6','quotePrecision': '8','status': 'online','minTradeUSDT': '1','buyLimitPriceRatio': '0.05','sellLimitPriceRatio': '0.05','maxOrderNum': '500'}}
                        
                        # 【盘口深度】#20次/1s (IP)
                        # params={"symbol":str(thissymbol+"USDT"),"limit":'150',"type":'step0'}
                        # request_path="/api/v2/spot/market/orderbook"#现货
                        params={
                            "productType":thisproductType,
                            #【productType参数说明】
                            # USDT-FUTURES USDT专业合约
                            # COIN-FUTURES 混合合约
                            # USDC-FUTURES USDC专业合约
                            # SUSDT-FUTURES USDT专业合约模拟盘
                            # SCOIN-FUTURES 混合合约模拟盘
                            # SUSDC-FUTURES USDC专业合约模拟盘
                            "symbol":str(thissymbol),"limit":'150',"type":'step0'}
                        request_path="/api/v2/mix/market/orderbook"#合约
                        thisdepth=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
                        # logger.info(thisdepth)#【能够获取合约深度数据】
                        bid1=thisdepth["bids"][0][0]#买一
                        bid1v=thisdepth["bids"][0][1]
                        ask1=thisdepth["asks"][0][0]#卖一
                        ask1v=thisdepth["asks"][0][1]
                        logger.info(f"""买入
                            {bid1},{type(bid1)},bid1
                            {bid1v},{type(bid1v)},bid1v
                            {ask1},{type(ask1)},ask1
                            {ask1v},{type(ask1v)},ask1v
                            """
                            )
                        
                        #【获取可用余额】
                        # coin="USDT"
                        # coin=""
                        # params = {"coin":coin}
                        # request_path="/api/v2/spot/account/assets"#现货资产余额
                        if thisproductType=="USDT-FUTURES":
                            logger.info(f"当前为实盘，交易抵押物为USDT")
                            marginCoin='USDT'
                        elif thisproductType=="SUSDT-FUTURES":
                            logger.info(f"当前为模拟盘，交易抵押物为SUSDT")
                            marginCoin='SUSDT'
                        params = {
                            "symbol":str(thissymbol),
                            "productType":thisproductType,
                            #【productType参数说明】
                            # USDT-FUTURES USDT专业合约
                            # COIN-FUTURES 混合合约
                            # USDC-FUTURES USDC专业合约
                            # SUSDT-FUTURES USDT专业合约模拟盘
                            # SCOIN-FUTURES 混合合约模拟盘
                            # SUSDC-FUTURES USDC专业合约模拟盘
                            "marginCoin":marginCoin}
                        request_path="/api/v2/mix/account/accounts"#合约资产余额
                        res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
                        logger.info(f"合约资产余额,{str(thissymbol)},{type(res)},{res}")#unrealizedPL未实现盈亏
                        # available#账户可用数量{应该是计提损益之前的账户权益}比权益小比保证金大
                        # accountEquity#账户权益
                        # crossedMaxAvailable#可用全仓保证金
                        # isolatedMaxAvailable#可用逐仓保证金
                        #【保证金比余额更准确】保证金减去仓位应该就是当前方向的可下单余额了
                        # mixbalance=float([re["available"] for re in res if re["marginCoin"]==marginCoin][0])#返回的数据为字符串需要提前转float
                        # logger.info(f"mixbalance,{mixbalance},{type(mixbalance)}")
                        crossedMaxAvailablemixbalance=float([re["crossedMaxAvailable"] for re in res if re["marginCoin"]==marginCoin][0])#返回的数据为字符串需要提前转float
                        logger.info(f"crossedMaxAvailablemixbalance,{crossedMaxAvailablemixbalance},{type(crossedMaxAvailablemixbalance)}")

                        #【根据多空方向判断下单价格】
                        if rate>0:#【费率为正数适合做空】
                            logger.info(f"当前开仓方向是空头")
                            buyprice=round(float(ask1),pricePrecision)#卖的时候不急了在自己这边挂卖单就行
                            logger.info(f"buyprice,{buyprice}")
                            thisside="sell"
                            holdSide="short"#用于调整杠杆倍数
                        elif rate<0:#【费率为负数适合做多】
                            logger.info(f"当前开仓方向是多头")
                            buyprice=round(float(bid1),pricePrecision)#卖的时候不急了在自己这边挂卖单就行
                            logger.info(f"buyprice,{buyprice}")
                            thisside="buy"
                            holdSide="long"#用于调整杠杆倍数
                            
                        #【调整杠杆倍数】
                        params={"symbol":thissymbol,
                                "marginCoin":marginCoin,
                                "productType":thisproductType,
                                "leverage":thisLever,#杠杆倍数【采用最大倍数】
                                "holdSide":holdSide,#持仓方向（全仓模式下不传，会忽略此参数）long：多仓；short：空仓
                                #【productType参数说明】
                                # USDT-FUTURES USDT专业合约
                                # COIN-FUTURES 混合合约
                                # USDC-FUTURES USDC专业合约
                                # SUSDT-FUTURES USDT专业合约模拟盘
                                # SCOIN-FUTURES 混合合约模拟盘
                                # SUSDC-FUTURES USDC专业合约模拟盘
                                }
                        request_path="/api/v2/mix/account/set-leverage"#修改杠杆倍数【否则使用默认倍数】
                        cance_order=client._request_with_params(params=params,request_path=request_path,method="POST")#【杠杆倍数调整后实际交易当中开单的杠杆倍数也跟着变化了】
                        # 使用当前可下单数量跟最大最小下单金额【含USDT的最小下单金额】对比【如果不进行验证则计算最大开仓数量就会报错】
                        if crossedMaxAvailablemixbalance<float(minTradeAmountUSDT/buyprice):#这个sellvolume是原始代币的数量，所以后面的float应该是这个USDT/代币本身
                            logger.info(f"【跳过后续任务】可下单数量小于最小下单金额USDT[{minTradeAmountUSDT}]/价格[{buyprice}]")
                            continue
                        if crossedMaxAvailablemixbalance<float(minTradeAmount):#这个sellvolume是原始代币的数量，所以后面的float应该是这个USDT/代币本身
                            logger.info(f"【跳过后续任务】可下单数量小于最小下单金额[{minTradeAmount}]")
                            continue
                        # 【可开仓数量】需要前面的buyprice，含义是加杠杆后买入的合约目标代币的总数量，如果是100USDT保证金，XRP/USDT的50倍合约价格为2USDT，则结果是250
                        params = {
                            "symbol":str(thissymbol),
                            "productType":thisproductType,
                            #【productType参数说明】
                            # USDT-FUTURES USDT专业合约
                            # COIN-FUTURES 混合合约
                            # USDC-FUTURES USDC专业合约
                            # SUSDT-FUTURES USDT专业合约模拟盘
                            # SCOIN-FUTURES 混合合约模拟盘
                            # SUSDC-FUTURES USDC专业合约模拟盘
                            "marginCoin":marginCoin,
                            # "openAmount":mixbalance,#类似于总资产了
                            "openAmount":crossedMaxAvailablemixbalance,#可进行全仓交易的保证金数量
                            "openPrice":buyprice,#订单价格
                            "leverage":thisLever,#杠杆倍数
                            }
                        request_path="/api/v2/mix/account/open-count"#可开仓数量
                        res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
                        logger.info(f"总可开仓数量,{str(thissymbol)},{type(res)},{res}")#unrealizedPL未实现盈亏
                        logger.info(type(res["size"]))#单独提出来避免[]在github action当中报错
                        logger.info(res["size"])#单独提出来避免[]在github action当中报错
                        maxvolume=float(res["size"])#最大开仓数量
                        logger.info(f"maxvolume,{maxvolume}")
                        # #最大下单数量=maxvolume-已经持仓的数量
                        # maxvolume=maxvolume-thisavailable
                        # logger.info(f"maxvolume,{maxvolume}")

                        #【根据可下单数量计算可下单金额与单笔最大金额对比控制单笔下单金额】
                        maxmoney=maxvolume*buyprice
                        #计算下单数量【这里不一定是对的，有时候比可开金额要大】
                        if maxmoney>trademoney*traderate:#当maxmoney大于trademoney的时候按照trademoney
                            buymoney=trademoney#这里在实盘显示的0，也就是目标下单
                            logger.info(f"trademoney,{trademoney}")
                        else:#当maxmoney小于等于于trademoney的时候按照maxmoney
                            buymoney=maxmoney
                            logger.info(f"maxmoney,{maxmoney}")
                        logger.info(f"buymoney,{buymoney}")
                        # 金额/价格=数量，这里不需要对杠杆进行处理即可获得实际数量
                        buyvolume=(((buymoney/buyprice))//(sizeMultiplier))*(sizeMultiplier)#【数量上可能需要再次乘以杠杆】计算了应下单数量后还需要根据数量乘数去掉余数
                        logger.info(f"buyvolume,{buyvolume}")
                        if buyvolume>maxvolume:
                            logger.info(f"拟下单金额大于最大可下单数量进行调整")
                            buyvolume=maxvolume
                        else:
                            logger.info(f"拟下单金额不大于最大可下单数量无需进行调整")
                        logger.info(f"buyvolume,{buyvolume}")
                        #【因为下单精度问题很多零碎的代币都没卖掉】
                        buyvolume=round(math.floor(float(buyvolume)*(10**quantityPrecision))/(10**quantityPrecision),
                                        quantityPrecision)#为防止余额不足需要先乘后除再取位数
                        logger.info(f"{thissymbol},buyvolume,{buyvolume},{type(buyvolume)}")
                                        
                        # 目标下单金额跟最大最小下单金额【含USDT的最小下单金额】对比
                        if buyvolume<float(minTradeAmountUSDT/buyprice):#这个buyvolume是原始代币的数量，所以后面的float应该是这个USDT/代币本身
                            logger.info(f"【跳过后续任务】目标下单金额小于最小下单金额USDT[{minTradeAmountUSDT}]/[{buyprice}]")
                            continue
                        else:
                            logger.info(f"【目标下单金额正常】大于最小下单金额USDT[{minTradeAmountUSDT}]/[{buyprice}]")
                        if buyvolume<float(minTradeAmount):
                            logger.info(f"【跳过后续任务】目标下单金额小于最小下单金额[{minTradeAmount}]")
                            continue
                        else:
                            logger.info(f"【目标下单金额正常】大于最小下单金额[{minTradeAmount}]")

                        # 【再次验证时间，只在合理时间内下单】
                        thisnow=(datetime.datetime.utcnow()+datetime.timedelta(hours=8)).time()
                        logger.info(f"thisnow,{thisnow}")
                        if (#在特定时间内才执行交易任务【最后3秒不交易，2秒撤单一般能够避免结算后交易的问题】后面看情况再去更改时间
                            ((thisnow>datetime.time(7,58))and(thisnow<datetime.time(7,59,57)))
                            or
                            ((thisnow>datetime.time(15,58))and(thisnow<datetime.time(15,59,57)))
                            or
                            ((thisnow>datetime.time(23,58))and(thisnow<datetime.time(23,59,57)))
                        ):#这个阶段持续按照对应金额买入对应高资金费率的衍生品合约，并且在这个阶段结束后预计下单金额直接重置为空
                        # if True:#【测试】
                            try:
                                # {'marginCoin': 'SUSDT','symbol': 'SEOSSUSDT','holdSide': 'short','openDelegateSize': '0','marginSize': '167.5439','available': '2071','locked': '0','total': '2071','leverage': '10','achievedProfits': '0','openPriceAvg': '0.809','marginMode': 'crossed','posMode': 'hedge_mode','unrealizedPL': '-3.7278','liquidationPrice': '2.244419487762','keepMarginRate': '0.01','markPrice': '0.8108','marginRatio': '0.023008182661','breakEvenPrice': '0.80802978213','totalFee': '','deductedFee': '1.0052634','grant': '','assetMode': 'single','autoMargin': 'off','takeProfit': '','stopLoss': '','takeProfitId': '','stopLossId': '','cTime': '1735460075396','uTime': '1735460075396'}
                                # #【合约下单】# 开多规则为：side=buy,tradeSide=open；开空规则为：side=sell,tradeSide=open；平多规则为：side=buy,tradeSide=close；平空规则为：side=sell,tradeSide=close
                                if thisproductType=="USDT-FUTURES":
                                    logger.info(f"当前为实盘，交易抵押物为USDT")
                                    marginCoin='USDT'
                                elif thisproductType=="SUSDT-FUTURES":
                                    logger.info(f"当前为模拟盘，交易抵押物为SUSDT")
                                    marginCoin='SUSDT'
                                params={#【API下单默认10倍杠杆】
                                    "productType":thisproductType,
                                    #【productType参数说明】
                                    # USDT-FUTURES USDT专业合约
                                    # COIN-FUTURES 混合合约
                                    # USDC-FUTURES USDC专业合约
                                    # SUSDT-FUTURES USDT专业合约模拟盘
                                    # SCOIN-FUTURES 混合合约模拟盘
                                    # SUSDC-FUTURES USDC专业合约模拟盘
                                    "marginMode":"crossed",#仓位模式\isolated: 逐仓\crossed: 全仓【使用逐仓模式避免爆仓，只有全仓状态可以使用联合保证金模式】
                                    "marginCoin":marginCoin,#保证金币种
                                    "tradeSide":"open",#交易类型(仅限双向持仓)\双向持仓模式下必填，单向持仓时不要填\open: 开仓\close: 平仓
                                    # "stpMode":"cancel_taker",#STP模式（自成交预防）\none：不设置STP（默认值）\cancel_taker：取消taker单\cancel_maker：取消maker单\cancel_both：两者都取消
                                    "symbol":str(thissymbol),#"SBTCSUSDT_SUMCBL"
                                    "side":thisside,#方向：PS_BUY现货买入，PS_SELL现货卖出
                                    #【限价单】
                                    "orderType":"limit",#订单类型"limit"、"market"
                                    "price":str(buyprice),# 限价价格# 价格小数位、价格步长可以通过获取交易对信息接口获取
                                    "size":str(buyvolume),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                                    #【市价单】判断剧烈行情是否一定能够成交
                                    # "orderType":"market",#订单类型"limit"、"market"
                                    # "size":str(buyusdt),# 委托数量# 对于Limit和Market-Sell订单，此参数表示base coin数量;# 对于Market-Buy订单，此参数表示quote coin数量；
                                    "force":"gtc",#执行策略（orderType为market时无效）# gtc：普通限价单，一直有效直至取消# post_only：只做 maker 订单# fok：全部成交或立即取消# ioc：立即成交并取消剩余
                                    # "clientOrderId":str(random_string("Cuongitl"))#自定义订单ID
                                    "tpslType":"normal",# normal：普通单（默认值）# tpsl：止盈止损单
                                    # "presetStopSurplusPrice":"",#str止盈值，针对tpsl：止盈止损单
                                    # "presetStopLossPrice":"",#str止损值，针对tpsl：止盈止损单
                                }
                                request_path="/api/v2/mix/order/place-order"
                                #最小下单金额为1USDT
                                thisorder=client._request_with_params(params=params,request_path=request_path,method="POST")
                                logger.info(f"thisorder,{thisorder}")#如果执行了下单这里返回一个order详情{包含下单是否成功的返回值}
                            except Exception as e:
                                logger.info(f"执行下单报错{e}")#这里偶尔会报错，估计是下单完没更新出来最新余额或者是仓位变动导致可开仓余额变化进而导致了实际可下单余额不足
                        else:
                            logger.info(f"未到开仓时间")
    #【超时撤单模块】
    try:#真正的交易机会就很短时间休息久了容易错过机会
        #【休息】避免速度过快限制IP
        thistime=datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        logger.info(f"thistime,{thistime}")
        # # #【获取全部订单】#10次/1s (UID)(仅支持查询90天内数据，超过90天数据可以在网页端导出)
        # # params={}
        # # request_path="/api/v2/spot/trade/history-orders"#现货
        # params={
        #     "productType":thisproductType,
        #     #【productType参数说明】
        #     # USDT-FUTURES USDT专业合约
        #     # COIN-FUTURES 混合合约
        #     # USDC-FUTURES USDC专业合约
        #     # SUSDT-FUTURES USDT专业合约模拟盘
        #     # SCOIN-FUTURES 混合合约模拟盘
        #     # SUSDC-FUTURES USDC专业合约模拟盘
        #     }
        # request_path="/api/v2/mix/order/orders-history"#合约
        # all_orders=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
        # # logger.info(f"all_orders,{all_orders}")
        # pd.DataFrame(all_orders).to_csv("all_orders.csv")
        # #【获取未成交订单】#10次/1s (UID)
        # params={}
        # request_path="/api/v2/spot/trade/unfilled-orders"#现货
        # open_orders=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
        params={
            "productType":thisproductType,
            #【productType参数说明】
            # USDT-FUTURES USDT专业合约
            # COIN-FUTURES 混合合约
            # USDC-FUTURES USDC专业合约
            # SUSDT-FUTURES USDT专业合约模拟盘
            # SCOIN-FUTURES 混合合约模拟盘
            # SUSDC-FUTURES USDC专业合约模拟盘
            }
        request_path="/api/v2/mix/order/orders-pending"#合约
        open_orders=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]['entrustedList']
        logger.info(f"open_orders,{open_orders},{type(open_orders)}")
        if open_orders is not None:#验证不为空【这里仅仅是合约需要验证，现货直接循环就行】
            for thisorder in open_orders:
                logger.info(f"{thisorder}")
                thissymbol=thisorder["symbol"]
                thisorderId=thisorder["orderId"]
                ctime=thisorder["cTime"]#1732973006752创建时间{略快一秒}
                utime=thisorder["uTime"]#1732973006818更新时间{略慢一秒}
                logger.info(f"ctime,{ctime},{type(ctime)}")
                thisdt=datetime.datetime.fromtimestamp(int(ctime)//1000,tz=datetime.timezone.utc)
                logger.info(f"{thisdt}")
                logger.info(f"{thistime-thisdt}")
                if thistime-thisdt>=datetime.timedelta(seconds=2):#订单挂起超时1.5秒撤单
                    logger.info(f"该订单挂起超时执行撤单")
                    # #【现货撤单】#10次/1s (UID)
                    # params={"symbol":thissymbol,
                    #         "orderId":thisorderId,
                    #         }
                    # request_path="/api/v2/spot/trade/cancel-order"
                    params={"symbol":thissymbol,
                            "orderId":thisorderId,
                            "productType":thisproductType,
                            #【productType参数说明】
                            # USDT-FUTURES USDT专业合约
                            # COIN-FUTURES 混合合约
                            # USDC-FUTURES USDC专业合约
                            # SUSDT-FUTURES USDT专业合约模拟盘
                            # SCOIN-FUTURES 混合合约模拟盘
                            # SUSDC-FUTURES USDC专业合约模拟盘
                            }
                    request_path="/api/v2/mix/order/cancel-order"
                    cance_order=client._request_with_params(params=params,request_path=request_path,method="POST")
                    logger.info(f"cance_order,{cance_order}")#撤单成功
                else:
                    logger.info(f"订单挂起时间未达到超时撤单标准")
    except Exception as e:
        logger.info(f"超时撤单报错,{e}")



# #【获取公告数据】
# # annType	String	否	公告类型
# # latest_news: 最新活动
# # coin_listings: 新币上线
# # trading_competitions_promotions: 交易比赛和活动
# # maintenance_system_updates: 维护/系统升级
# # symbol_delisting: 下架资讯
# # startTime	String	否	查询的开始时间，Unix毫秒时间戳，例如1690196141868
# # 按照对外展示时间查询
# # endTime	String	否	查询的结束时间，Unix毫秒时间戳，例如1690196141868
# # 按照对外展示时间查询
# # language	String	是	语言类型
# # zh_CN中文
# # en_US英文
# # 如果传入的语言类型不支持，则返回英文
# params={"language":'zh_CN'}
# request_path="/api/v2/public/annoucements"
# df=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]#quantityScale可能是精度
# df=pd.DataFrame(df)
# logger.info(df)
# df.to_csv("bitget公告.csv")



# #【获取coin信息】
# request_path="/api/v2/spot/public/coins"
# params={}
# bitget_coins_info=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
# bitget_coins_info=pd.DataFrame(bitget_coins_info)
# alldf=pd.DataFrame({})
# for index,thiinfo in bitget_coins_info.iterrows():
#     # logger.info(index,thiinfo)
#     thiscoin=thiinfo["coin"]
#     thistransfer=thiinfo["transfer"]
#     thisdf=pd.DataFrame(thiinfo["chains"])
#     thisdf["coin"]=thiscoin
#     thisdf["transfer"]=thistransfer
#     # logger.info(thisdf)
#     alldf=pd.concat([alldf,thisdf])
# alldf=alldf.rename(columns={
#     # "coin":"base",
#     "transfer":"是否可以划转",
#     "chain":"链名称",#	Array	
#     "needTag":"是否需要tag",#Boolean	
#     "withdrawable":"是否可提现",
#     "rechargeable":"是否可充值",
#     "withdrawFee":"提现手续费",
#     "extraWithdrawFee":"链上转账销毁",#额外收取,链上转账销毁，0.1表示10%
#     "depositConfirm":"充值确认块数",
#     "withdrawConfirm":"提现确认块数",
#     "minDepositAmount":"最小充值数",
#     "minWithdrawAmount":"最小提现数",
#     "browserUrl":"区块浏览器地址",
#     "contractAddress":"币种合约地址",
#     "withdrawStep":"提币步长",
#         # 非0，代表提币数量需满足步长倍数
#         # 为0，代表没有步长倍数的限制
#     "withdrawMinScale":"提币数量精度",
#     "congestion":"链网络拥堵情况",
#         # "normal": 正常
#         # "congested": 拥堵
#     # 返回字段	参数类型	字段说明
#     # coinId	String	币种ID
#     # coin	String	币种名称
#     # transfer	Boolean	是否可以划转
#     # chains	Array	支持的链列表
#     # > chain	String	链名称
#     # > needTag	Boolean	是否需要tag
#     # > withdrawable	Boolean	是否可提现
#     # > rechargeable	Boolean	是否可充值
#     # > withdrawFee	String	提现手续费
#     # > extraWithdrawFee	String	额外收取,链上转账销毁，0.1表示10%
#     # > depositConfirm	String	充值确认块数
#     # > withdrawConfirm	String	提现确认块数
#     # > minDepositAmount	String	最小充值数
#     # > minWithdrawAmount	String	最小提现数
#     # > browserUrl	String	区块浏览器地址
#     # > contractAddress	String	币种合约地址
#     # > withdrawStep	String	提币步长
#     # 非0，代表提币数量需满足步长倍数
#     # 为0，代表没有步长倍数的限制
#     # > withdrawMinScale	String	提币数量精度
#     # > congestion	String	链网络拥堵情况
#     # normal: 正常
#     # congested: 拥堵
#     })
# logger.info(alldf,type(alldf))
# alldf.to_csv("bitget币种信息symbol.csv")



# #【获取symbol详情】这个不需要详情因为不参与交易
# request_path="/api/v2/spot/public/symbols"
# params={}
# bitget_symbols_info=client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
# bitget_symbols_info=pd.DataFrame(bitget_symbols_info)
# # #获取交易对信息
# # url="https://api.bitget.com/api/v2/spot/public/symbols"
# # bitget_symbols_info=pd.DataFrame(requests.get(url).json()["data"])
# bitget_symbols_info=bitget_symbols_info.rename(columns={
#     # symbol:交易对名称
#     "baseCoin":"基础币",#如交易对"BTCUSDT"中的"BTC"
#     "quoteCoin":"计价货币",#例如交易对"BTCUSDT"中的"USDT"
#     "minTradeAmount":"最小交易数量",
#     "maxTradeAmount":"最大交易数量",
#     "takerFeeRate":"默认吃单手续费率",#可被个人交易手续费率覆盖
#     "makerFeeRate":"默认挂单手续费率",#可被个人交易手续费率覆盖
#     "pricePrecision":"价格精度",
#     "quantityPrecision":"数量精度",
#     "quotePrecision":"右币精度",
#     "minTradeUSDT":"最小USDT交易额",
#     "status":"上架状态",
#         # offline: 维护
#         # gray: 灰度
#         # online: 上线
#         # halt: 停盘
#     "buyLimitPriceRatio":"买入与现价的价差百分比",#小数形式    如 0.05 表示: 5%
#     "sellLimitPriceRatio":"卖出与现价的价差百分比",#小数形式    如 0.05 表示: 5%
#     # 返回字段	参数类型	字段说明
#     # symbol	String	交易对名称
#     # baseCoin	String	基础币，如交易对"BTCUSDT"中的"BTC"
#     # quoteCoin	String	计价货币，例如交易对"BTCUSDT"中的"USDT"
#     # minTradeAmount	String	最小交易数量
#     # maxTradeAmount	String	最大交易数量
#     # takerFeeRate	String	默认吃单手续费率，可被个人交易手续费率覆盖
#     # makerFeeRate	String	默认挂单手续费率，可被个人交易手续费率覆盖
#     # pricePrecision	String	价格精度
#     # quantityPrecision	String	数量精度
#     # quotePrecision	String	右币精度
#     # minTradeUSDT	String	最小USDT交易额
#     # status	String	上架状态
#     # offline: 维护
#     # gray: 灰度
#     # online: 上线
#     # halt: 停盘
#     # buyLimitPriceRatio	String	买入与现价的价差百分比,小数形式
#     # 如 0.05 表示: 5%
#     # sellLimitPriceRatio	String	卖出与现价的价差百分比,小数形式
#     # 如 0.05 表示: 5%
# })
# bitget_symbols_info["coin"]=bitget_symbols_info["symbol"].str.replace("USDT","").replace("USDC","")
# # alldf=bitget_symbols_info.merge(alldf,on="coin")
# logger.info(bitget_symbols_info)
# bitget_symbols_info.to_csv("bitget交易对信息.csv")
