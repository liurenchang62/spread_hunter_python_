# pip install python-bitget 
# pip install asyncio
# 【参考文档】https://bitgetlimited.github.io/apidoc/en/mix/#get-account-list
from pybitget import Client
from pybitget.utils import *
from pybitget.enums import *
from pybitget import logger
logger.add(
    sink=f"log.log",#sink:创建日志文件的路径。
    level="INFO",#level:记录日志的等级,低于这个等级的日志不会被记录。等级顺序为 debug < info < warning < error。设置 INFO 会让 logger.debug 的输出信息不被写入磁盘。
    rotation="00:00",#rotation:轮换策略,此处代表每天凌晨创建新的日志文件进行日志 IO；也可以通过设置 "2 MB" 来指定 日志文件达到 2 MB 时进行轮换。   
    retention="7 days",#retention:只保留 7 天。 ``
    encoding="utf-8",#encoding:编码方式
    enqueue=True,#enqueue:队列 IO 模式,此模式下日志 IO 不会影响 python 主进程,建议开启。
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"#format:定义日志字符串的样式,这个应该都能看懂。
)
import asyncio
import math
#【bitget理财大概一个小时一结算利息】
# 现在市面上很多资管公司的策略是：买入现货吃借币利息，做空期货吃资金费率【专门找两边都有利润的标的做】但是庄家能看对手盘因而感觉未必能稳定盈利
# 配置您的Bitget API密钥和密码短语
api_key = "bg_5e69f9e32e87c9bb8087f97cc6adb910"
api_secret = 'b0682a6e4a0e0c50493a4be19b4f56de4fa81f07d6e7d010a71e1971a7c3bbb4'#默认HMAC方式解码
api_passphrase = "wthWTH00"
client = Client(api_key, api_secret, passphrase=api_passphrase)

#【后面写一个策略期货做空吃资金费率，现货买入吃借币利息】
import requests
import datetime
import pandas as pd
def getmarket():
    now=datetime.datetime.now()
    # 设置参数【其他的url报错403是当前的订阅计划不支持该接口】
    name = "COIN"
    headers={
            'Accepts':'application/json',
            'X-CMC_PRO_API_KEY':'5d4d4a5e-a08b-4a90-9aa4-af5dca02f5a4'
            }
    params={
            'start':'1',
            'limit':'50',
            'convert':'USD'
            }
    url='https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest'
    response = requests.get(url=url,headers=headers,params=params)
    print(response)
    if response.status_code == 200:
        data = response.json()
        # print(data,type(data))
        df=pd.DataFrame(data['data'])
        df["日期"]=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df["代码"]=df["symbol"].astype(str)
        df["总市值"]=df['quote'].apply(lambda x : x['USD']['market_cap'])
        df["流通量"]=df["circulating_supply"].astype(float)
        df["发行量"]=df["total_supply"].astype(float)
        df["最大发行量"]=df["max_supply"].astype(float)
        df = df.drop([
            # 'self_reported_circulating_supply',
            # 'self_reported_market_cap',
            # 'tvl_ratio',
            "symbol",
            "circulating_supply",
            "total_supply",
            "max_supply",
            ],axis=1) # 删除掉干扰列
        print(df)
        # df.to_csv("__COIN基本面.csv")
    #【注意代码和总市值的处理】
    droplist=["USDT","USDC"]
    df=df[~df["代码"].isin(droplist)]
    # df['市值比值'] = df['总市值'] / df['总市值'].shift(1)
    dfone=df.nlargest(15, '总市值')
    # dfone.to_csv("dfone.csv")
    dftwo=df.nlargest(25, '总市值')
    # dftwo.to_csv("dftwo.csv")
    # print(df)
    # print(df["代码"].tolist())
    return dfone,dftwo

#【获取现货账户余额】
def getspotbalance(coin):
    params = {"coin":coin}
    request_path="/api/v2/spot/account/assets"
    res=client._request_with_params(params=params,request_path=request_path,method="GET",)["data"]
    # logger.info(f"res现货资产余额,{type(res)},{res}")
    return res
# spotbalance=getspotbalance(coin="USDT")
# usdtbalance=[balance for balance in spotbalance if balance["coin"]=="USDT"][0]["available"]
# logger.info(f"usdtbalance,{usdtbalance},{type(usdtbalance)}")

#【获取理财产品列表】这里只要活期存款
def getsavingslist(coin):#10次/1s (Uid)
    request_path="/api/v2/earn/savings/product"
    params = {"filter":"all",#筛选条件是否可申购
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

def postmessage(text):
    BASEURL = 'http://wxpusher.zjiecode.com/api'
    #【查询订阅用户数量】
    pagenum=1
    payload = {
        'appToken': "AT_tFRZgjToc6XnG5dzR2MGyv1DzECNYOIU",
        'page': str(pagenum),
        'pageSize': "50",
    }
    query_user=requests.get(url=f'{BASEURL}/fun/wxuser', params=payload).json()
    # logger.info(f"{query_user}")
    uidslist=[]
    if len(query_user["data"]["records"])>0:
        for query in query_user["data"]["records"]:
            logger.info(f'{query["uid"]}')
            uidslist.append(query["uid"])
    # logger.info(f"{uidslist}")
    #【推送消息】
    payload = {
        'appToken': "AT_tFRZgjToc6XnG5dzR2MGyv1DzECNYOIU",
        'content': str(text),#文本消息
        'topicIds':["12417"],
        # 'uids': ["UID_qkmjMTBknX0I5ZZoVY3IBFv7WVV1"],#消息单发
        'uids':uidslist,#消息群发
    }
    requests.post(url=f'{BASEURL}/send/message', json=payload).json()

async def main():#bitget交易所的频率限制一般是每秒10次/（IP）、20次/（UID）
    tradenum=0
    #无论牛市熊市上市币安都是好事：合约上线{英文公告叫做Add}，现货上市{英文公告叫做List}，但是容量不大{4w美金能打出来60%的滑点}
    #香港IP无法访问换成美国或者新加坡的就好，一个IP还有访问次数限制，需要多个ip组合
    while True:#每一轮任务执行时间比较短主要耗时在time.sleep上了
        if tradenum>100:
            print("交易次数超过100次，停止交易")
            break
        #【先执行休息避免中间报错导致休息时间受影响，因为访问过于频繁导致IP封禁】避免速度过快限制IP
        time.sleep(3.5)#2秒一次容易抓不到公告【报错空值】，2.5秒一次【报错减少】，3秒一次【继续减少】，3.5秒一次
        try:#真正的交易机会就很短时间休息久了容易错过机会
            thistime=datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            logger.info(f"thistime,{thistime}")
            # #【获取全部订单】#10次/1s (UID)(仅支持查询90天内数据，超过90天数据可以在网页端导出)
            # params={}
            # request_path="/api/v2/spot/trade/history-orders"
            # all_orders = client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
            # logger.info(f"all_orders,{all_orders}")
            #【获取未成交订单】#10次/1s (UID)
            params={}
            request_path="/api/v2/spot/trade/unfilled-orders"
            open_orders = client._request_with_params(params=params,request_path=request_path,method="GET")["data"]
            logger.info(f"open_orders,{open_orders}")
            for thisorder in open_orders:
                logger.info(f"{thisorder}")
                thissymbol=thisorder["symbol"]
                thisorderId=thisorder["orderId"]
                ctime=thisorder["cTime"]#1732973006752创建时间{略快一秒}
                utime=thisorder["uTime"]#1732973006818更新时间{略慢一秒}
                logger.info(f"ctime,{ctime},{type(ctime)}")
                thisdt = datetime.datetime.fromtimestamp(int(ctime)//1000, tz=datetime.timezone.utc)
                logger.info(f"{thisdt}")
                logger.info(f"{thistime-thisdt}")
                if thistime-thisdt>=datetime.timedelta(seconds=3):
                    logger.info("该订单挂起超时执行撤单")
                    #【现货撤单】#10次/1s (UID)
                    params={"symbol":thissymbol,
                            "orderId":thisorderId,
                            }
                    request_path="/api/v2/spot/trade/cancel-order"
                    cance_order = client._request_with_params(params=params,request_path=request_path,method="POST")
                    logger.info(f"cance_order,{cance_order}")#撤单成功
        except Exception as e:
            logger.info(f"撤单报错,{e}")

        #【使用tru、except模式之后代码即便报错也不会导致进程终止】
        #【多个进程任务同时监控进行交易的情况下一个任务失败了但是没有导致订单错乱，理财申购上其他任务前后脚下出去了但是直接返回下单失败而没有报错】
        #【while true下下了几百笔金额溢出的失败订单，并没有导致其他模块受限说明频率限制可能不是一个字段超频就会导致整个账户或者IP无法使用】
        tradenum+=1
        logger.info(f"当前交易轮次为{tradenum}")

        thistime=datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        logger.info(f"thistime,{thistime}")
        if thistime.date()>=datetime.date(2025,12,31):
            print("熊市结束停止交易存入理财",thistime.date())

            thisproductType="USDT-FUTURES"#【实盘】
            absrate=0.003#【实盘】
            # thisproductType="SUSDT-FUTURES"#【模拟盘】
            # absrate=-10#【模拟盘】之前这个值为0的时候容易遇到盘口价差过大导致默认不执行交易的问题

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

            break
        else:
            print("继续交易",thistime.date())
            dfone,dftwo=getmarket()
            print(dfone)
            print(dftwo)
            

# 【github action能够最大程度避免IP报错】main这个异步函数的作用是处理公告监控问题
if __name__ == '__main__':
    # 运行主函数【使用异步可以规避github action的时间限制问题】
    asyncio.run(main())
