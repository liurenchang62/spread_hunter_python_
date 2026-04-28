# 使用eth_defi库执行ETH的链上交易

#【日志详情】
# pip install loguru # 这个框架可以解决中文不显示的问题
from loguru import logger 
logger.add(
    sink=f"价差.log",#sink: 创建日志文件的路径。
    # sink=f"/home/wth000/gitee/价差.log",#sink: 创建日志文件的路径。
    level="INFO",#level: 记录日志的等级,低于这个等级的日志不会被记录。等级顺序为 debug < info < warning < error。设置 INFO 会让 logger.debug 的输出信息不被写入磁盘。
    rotation="00:00",#rotation: 轮换策略,此处代表每天凌晨创建新的日志文件进行日志 IO；也可以通过设置 "2 MB" 来指定 日志文件达到 2 MB 时进行轮换。   
    retention="7 days",#retention: 只保留 7 天。 
    # compression="zip",#compression: 日志文件较大时会采用 zip 进行压缩。
    encoding="utf-8",#encoding: 编码方式
    enqueue=True,#enqueue: 队列 IO 模式,此模式下日志 IO 不会影响 python 主进程,建议开启。
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"#format: 定义日志字符串的样式,这个应该都能看懂。
)

#【消息推送】
import time
import datetime
import pandas as pd
import numpy as np
import hmac
import hashlib
import base64
import urllib.parse
import requests
# #公司群
# secret='SECdcb4cb543702bd9d50b68d46bf315f69dc8bc38b095d3b10ca9cc60bb35f23f9'#加签密钥
# access_token="0b941cdd927c3e47a915cb02b914f29bdc77ca5890a97f70ccca53930385a882"#机器人token
#个人群
secret="SEC2b6e72ba7cd36ae3f1fd566a17bdcc323c1d965c6c77e565d8f4d0cd682290b8"
access_token="f5a623f7af0ae156047ef0be361a70de58aff83b7f6935f4a5671a626cf42165"
def postmessage(title,mes,access_token,secret):
    timestamp=str(round(time.time()*1000))
    secret_enc=secret.encode('utf-8')
    string_to_sign='{}\n{}'.format(timestamp,secret)
    string_to_sign_enc=string_to_sign.encode('utf-8')
    hmac_code=hmac.new(secret_enc,string_to_sign_enc,digestmod=hashlib.sha256).digest()
    sign=urllib.parse.quote_plus(base64.b64encode(hmac_code))
    print(timestamp)
    print(sign)
    # conda install tabulate
    if type(mes)==pd.DataFrame:
        print("格式为df")
        message=mes.to_markdown()
    else:
        print("格式为字符")
        message=mes
    webhook=f"https://oapi.dingtalk.com/robot/send?access_token={access_token}&timestamp={timestamp}&sign={sign}"
    test=requests.post(
        webhook,
        json={
            "msgtype":"markdown",
            "markdown":{"title":title,"text":message},
        },
        #可能是文件大小受限制无法发送
        # json={
        #     "msgtype":"file",
        #     "file":{
        #         "media_id":"",
        #         "file_name":"data.csv",
        #         "file_type":"csv",
        #         "content":mes.to_csv(index=False)
        #     }
        # },
    )
    print(test)

#gate对代币处理的时间比较长，实盘建议不走gate

import pandas as pd
import datetime
import requests
# getaddress=True#是否重新获取代币充值地址
getaddress=False#是否重新获取代币充值地址
if getaddress==True:
    # cexnames=["binance","mexc","bitget","gate"]#目前四大交易所分别是币安 OKX Bybit Bitget（其中bitget现货流动性最好）
    cexnames=["gate"]
    for cexname in cexnames:
        if cexname=="gate":#【模拟IP：新加坡、台北】使用鼠标悬浮抓数据不够稳定
            gate_host_prefix="https://api.gateio.ws/api/v4"#实盘
            gate_headers={'Accept':'application/json','Content-Type':'application/json'}
            # 比特儿平台内期现套利
            print("选股开始",datetime.datetime.now())

            # #查询充值地址
            # host="https://api.gateio.ws"
            # prefix="/api/v4"
            # headers={'Accept':'application/json','Content-Type':'application/json'}
            # url='/wallet/deposit_address'
            # query_param='currency=USDT'
            # # `gen_sign` 的实现参考认证一章
            # sign_headers=gen_sign('GET',prefix+url,query_param)
            # headers.update(sign_headers)
            # r=requests.request('GET',host+prefix+url+"?"+query_param,headers=headers)
            # print(r.json())

            # #查询提现状态
            # host="https://api.gateio.ws"
            # prefix="/api/v4"
            # headers={'Accept':'application/json','Content-Type':'application/json'}
            # url='/wallet/withdraw_status'
            # query_param=''
            # # `gen_sign` 的实现参考认证一章
            # sign_headers=gen_sign('GET',prefix+url,query_param)
            # headers.update(sign_headers)
            # r=requests.request('GET',host+prefix+url,headers=headers)
            # print(r.json())

            #获取合约交易对【只要非杠杆代币】
            gate_info=pd.DataFrame(requests.request('GET',gate_host_prefix+'/spot/currencies',headers=gate_headers).json())
            gate_info=gate_info[gate_info["trade_disabled"]==False]#去掉暂停交易的标的
            gate_info=gate_info[gate_info["delisted"]==False]#去掉已经下架的标的
            gate_info=gate_info[~gate_info['chain'].apply(lambda x:any(c.isdigit() for c in str(x)))]#过滤杠杆代币
            gate_info=gate_info.rename(columns={
                "currency":"base",#币种名称
                "delisted":"是否下架",
                "withdraw_disabled":"是否暂停提现",
                "withdraw_delayed":"提现是否延迟",
                "deposit_disabled":"是否暂停充值",
                "trade_disabled":"是否暂停交易",
                })
            gate_info=gate_info[[
                "base",
                "是否下架",
                "是否暂停提现",
                "提现是否延迟",
                "是否暂停充值",
                "是否暂停交易",
                ]]
            gate_info.to_csv("gate_info.csv")
            alldf=pd.DataFrame({})
            for base in gate_info["base"].tolist():
                try:#应该是有一些退市的标的，或者干脆没有链
                    #查询支持的链【需要根据代币名称循环拼接才行】
                    query_param=f'currency={base}'
                    currency_chains=pd.DataFrame(requests.request('GET',gate_host_prefix+'/wallet/currency_chains'+"?"+query_param,headers=gate_headers).json())
                    currency_chains["base"]=base
                    print(currency_chains,type(currency_chains))
                    alldf=pd.concat([alldf,currency_chains])
                    # print(alldf)
                except Exception as e:
                    print(e)
            alldf=alldf.rename(columns={
                    # "chain":"链名称",#string
                    "name_cn":"链的中文名称",#string
                    "name_en":"链的英文名称",#string
                    "contract_address":"智能合约地址",#如果没有地址则为空字串string
                    "is_disabled":"是否禁用",#0 表示未禁用integer(int32)
                    "is_deposit_disabled":"充值是否禁用",#0 表示未禁用integer(int32)
                    "is_withdraw_disabled":"提现是否禁用",#0 表示未禁用integer(int32)	
                    "decimal":"提币精度",#string
                    # » chain	string	链名称
                    # » name_cn	string	链的中文名称
                    # » name_en	string	链的英文名称
                    # » contract_address	string	智能合约地址，如果没有地址则为空字串
                    # » is_disabled	integer(int32)	是否禁用，0 表示未禁用
                    # » is_deposit_disabled	integer(int32)	充值是否禁用，0 表示未禁用
                    # » is_withdraw_disabled	integer(int32)	提现是否禁用，0 表示未禁用
                    # » decimal	string	提币精度
                })
            alldf=alldf[[
                "base",
                "chain",
                "链的中文名称",
                "链的英文名称",
                "智能合约地址",
                "是否禁用",
                "充值是否禁用",
                "提现是否禁用",
                "提币精度",#string
                ]]
            gate_info=gate_info.merge(alldf,on="base")
            print(gate_info)
            gate_info.to_csv("gate_info.csv")

            gate_spot=pd.DataFrame(requests.request('GET',gate_host_prefix+"/spot/currency_pairs",headers=gate_headers).json())
            gate_spot=gate_spot[gate_spot["trade_status"]=="tradable"]#只保留可以交易的标的【还有一种sellable是临近上市的标的】
            #拼接上是否冲提币数据
            gate_spot=gate_spot[[                
                "id",#币种名称
                "base",#就是去掉USDT这些后缀了
                "fee",
                "quote",
                "min_base_amount",
                "min_quote_amount",
                "max_base_amount",
                "max_quote_amount",
                "amount_precision",
                "precision",
                "trade_status",
                "sell_start",
                "buy_start",
                ]]
            gate_spot=gate_spot.merge(gate_info,on="base")
            gate_spot=gate_spot.rename(columns={
                "id":"symbol",#币种名称
                "base":"交易货币",#就是去掉USDT这些后缀了
                "fee":"交易费率",
                "quote":"计价货币",
                "min_base_amount":"交易货币最低交易数量",
                "min_quote_amount":"计价货币最低交易数量",
                "max_base_amount":"交易货币最大交易数量",
                "max_quote_amount":"计价货币最大交易数量",
                "amount_precision":"数量精度",
                "precision":"价格精度",#int
                "trade_status":"交易状态",
                    # - untradable:不可交易
                    # - buyable:可买
                    # - sellable:可卖
                    # - tradable:买卖均可交易
                "sell_start":"允许卖出时间",#int(64)秒级 Unix 时间戳
                "buy_start":"允许买入时间",#int(64)秒级 Unix 时间戳
                # 名称	类型	必选	限制	描述
                # id	string	false	none	交易对
                # base	string	false	none	交易货币#就是去掉USDT这些后缀了
                # quote	string	false	none	计价货币
                # fee	string	false	none	交易费率
                # min_base_amount	string	false	none	交易货币最低交易数量，null 表示无限制
                # min_quote_amount	string	false	none	计价货币最低交易数量，null 表示无限制
                # max_base_amount	string	false	none	交易货币最大交易数量，null 表示无限制
                # max_quote_amount	string	false	none	计价货币最大交易数量，null 表示无限制
                # amount_precision	integer	false	none	数量精度
                # precision	integer	false	none	价格精度
                # trade_status	string	false	none	交易状态
                    # - untradable:不可交易
                    # - buyable:可买
                    # - sellable:可卖
                    # - tradable:买卖均可交易
                # sell_start	integer(int64)	false	none	允许卖出时间，秒级 Unix 时间戳
                # buy_start	integer(int64)	false	none	允许买入时间，秒级 Unix 时间戳
                })
            gate_spot.to_csv("gate_spot.csv")
            
            # 【添加成交额限制】添加之后SOL上总共100+币基本无价差，添加之后SOL上总共50+币有一个有价差的
            symbols=gate_spot["symbol"].tolist()
            #获取所有现货交易对tick信息
            gate_spot_ticker=pd.DataFrame(requests.request('GET',gate_host_prefix+'/spot/tickers',headers=gate_headers).json())#现货ticker
            gate_spot_ticker=gate_spot_ticker[["currency_pair","last","quote_volume","lowest_ask","highest_bid",]]
            gate_spot_ticker=gate_spot_ticker[gate_spot_ticker["currency_pair"].isin(symbols)]#只要非杠杆代币
            gate_spot_ticker=gate_spot_ticker.rename(columns={
                    "currency_pair":"symbol",
                    "last":"现价",
                    "quote_volume":"24小时成交额",#计价货币
                    # "base_volume":"24小时成交量",#基础货币
                    # "change_percentage":"涨跌幅",
                    "lowest_ask":"ask1",
                    "highest_bid":"bid1",
                })
            gate_spot_ticker=gate_spot_ticker.merge(gate_spot,on="symbol")
            gate_spot_ticker["24小时成交额"]=gate_spot_ticker["24小时成交额"].astype(float)
            # gate_spot_ticker=gate_spot_ticker[gate_spot_ticker["24小时成交额"]>100000]
            gate_spot_ticker.to_csv(f"代币详情{cexname}.csv")

        if cexname=="mexc":#【模拟IP：新加坡、台北】速度最快
            # mexc数据获取
            # pip install pymexc#可能要求python11以上版本
            from pymexc import spot,futures
            api_key="mx0vglxeUz5UQL4wlI"
            api_secret="81a7ca1cf2d8497fb4d95e43552cc5ad"
            # 现货SPOT V3
            # initialize HTTP client
            spot_client=spot.HTTP(api_key=api_key,api_secret=api_secret)
            # # initialize WebSocket client
            # ws_spot_client=spot.WebSocket(api_key=api_key,api_secret=api_secret)
            # # 现货交易对详情
            mexc_spot_info=spot_client.exchange_info()
            mexc_spot_info=pd.DataFrame(mexc_spot_info["symbols"])
            mexc_spot_info=mexc_spot_info.rename(columns={
                "status":"状态",
                "baseAsset":"交易币",#String	
                "baseAssetPrecision":"交易币精度",#Int	
                "quoteAsset":"计价币",#String	
                "quotePrecision":"计价币价格精度",#Int	
                "quoteAssetPrecision":"计价币资产精度",#Int	
                "baseCommissionPrecision":"交易币手续费精度",#Int	
                "quoteCommissionPrecision":"计价币手续费精度",#Int	
                "orderTypes":"订单类型",#Array
                # "quoteOrderQtyMarketAllowed":"是否允许市价委托",#Boolean【这个可能取消了】
                "isSpotTradingAllowed":"是否允许api现货交易",#Boolean	
                "isMarginTradingAllowed":"是否允许api杠杆交易",#Boolean	
                "permissions":"权限",#Array
                "maxQuoteAmount":"最大下单金额",#String	
                "makerCommission":"marker手续费",#String	
                "takerCommission":"taker手续费",#String	
                "quoteAmountPrecision":"最小下单金额",#string	
                "baseSizePrecision":"最小下单数量",#string	
                "quoteAmountPrecisionMarket":"市价最小下单金额",#String
                "maxQuoteAmountMarket":"市价最大下单金额",#String
                "tradeSideType":"交易对可交易方向",#String	1 - 全部， 2 - 仅买单， 3 - 仅卖单，4 - 关闭
                
                # timezone	string	时区
                # serverTime	long	服务器时间
                # rateLimits	Array	频率限制
                # exchangeFilters	Array	过滤器
                # symbol	String	交易对
                # status	String	状态:1 - 开放， 2 - 暂停， 3 - 下线
                # baseAsset	String	交易币
                # baseAssetPrecision	Int	交易币精度
                # quoteAsset	String	计价币
                # quotePrecision	Int	计价币价格精度
                # quoteAssetPrecision	Int	计价币资产精度
                # baseCommissionPrecision	Int	交易币手续费精度
                # quoteCommissionPrecision	Int	计价币手续费精度
                # orderTypes	Array	订单类型
                # quoteOrderQtyMarketAllowed	Boolean	是否允许市价委托
                # isSpotTradingAllowed	Boolean	是否允许api现货交易
                # isMarginTradingAllowed	Boolean	是否允许api杠杆交易
                # permissions	Array	权限
                # maxQuoteAmount	String	最大下单金额
                # makerCommission	String	marker手续费
                # takerCommission	String	taker手续费
                # quoteAmountPrecision	string	最小下单金额
                # baseSizePrecision	string	最小下单数量
                # quoteAmountPrecisionMarket	string	市价最小下单金额
                # maxQuoteAmountMarket	String	市价最大下单金额
                # tradeSideType	String	交易对可交易方向:1 - 全部， 2 - 仅买单， 3 - 仅卖单，4 - 关闭
                })
            mexc_spot_info=mexc_spot_info[[
                "symbol",
                "状态",
                "交易币","交易币精度",
                "计价币","计价币价格精度",
                "计价币资产精度",
                "交易币手续费精度",
                "计价币手续费精度",
                "订单类型",
                # "是否允许市价委托",
                "是否允许api现货交易",
                "是否允许api杠杆交易",
                "权限",
                "最大下单金额",
                "marker手续费","taker手续费",
                "最小下单金额","最小下单数量",
                "市价最小下单金额","市价最大下单金额",
                "交易对可交易方向",
                ]]
            mexc_spot_info["coin"]=mexc_spot_info["symbol"].str.replace("USDT","").replace("USDC","").replace("ETH","")
            mexc_spot_info.to_csv(f"{cexname}现货交易对.csv")#这个是各个标的的详情

            #账号详情
            account_information=spot_client.account_information()
            # canTrade	是否可交易
            # canWithdraw	是否可提现
            # canDeposit	是否可充值
            # updateTime	更新时间
            # accountType	账户类型
            # balances	余额
            #     asset	资产币种
            #     free	可用数量
            #     locked	冻结数量
            #     permissions	权限
            print("账号详情",account_information)
            #代币详情（是否可提币）
            mexc_currency_info=spot_client.get_currency_info()
            mexc_currency_info_df=pd.DataFrame({})
            for info in mexc_currency_info:
                # print(info,type(info))
                thisdf=pd.DataFrame(info["networkList"])
                mexc_currency_info_df=pd.concat([mexc_currency_info_df,thisdf])
            mexc_currency_info_df=mexc_currency_info_df.rename(columns={
                # "coin":"代币ID"
                "depositEnable":"是否可充值",
                "withdrawEnable":"是否可提币",
                "withdrawFee":"提币手续费",
                "withdrawMax":"最大提币限额",
                "withdrawMin":"最小提币限额",
                "contract":"智能合约地址",#抹茶的API里面是给智能合约地址的
                # "network":"chain",#币种所支持的网络（旧参数，即将下线，建议提币使用提币新接口）
                "netWork":"chain",#币种所支持的网络（新参数，适用于提币新接口）
            })
            mexc_currency_info_df=mexc_currency_info_df[["coin",
                                            "是否可充值","是否可提币",
                                            "提币手续费","最大提币限额",
                                            "最小提币限额","智能合约地址",
                                            "chain",]]
            mexc_currency_info_df.to_csv("mexc_currency_info_df.csv")
            print(mexc_currency_info_df)

            mexc_currency_info_df=mexc_currency_info_df.merge(mexc_spot_info,on="coin")


            # #全部ticker【只有实时价格和代币名称】
            # mexc_spot_ticker=spot_client.ticker_price()
            # mexc_spot_ticker=pd.DataFrame(mexc_spot_ticker)
            # mexc_spot_ticker["price"]=mexc_spot_ticker["price"].astype(float)
            # # mexc_spot_ticker.to_csv(f"{cexname}ticker.csv")#这个是各个标的的详情
            # print(mexc_spot_ticker)
            #全部ticker_24h【包含买一卖一】
            mexc_spot_ticker=spot_client.ticker_24h()
            mexc_spot_ticker=pd.DataFrame(mexc_spot_ticker)
            mexc_spot_ticker=mexc_spot_ticker.rename(columns={
                "volume":"成交量",
                "quoteVolume":"24小时成交额",
                # symbol	交易对
                # priceChange	价格变化
                # priceChangePercent	价格变化比
                # prevClosePrice	前一收盘价
                # lastPrice	最新价
                # lastQty	最新量
                # bidPrice	买盘价格
                # bidQty	买盘数量
                # askPrice	卖盘价格
                # askQty	卖盘数量
                # openPrice	开始价
                # highPrice	最高价
                # lowPrice	最低价
                # volume	成交量
                # quoteVolume	成交额
                # openTime	开始时间
                # closeTime	结束时间
                })
            mexc_spot_ticker=mexc_spot_ticker[["symbol","24小时成交额"]]
            mexc_spot_ticker.to_csv(f"{cexname}ticker24h.csv")#这个是各个标的的详情
            mexc_spot_ticker=mexc_spot_ticker.merge(mexc_currency_info_df,on="symbol")
            mexc_spot_ticker["24小时成交额"]=mexc_spot_ticker["24小时成交额"].astype(float)
            # mexc_spot_ticker=mexc_spot_ticker[mexc_spot_ticker["24小时成交额"]>100000]
            mexc_spot_ticker.to_csv(f"代币详情{cexname}.csv")
            # #充值地址
            # generate_deposit_address
            # deposit_address

        if cexname=="binance":#【模拟IP：台北】
            # 获取币安数据
            from binance.client import Client
            # 创建Binance客户端【实盘服务器】
            binanceclient=Client(api_key="0jmNVvNZusoXKGkwnGLBghPh8Kmc0klh096VxNS9kn8P0nkAEslVUlsuOcRoGrtm",api_secret="PbSWkno1meUckhmkLyz8jQ2RRG7KgmZyAWhIF0qPdCJrmDSFxoxGdMG5gZeYYCgy")
            # 这里应该是获取的现货余额
            binance_spot_balances=binanceclient.get_account()
            binance_spot_balances=pd.json_normalize(binance_spot_balances["balances"])
            binance_spot_balances=binance_spot_balances[binance_spot_balances["asset"]=="USDT"]
            # binance_spot_balances["free"]=binance_spot_balances["free"].astype(float)
            # binance_spot_balances=binance_spot_balances[~(binance_spot_balances["free"]==0)]
            print("总余额",binance_spot_balances)
            # #获取现货余额
            # spot_balance=binanceclient.get_asset_balance(asset="USDT")
            # binance_spot_amount=float(spot_balance["free"])
            # print(f"现货USDT余额",binance_spot_amount)
            # #获取合约余额
            # futures_balance=binanceclient.futures_account_balance()#获取永续合约账户资产余额
            # futures_balance_df=pd.json_normalize(futures_balance)#永续合约账户资产余额转DataFrame
            # futures_balance_df=futures_balance_df[futures_balance_df["asset"]=="USDT"]#只计算USDT本位合约的资产信息
            # binance_futures_amount=float(futures_balance_df["balance"].values[0])
            # print(f"合约USDT余额",binance_futures_amount)
            # #获取充值地址
            # res=binanceclient.get_deposit_address(coin="BTC")#获取的地址是deposit/address
            # print(res)
            # #所有币的信息【包含合约地址】
            # binance_all_coins_info=pd.json_normalize(binanceclient.get_all_coins_info())
            # binance_all_coins_info["智能合约地址"]=binance_all_coins_info["networkList"].apply(lambda x:x[-1])
            binance_all_coins_info=pd.json_normalize(binanceclient.get_all_coins_info(),record_path="networkList")
            binance_all_coins_info=binance_all_coins_info.rename(columns={
                # "coin"
                "name":"代币名称",
                "depositDesc":"充值维护信息",#仅在充值关闭时返回"Wallet Maintenance,Deposit Suspended"
                "withdrawDesc":"提现维护信息",#仅在提现关闭时返回"Wallet Maintenance,Withdrawal Suspended"
                "minConfirm":"上账所需最新确认数",
                "unLockConfirm":"解锁需要的确认数",
                "network":"chain",
                "sameAddress":"是否需要memo",#true
                "estimatedArrivalTime":"预计到账时间",#25
                "busy":"网络是否繁忙",#false,
                "contractAddressUrl":"合约浏览器URL",#"https://bscscan.com/token/"
                "contractAddress":"智能合约地址",#"0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c"
            })
            binance_all_coins_info=binance_all_coins_info[[
                "coin",
                "代币名称",
                "充值维护信息",
                "提现维护信息",
                "上账所需最新确认数",
                "解锁需要的确认数",
                "chain",
                "是否需要memo",
                "预计到账时间",
                "网络是否繁忙",
                "合约浏览器URL",
                "智能合约地址",
                ]]
            binance_all_coins_info.to_csv("binance_all_coins_info.csv")
            #现货交易对详情
            binance_spot_info_df=pd.json_normalize(binanceclient.get_exchange_info(),record_path="symbols")
            binance_spot_info_df=binance_spot_info_df[binance_spot_info_df["status"]=="TRADING"]#只要仍然在交易的代币
            #TRADING状态是可交易，PENDING_TRADING状态是待上市，SETTLING状态是退市
            binance_spot_info_df=binance_spot_info_df[binance_spot_info_df["quoteAsset"]=="USDT"]#以USDT结算
            binance_spot_info_df=binance_spot_info_df[binance_spot_info_df['symbol'].str.endswith('USDT')]#以USDT结尾
            binance_spot_info_df=binance_spot_info_df[~binance_spot_info_df['symbol'].apply(lambda x:any(c.isdigit() for c in str(x)))] # 去掉交割合约等包含数字的合约标的
            binance_spot_info_df["minPrice"]=binance_spot_info_df["filters"].apply(lambda x:x[0]["minPrice"])#最小价格
            binance_spot_info_df["minQty"]=binance_spot_info_df["filters"].apply(lambda x:x[1]["minQty"])#最小数量
            binance_spot_info_df["tickSize"]=binance_spot_info_df["filters"].apply(lambda x:x[0]["tickSize"])#价格步长
            binance_spot_info_df["stepSize"]=binance_spot_info_df["filters"].apply(lambda x:x[1]["stepSize"])#数量步长
            binance_spot_info_df=binance_spot_info_df[["symbol","status",
                                                    "quoteAsset",
                                                    "minPrice","minQty",
                                                    "tickSize","stepSize"]]
            binance_spot_info_df=binance_spot_info_df.rename(columns={
                    # "symbol":"代码",
                    "status":"状态",
                    "quoteAsset":"计价代币",
                    "minQty":"最小数量",
                    "tickSize":"价格步长",
                    "stepSize":"数量步长",
                })
            binance_spot_info_df["coin"]=binance_spot_info_df["symbol"].str.replace("USDT","").replace("USDC","").replace("ETH","")
            binance_spot_info_df=binance_spot_info_df.merge(binance_all_coins_info,on="coin")
            binance_spot_info_df.to_csv("binance_spot_info_df.csv")
            binance_spot_usdt_symbols=binance_spot_info_df["symbol"].tolist()
            # 现货ticker
            binance_spot_ticker=pd.json_normalize(binanceclient.get_ticker())
            binance_spot_ticker=binance_spot_ticker[binance_spot_ticker["symbol"].isin(binance_spot_usdt_symbols)]
            binance_spot_ticker=binance_spot_ticker.rename(columns={
                    # "symbol":"代码",
                    "lastPrice":"现价",
                    "quoteVolume":"24小时成交额",#计价货币
                    "volume":"24小时成交量",#基础货币
                    # "priceChangePercent":"涨跌幅",
                    "closeTime":"标记时间",
                    "askPrice":"asks1p",
                    "askQty":"asks1v",
                    "bidPrice":"bids1p",
                    "bidQty":"bids1v",
                })
            binance_spot_ticker.to_csv("binance_spot_ticker.csv")
            print("现货ticker",binance_spot_ticker)
            binance_spot_ticker=binance_spot_ticker[["symbol","现价","24小时成交额","24小时成交量","标记时间",]]
            binance_spot_ticker=binance_spot_ticker.merge(binance_spot_info_df,on="symbol")
            binance_spot_ticker["24小时成交额"]=binance_spot_ticker["24小时成交额"].astype(float)
            # binance_spot_ticker=binance_spot_ticker[binance_spot_ticker["24小时成交额"]>100000]
            binance_spot_ticker.to_csv(f"代币详情{cexname}.csv")

        if cexname=="bitget":
            # # https://github.com/BitgetLimited/v3-bitget-api-sdk【下载SDK】
            # import bitget.v1.mix.order_api as maxOrderApi
            # import bitget.bitget_api as baseApi
            # from bitget.exceptions import BitgetAPIException
            # apiKey="bg_6cdefce0592f0b42e08b49653ea41609"
            # secretKey='730e2773aec3b3f64941d85aa03a97053ad0a4ac0a73ad1328b3f766ddc6854a'
            # passphrase="wthWTH00"
            # # Demo 1:place order
            # maxOrderApi=maxOrderApi.OrderApi(apiKey,secretKey,passphrase)
            # try:
            #     params={}
            #     params["symbol"]="BTCUSDT_UMCBL"
            #     params["marginCoin"]="USDT"
            #     params["side"]="open_long"
            #     params["orderType"]="limit"
            #     params["price"]="27012"
            #     params["size"]="0.01"
            #     params["timInForceValue"]="normal"
            #     response=maxOrderApi.placeOrder(params)
            #     print(response)
            # except BitgetAPIException as e:
            #     print("error:"+e.message)

            hostprefix="https://api.bitget.com/api/v2/"

            #获取币种信息
            url='/spot/public/coins'
            bitget_coins_info=pd.DataFrame(requests.request('GET',hostprefix+url).json()["data"])
            alldf=pd.DataFrame({})
            for index,thiinfo in bitget_coins_info.iterrows():
                # print(index,thiinfo)
                thiscoin=thiinfo["coin"]
                thistransfer=thiinfo["transfer"]
                thisdf=pd.DataFrame(thiinfo["chains"])
                thisdf["coin"]=thiscoin
                thisdf["transfer"]=thistransfer
                # print(thisdf)
                alldf=pd.concat([alldf,thisdf])
            alldf=alldf.rename(columns={
                # "coin":"base",
                "transfer":"是否可以划转",
                # "chain":"链名称",#	Array
                "needTag":"是否需要tag",#Boolean	
                "withdrawable":"是否可提现",
                "rechargeable":"是否可充值",
                "withdrawFee":"提现手续费",
                "extraWithdrawFee":"链上转账销毁",#额外收取,链上转账销毁，0.1表示10%
                "depositConfirm":"充值确认块数",
                "withdrawConfirm":"提现确认块数",
                "minDepositAmount":"最小充值数",
                "minWithdrawAmount":"最小提现数",
                "browserUrl":"区块浏览器地址",
                "contractAddress":"智能合约地址",
                "withdrawStep":"提币步长",
                    # 非0，代表提币数量需满足步长倍数
                    # 为0，代表没有步长倍数的限制
                "withdrawMinScale":"提币数量精度",
                "congestion":"链网络拥堵情况",
                    # "normal":正常
                    # "congested":拥堵

                # 返回字段	参数类型	字段说明
                # coinId	String	币种ID
                # coin	String	币种名称
                # transfer	Boolean	是否可以划转
                # chains	Array	支持的链列表
                # > chain	String	链名称
                # > needTag	Boolean	是否需要tag
                # > withdrawable	Boolean	是否可提现
                # > rechargeable	Boolean	是否可充值
                # > withdrawFee	String	提现手续费
                # > extraWithdrawFee	String	额外收取,链上转账销毁，0.1表示10%
                # > depositConfirm	String	充值确认块数
                # > withdrawConfirm	String	提现确认块数
                # > minDepositAmount	String	最小充值数
                # > minWithdrawAmount	String	最小提现数
                # > browserUrl	String	区块浏览器地址
                # > contractAddress	String	币种合约地址
                # > withdrawStep	String	提币步长
                # 非0，代表提币数量需满足步长倍数
                # 为0，代表没有步长倍数的限制
                # > withdrawMinScale	String	提币数量精度
                # > congestion	String	链网络拥堵情况
                # normal:正常
                # congested:拥堵
                })
            print(alldf,type(alldf))
            # alldf.to_csv("bitget币种信息.csv")

            #获取交易对信息
            url="spot/public/symbols"
            bitget_symbols_info=pd.DataFrame(requests.request('GET',hostprefix+url).json()["data"])
            bitget_symbols_info=bitget_symbols_info.rename(columns={
                # symbol:交易对名称
                "baseCoin":"基础币",#如交易对"BTCUSDT"中的"BTC"
                "quoteCoin":"计价货币",#例如交易对"BTCUSDT"中的"USDT"
                "minTradeAmount":"最小交易数量",
                "maxTradeAmount":"最大交易数量",
                "takerFeeRate":"默认吃单手续费率",#可被个人交易手续费率覆盖
                "makerFeeRate":"默认挂单手续费率",#可被个人交易手续费率覆盖
                "pricePrecision":"价格精度",
                "quantityPrecision":"数量精度",
                "quotePrecision":"右币精度",
                "minTradeUSDT":"最小USDT交易额",
                "status":"上架状态",
                    # offline:维护
                    # gray:灰度
                    # online:上线
                    # halt:停盘
                "buyLimitPriceRatio":"买入与现价的价差百分比",#小数形式    如 0.05 表示:5%
                "sellLimitPriceRatio":"卖出与现价的价差百分比",#小数形式    如 0.05 表示:5%

                # 返回字段	参数类型	字段说明
                # symbol	String	交易对名称
                # baseCoin	String	基础币，如交易对"BTCUSDT"中的"BTC"
                # quoteCoin	String	计价货币，例如交易对"BTCUSDT"中的"USDT"
                # minTradeAmount	String	最小交易数量
                # maxTradeAmount	String	最大交易数量
                # takerFeeRate	String	默认吃单手续费率，可被个人交易手续费率覆盖
                # makerFeeRate	String	默认挂单手续费率，可被个人交易手续费率覆盖
                # pricePrecision	String	价格精度
                # quantityPrecision	String	数量精度
                # quotePrecision	String	右币精度
                # minTradeUSDT	String	最小USDT交易额
                # status	String	上架状态
                # offline:维护
                # gray:灰度
                # online:上线
                # halt:停盘
                # buyLimitPriceRatio	String	买入与现价的价差百分比,小数形式
                # 如 0.05 表示:5%
                # sellLimitPriceRatio	String	卖出与现价的价差百分比,小数形式
                # 如 0.05 表示:5%
            })
            bitget_symbols_info["coin"]=bitget_symbols_info["symbol"].str.replace("USDT","").replace("USDC","")
            bitget_symbols_info=bitget_symbols_info.merge(alldf,on="coin")
            print(bitget_symbols_info)
            # bitget_symbols_info.to_csv("bitget交易对信息.csv")

            #获取行情信息
            url="spot/market/tickers"
            bitget_tickers=pd.DataFrame(requests.request('GET',hostprefix+url).json()["data"])
            bitget_tickers=bitget_tickers.rename(columns={
                # "symbol":"交易对名称",
                "high24h":"24小时最高价",
                "open":"24小时开盘价",
                "lastPr":"最新成交价",
                "low24h":"24小时最低价",
                "quoteVolume":"计价币成交额",
                "baseVolume":"基础币成交额",
                "usdtVolume":"24小时成交额",#USDT
                "bidPr":"买一价",
                "askPr":"卖一价",
                "bidSz":"买一量",
                "askSz":"卖一量",
                "openUtc":"零时区开盘价",
                "ts":"当前时间",#。Unix毫秒时间戳，例如1690196141868
                "changeUtc24h":"UTC0时涨跌幅",# 0.01表示1%
                "change24h":"24小时涨跌幅",# 0.01表示1%

                # 返回字段	参数类型	字段说明
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
            bitget_tickers=bitget_tickers.merge(bitget_symbols_info,on="symbol")
            print(bitget_tickers)
            # bitget_tickers.to_csv("bitget行情信息.csv")

            bitget_tickers["提现手续费（USDT）"]=bitget_tickers["最新成交价"].astype(float)*bitget_tickers["提现手续费"].astype(float)
            # bitget_tickers=bitget_tickers[(bitget_tickers["chain"]=="ERC20")]#只要ERC20代币，从原来的1000交易对变成了500交易对
            print(bitget_tickers["是否可提现"].values[0],type(bitget_tickers["是否可提现"].values[0]))#字符串
            # bitget_tickers=bitget_tickers[(bitget_tickers["是否可提现"]=="true")&(bitget_tickers["是否可充值"]=="true")]#原来将近500交易对，过滤完之后剩下362交易对
            print(bitget_tickers)
            bitget_tickers["24小时成交额"]=bitget_tickers["24小时成交额"].astype(float)
            # bitget_tickers=bitget_tickers[bitget_tickers["24小时成交额"]>100000]
            bitget_tickers.to_csv(f"代币详情{cexname}.csv")

            # #现货资产
            # curl "https://api.bitget.com/api/v2/spot/account/assets?coin=USDT" \
            #    -H "ACCESS-KEY:*******" \
            #    -H "ACCESS-SIGN:*" \
            #    -H "ACCESS-PASSPHRASE:*" \
            #    -H "ACCESS-TIMESTAMP:1659076670000" \
            #    -H "locale:en-US" \
            #    -H "Content-Type:application/json"
            # 参数名	参数类型	是否必须	描述
            # coin	String	否	币种名称,如USDT
            # 该字段用于单币种持仓查询
            # assetType	String	否	资产类型
            # hold_only:持仓币种
            # all:全部币种
            # 该字段用于返回多币种持仓数据。默认值为hold_only
            # 当不传coin，只传assetType时，则返回全部符合条件的币种。当同时传参coin及assetType时，coin优先级更高

            # #账号信息
            # curl "https://api.bitget.com/api/v2/spot/account/info" \
            #    -H "ACCESS-KEY:*******" \
            #    -H "ACCESS-SIGN:*******" \
            #    -H "ACCESS-PASSPHRASE:*****" \
            #    -H "ACCESS-TIMESTAMP:1659076670000" \
            #    -H "locale:en-US" \
            #    -H "Content-Type:application/json"
            # 返回字段	参数类型	字段说明
            # userId	String	用户ID
            # inviterId	String	邀请人UID
            # channelCode	String	渠道邀请码
            # channel	String	渠道
            # ips	String	IP白名单
            # authorities	Array	权限
            # 只读
            # coor 合约订单
            # cpor 合约仓位
            # stor 现货
            # smor 杠杆
            # ttor 跟单
            # wtor 划转
            # taxr 税务
            # chor 子账户
            # p2pr P2P
            # 读写
            # coow 合约订单
            # cpow 合约仓位
            # stow 现货
            # smow 杠杆
            # ttow 跟单
            # wtow 划转
            # wwow 提币
            # chow 子账户
            # p2pw P2P
            # parentId	Int	母账户UID
            # traderType	String	trader 是交易员,not_trader 不是交易员
            # regisTime	String	注册时间

            # #下单
            # curl -X POST "https://api.bitget.com/api/v2/spot/trade/place-order" \
            #    -H "ACCESS-KEY:*******" \
            #    -H "ACCESS-SIGN:*******" \
            #    -H "ACCESS-PASSPHRASE:*****" \
            #    -H "ACCESS-TIMESTAMP:1659076670000" \
            #    -H "locale:en-US" \
            #    -H "Content-Type:application/json" \  
            #    -d '{"symbol":"BTCUSDT","side":"buy","orderType":"limit","force":"gtc","price":"23222.5","size":"1","clientOid":"1"}'

            # #撤单
            # curl -X POST "https://api.bitget.com/api/v2/spot/trade/cancel-order" \
            #    -H "ACCESS-KEY:*******" \
            #    -H "ACCESS-SIGN:*******" \
            #    -H "ACCESS-PASSPHRASE:*****" \
            #    -H "ACCESS-TIMESTAMP:1659076670000" \
            #    -H "locale:en-US" \
            #    -H "Content-Type:application/json" \
            #    -d '{"symbol":"BTCUSDT","orderId":"121211212122"}'

            # #获取账号信息
            # curl "https://api.bitget.com/api/v2/spot/account/info" \
            #    -H "ACCESS-KEY:*******" \
            #    -H "ACCESS-SIGN:*******" \
            #    -H "ACCESS-PASSPHRASE:*****" \
            #    -H "ACCESS-TIMESTAMP:1659076670000" \
            #    -H "locale:en-US" \
            #    -H "Content-Type:application/json"

# gettax=True#是否重新获取tax
gettax=False#是否重新获取tax
if gettax==True:
    #获取代币费率信息#这个函数比较准确【跟uniswap的API比较接近】
    def getalltax(address):#这个可能需要本机IP才行，代理也需要判断区域
        response = requests.get(f'https://api.honeypot.is/v2/IsHoneypot?chainID=1&address={address}').json()
        # print(response)#指定代币查询的同时指定交易对
        return response
    #获取代币交易对信息
    def getallpairs(address):#这个可能需要本机IP才行，代理也需要判断区域
        pairs = requests.get(f'https://api.honeypot.is/v1/GetPairs?chainID=1&address={address}').json()
        # print(pairs)#指定代币查询所有池子（有一些确实可能有交易对没有交易进行）
        return pairs

    # cexnames=["binance","mexc","bitget","gate"]#目前四大交易所分别是币安 OKX Bybit Bitget（其中bitget现货流动性最好）
    cexnames=["gate"]
    for cexname in cexnames:
        # alldf=pd.DataFrame({})#重置一个空df
        df=pd.read_csv(f"代币详情{cexname}.csv")
        #只选择ETH代币
        if cexname=="bitget":
            df=df[(df["chain"]=="ERC20")]#bitget是ERC20，其他是ETH
        else:
            df=df[(df["chain"]=="ETH")]#bitget是ERC20，其他是ETH

        for index,thisdf in df.iterrows():
            thissymbol=thisdf["symbol"]
            # #有可能存在weth的问题
            # print(thissymbol.replace("USDT","").replace("USDC","").replace("_",""))#去掉后缀之后是否是SOL
            # if (thissymbol.replace("USDT","").replace("USDC","").replace("_","")=="ETH"):#平台母币在交易所内没有对应的地址
            #     thisaddress=wethaddresseth
            thisaddress=thisdf["智能合约地址"]
            print(thisaddress)
            #获取模拟交易费率详情
            thistax=getalltax(thisaddress)
            print(thistax)
            #精度信息梳理
            if "token" in thistax:
                if "decimals" in thistax.get("token", {}):
                    decimals=thistax["token"]["decimals"]#计算最大买数量
                    print("精度信息",decimals)
                    df.loc[df["智能合约地址"]==thisaddress,"链上decimals"]=decimals
            #tax信息梳理【按说可以在decimal后面，避免拿到不能获取decimal的非ecr20代币】
            if "simulationResult" in thistax:
                if "maxBuy" in thistax.get("simulationResult", {}):
                    maxBuy=thistax["simulationResult"]["maxBuy"]["token"]#计算最大买数量
                    print("包含最大购买数量",maxBuy)
                    df.loc[df["智能合约地址"]==thisaddress,"链上maxBuy"]=maxBuy
                if "maxSell" in thistax.get("simulationResult", {}):
                    maxSell=thistax["simulationResult"]["maxSell"]["token"]#计算最大卖数量
                    print("包含最小购买数量",maxSell)
                    df.loc[df["智能合约地址"]==thisaddress,"链上maxSell"]=maxSell
                buyTax=thistax["simulationResult"]["buyTax"]#买入税率（token本身的通缩）
                df.loc[df["智能合约地址"]==thisaddress,"链上buyTax"]=buyTax
                sellTax=thistax["simulationResult"]["sellTax"]#卖出税率（token本身的通缩）
                df.loc[df["智能合约地址"]==thisaddress,"链上sellTax"]=sellTax
                transferTax=thistax["simulationResult"]["transferTax"]#转账税率（token本身的通缩）
                df.loc[df["智能合约地址"]==thisaddress,"链上transferTax"]=transferTax
                buyGas=thistax["simulationResult"]["buyGas"]#购买gas
                df.loc[df["智能合约地址"]==thisaddress,"链上buyGas"]=buyGas
                sellGas=thistax["simulationResult"]["sellGas"]#卖出gas
                df.loc[df["智能合约地址"]==thisaddress,"链上sellGas"]=sellGas
                print(
                buyTax,#买入税率（token本身的通缩）
                sellTax,#卖出税率（token本身的通缩）
                transferTax,#转账税率（token本身的通缩）
                buyGas,#购买gas
                sellGas,#卖出gas
                )
                #获取所有交易对详情
                thispairs=getallpairs(thisaddress)
                # thispairs=pd.DataFrame(thispairs)#能转dataframe，但是转了之后不好存储，不如先存起来等用的时候再转dataframe
                print(thispairs)
                df.loc[df["智能合约地址"]==thisaddress,"链上pairs"]=str(thispairs)#后面需要把字符串转dataframe
                # df.to_csv(f"代币详情{cexname}拼接后.csv")
                # break
            else:
                print("模拟失败")
        df.to_csv(f"代币详情{cexname}拼接后.csv")

##【eth-defi库的命令行安装】
# #某些模块需要 ganache 才能安装。【不安装ganache就pip的话缺少东西】
# npm install -g ganache
# ganache --version
# #pip安装【尽量是3.10疑似的版本，不然少东西】
# pip install --upgrade pip
# pip install "web3-ethereum-defi[data]"#这个可能需要py12版本
# pip install coloredlogs
# pip install requests
# pip install tqdm
# pip install web3

# 打印价差日志
try:
    logdf=pd.read_csv("logdf.csv")
    print("读取历史logdf成功")
except:
    print("读取历史logdf失败，生成新的logdf")
    logdf=pd.DataFrame({})

# cexnames=["binance","mexc","bitget","gate"]#目前四大交易所分别是币安 OKX Bybit Bitget（其中bitget现货流动性最好）
# cexnames=["binance"]#（ETH交易对算着不咋挣钱）
# cexnames=["bitget"]#（ETH交易对算着不咋挣钱）大概192个代币符合条件
# cexnames=["mexc"]#大概200个代币符合条件
# cexnames=["gate"]#gate上的ETH代币价差蛮大的
cexnames=["gate"]
for cexname in cexnames:

    # #网络需要稳定，即便本地改了浏览器的IP也会导致网络报错
    dexname="uniswap"#钱包地址需要换，这边的问题是好几种报错，或许拿到资金池之后，再做二次处理会好一些
    if dexname=="uniswap":
        if cexname=="gate":
            #提币手续费是需要提的代币的数量，需要换算成USDT
            # df=pd.read_csv(f"代币详情{cexname}.csv")
            df=pd.read_csv(f"代币详情{cexname}拼接后.csv",encoding='utf-8')
            print("原始数据长度",len(df))
            df=df[(df["chain"]=="ETH")]
            print("只要ETH代币",len(df))
            df=df[(df["24小时成交额"]>100000)]
            print("过滤成交额10w",len(df))
            df=df[(df["是否暂停充值"]==False)&(df["是否暂停提现"]==False)&(df["是否暂停交易"]==False)]
            print("过滤不可充提币",len(df))
            def gettick(symbol):
                # symbol="BTC_USDT"
                r=requests.request('GET',
                                    "https://api.gateio.ws/api/v4/spot/order_book?"+f'currency_pair={symbol}',
                                    headers={'Accept':'application/json','Content-Type':'application/json'},
                                    )
                tick=r.json()
                # bids1p=tick["bids"][1][0]
                # bids1v=tick["bids"][1][1]
                # asks1p=tick["asks"][1][0]
                # asks1v=tick["asks"][1][1]
                # print(
                #     tick,
                #     bids1p,
                #     bids1v,
                #     asks1p,
                #     asks1v)
                return tick
        if cexname=="mexc":
            #提币手续费是需要提的代币的数量，需要换算成USDT
            # df=pd.read_csv(f"代币详情{cexname}.csv")
            df=pd.read_csv(f"代币详情{cexname}拼接后.csv")
            print("原始数据长度",len(df))
            df=df[(df["chain"]=="ETH")]
            print("只要ETH代币",len(df))
            df=df[(df["24小时成交额"]>100000)]
            print("过滤成交额10w",len(df))
            df=df[(df["是否可充值"]==True)&(df["是否可提币"]==True)]
            print("过滤不可充提币",len(df))
            # mexc数据获取
            # pip install pymexc#可能要求python11以上版本
            from pymexc import spot,futures
            api_key="mx0vglxeUz5UQL4wlI"
            api_secret="81a7ca1cf2d8497fb4d95e43552cc5ad"
            # 现货SPOT V3
            # initialize HTTP client
            spot_client=spot.HTTP(api_key=api_key,api_secret=api_secret)
            # # initialize WebSocket client
            # ws_spot_client=spot.WebSocket(api_key=api_key,api_secret=api_secret)
            def gettick(symbol):
                order_book=spot_client.order_book(symbol)#获取盘口数据
                bids1p=order_book["bids"][0][0]
                bids1v=order_book["bids"][0][1]
                asks1p=order_book["asks"][0][0]
                asks1v=order_book["asks"][0][1]
                # print(order_book)
                print(bids1p,bids1v,asks1p,asks1v)
                return order_book
        if cexname=="bitget":
            #提币手续费是需要提的代币的数量，需要换算成USDT
            # df=pd.read_csv(f"代币详情{cexname}.csv")
            df=pd.read_csv(f"代币详情{cexname}拼接后.csv")
            print("原始数据长度",len(df))
            df=df[(df["chain"]=="ERC20")]
            print("只要ETH代币",len(df))
            df=df[(df["24小时成交额"]>100000)]
            print("过滤成交额10w",len(df))
            df=df[(df["是否可提现"]==True)&(df["是否可充值"]==True)]
            print("过滤不可充提币",len(df))
            def gettick(symbol):
                # curl "https://api.bitget.com/api/v2/spot/market/orderbook?symbol=BTCUSDT&type=step0&limit=100"
                order_book=requests.request('GET',f"https://api.bitget.com/api/v2/spot/market/orderbook?symbol={symbol}&type=step0&limit=5").json()["data"]
                # print(order_book)
                # bids1p=order_book["bids"][0][0]
                # bids1v=order_book["bids"][0][1]
                # asks1p=order_book["asks"][0][0]
                # asks1v=order_book["asks"][0][1]
                # # print(order_book)
                # print(bids1p,bids1v,asks1p,asks1v)
                return order_book
        if cexname=="binance":
            #提币手续费是需要提的代币的数量，需要换算成USDT
            # df=pd.read_csv(f"代币详情{cexname}.csv")
            df=pd.read_csv(f"代币详情{cexname}拼接后.csv")
            print("原始数据长度",len(df))
            df=df[(df["chain"]=="ETH")]
            print("只要ETH代币",len(df))
            df=df[(df["24小时成交额"]>100000)]
            print("过滤成交额10w",len(df))
            df=df[(df["充值维护信息"].isna())&(df["提现维护信息"].isna())]
            print("过滤不可充提币",len(df))
            # 安装币安的python库
            # pip install python-binance
            from binance.client import Client
            # 币安的api配置
            api_key="0jmNVvNZusoXKGkwnGLBghPh8Kmc0klh096VxNS9kn8P0nkAEslVUlsuOcRoGrtm"
            api_secret="PbSWkno1meUckhmkLyz8jQ2RRG7KgmZyAWhIF0qPdCJrmDSFxoxGdMG5gZeYYCgy"
            # 创建Binance客户端
            client=Client(api_key,api_secret)
            def gettick(thissymbol):
                order_book=client.get_order_book(symbol=thissymbol,limit=5)
                print(order_book)
                bids1p=order_book["bids"][0][0]
                bids1v=order_book["bids"][0][1]
                asks1p=order_book["asks"][0][0]
                asks1v=order_book["asks"][0][1]
                # print(order_book)
                print(bids1p,bids1v,asks1p,asks1v)
                return order_book
        print("过滤tax之前",len(df))
        dropdf=df[(df["链上buyTax"]!=0)|(df["链上sellTax"]!=0)|(df["链上transferTax"]!=0)]
        print("过滤tax之中需要剔除的标的",len(dropdf),dropdf["智能合约地址"].tolist())
        # 0xcf0c122c6b73ff809c693db761e7baebe62b6a2e#这个大概千分之三的费用也会被去掉,以bitget为例总共182个币去掉了18个大概10%左右
        df=df[(df["链上buyTax"]==0)&(df["链上sellTax"]==0)&(df["链上transferTax"]==0)]#但凡包含一种税率的就直接清理掉
        #也可以处理计价货币
        df=df[(df["symbol"].str.endswith("USDT"))|(df["symbol"].str.endswith("USDC"))|(df["symbol"].str.endswith("ETH"))]#只要特定后缀的标的
        print("过滤tax之后",len(df))
        from web3 import HTTPProvider,Web3
        # # Uniswap连接参数【这个在早期版本需要包装路由合约地址，从路由合约的ABI当中获取调用的函数，不同的V1、V2、V3的路由合约还不一样】
        # UNISWAP_ROUTER_ADDRESS='0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'#uniswap路由地址
        # UNISWAP_ABI_URL='https://api.etherscan.io/api?module=contract&action=getabi&address='+UNISWAP_ROUTER_ADDRESS
        # 初始Web3连接地址73ee9f294d6443828729301f58786761
        # WEB3_INFURA_ADDRESS='https://go.getblock.io/0325742806184937aaac0240a5d0edb3'#主网
        # WEB3_INFURA_ADDRESS='https://rpc.ankr.com/eth'#主网
        WEB3_INFURA_ADDRESS='https://mainnet.infura.io/v3/d176b22a044c4fbcb002318438dc6e72'#主网
        # WEB3_INFURA_ADDRESS='wss://mainnet.infura.io/ws/v3/d176b22a044c4fbcb002318438dc6e72'#主网【http无链接】
        # WEB3_INFURA_ADDRESS='https://holesky.infura.io/v3/73ee9f294d6443828729301f58786761'#测试网holesky
        # 建立INFURA远程链接
        web3=Web3(Web3.HTTPProvider(WEB3_INFURA_ADDRESS))
        print("判断链接状态",web3.is_connected())
        print(f"Connected to chain {web3.eth.chain_id}")
        # 通过timestamp的方法获取第n个区块链和最后一个区块链的时间戳
        from eth_defi.timestamp import get_latest_block_timestamp
        lasttimestamp=get_latest_block_timestamp(web3)
        lasttimestamp=lasttimestamp.replace(tzinfo=datetime.timezone.utc)#转换为有事情的数据
        print("lasttimestamp",lasttimestamp,type(lasttimestamp))#这里显示的是时间戳所处时间
        import datetime
        # thisnow = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')# 格式化为字符串
        thisnow = datetime.datetime.now(datetime.timezone.utc)
        print("thisnow",thisnow,type(thisnow))
        if (lasttimestamp+datetime.timedelta(seconds=60))>datetime.datetime.now(datetime.timezone.utc):
            print("时间戳更新在1分钟内（任务开始）")
            # #之前出错是因为有大写的部分在干扰[在这个框架里面尽量统一小写]  
            # ZERO_ADDRESS_STR='0x0000000000000000000000000000000000000000'#以太坊0地址
            ethaddress="0x0000000000000000000000000000000000000000"
            #【获取ETH精度（赋值）】
            ethmint=int(18)#ETH母币不是ERC20
            wethaddress="0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
            usdtaddress="0xdac17f958d2ee523a2206206994597c13d831ec7"
            usdcaddress="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
            #计算ERC20代币的精度
            from eth_defi.token import fetch_erc20_details
            # usdc=fetch_erc20_details(web3,"0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")  # USDC on Polygon
            # print(f"{usdc}Token{usdc.name},{usdc.symbol},精度{usdc.decimals},at{usdc.address}on chain {usdc.chain_id}")
            wethmint=fetch_erc20_details(web3,wethaddress).decimals
            usdtmint=fetch_erc20_details(web3,usdtaddress).decimals
            usdcmint=fetch_erc20_details(web3,usdcaddress).decimals
            print(ethmint,wethmint,usdtmint,usdcmint,type(usdtmint),type(usdcmint))
            #【UNISWAP_V2_DEPLOYMENTS,选择ethereum的路由合约和工厂合约】
            from eth_defi.uniswap_v2.constants import UNISWAP_V2_DEPLOYMENTS
            #【UNISWAP_V3_DEPLOYMENTS,选择ethereum的路由合约和工厂合约】
            from eth_defi.uniswap_v3.constants import UNISWAP_V3_DEPLOYMENTS
            #获取多个合约的地址
            UNISWAP_V2_factoryaddress=UNISWAP_V2_DEPLOYMENTS["ethereum"]["factory"]
            UNISWAP_V2_routeraddress=UNISWAP_V2_DEPLOYMENTS["ethereum"]["router"]
            UNISWAP_V3_factoryaddress=UNISWAP_V3_DEPLOYMENTS["ethereum"]["factory"]
            UNISWAP_V3_routeraddress=UNISWAP_V3_DEPLOYMENTS["ethereum"]["router"]
            UNISWAP_V3_position_manager_address=UNISWAP_V3_DEPLOYMENTS["ethereum"]["position_manager"]
            UNISWAP_V3_quoteraddress=UNISWAP_V3_DEPLOYMENTS["ethereum"]["quoter"]
            print(
                "UNISWAP_V2_factoryaddress",UNISWAP_V2_factoryaddress,
                "UNISWAP_V2_routeraddress",UNISWAP_V2_routeraddress,
                "UNISWAP_V3_factoryaddress",UNISWAP_V3_factoryaddress,
                "UNISWAP_V3_routeraddress",UNISWAP_V3_routeraddress,
                "UNISWAP_V3_position_manager_address",UNISWAP_V3_factoryaddress,
                "UNISWAP_V3_quoteraddress",UNISWAP_V3_routeraddress,
                )
            from eth_defi.abi import get_contract,get_deployed_contract
            # UniswapV2Factorycontract=get_deployed_contract(web3,fname="sushi/UniswapV2Factory.json",address=UNISWAP_V2_factoryaddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV2Factorycontract",str(UniswapV2Factorycontract))
            # init_code_hash=web3.keccak(UniswapV2Factorycontract.bytecode).hex()#这个是部署字节码,应该是创建字节码
            # print("init_code_hash",init_code_hash)
            UniswapV2Factory=get_contract(web3,"sushi/UniswapV2Factory.json")
            UniswapV2Pair=get_contract(web3,"sushi/UniswapV2Pair.json")
            UniswapV3Factory=get_contract(web3,"uniswap_v3/UniswapV3Factory.json")
            UniswapV3Pair=get_contract(web3,"uniswap_v3/UniswapV3Pool.json")
            print(
                "UniswapV2Pair",UniswapV2Pair,"UniswapV2Factory",UniswapV2Factory,
                "UniswapV3Pair",UniswapV3Pair,"UniswapV3Factory",UniswapV3Factory,
                )#这个是合约信息
            # # 【使用abi和合约地址两种方式确认寻找到合约位置】需要哪一个单独启动,不然太占内存
            # #工厂合约地址
            # UniswapV2Factorycontract=get_deployed_contract(web3,fname="sushi/UniswapV2Factory.json",address=UNISWAP_V2_factoryaddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV2Factorycontract",str(UniswapV2Factorycontract))
            # UniswapV3Factorycontract=get_deployed_contract(web3,fname="uniswap_v3/UniswapV3Factory.json",address=UNISWAP_V3_factoryaddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV3Factorycontract",str(UniswapV3Factorycontract))
            # # 路由合约地址
            # UniswapV2Routercontract=get_deployed_contract(web3,fname="sushi/UniswapV2Factory.json",address=UNISWAP_V2_routeraddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV2Routercontract",str(UniswapV2Routercontract))
            # UniswapV3Routercontract=get_deployed_contract(web3,fname="uniswap_v3/UniswapV3Factory.json",address=UNISWAP_V3_routeraddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV3Routercontract",str(UniswapV3Routercontract))
            # # 交易对地址（需要用交易对的地址才行）
            # UniswapV2Poolcontract=get_deployed_contract(web3,fname="sushi/UniswapV2Pool.json",address=UNISWAP_V2_routeraddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV2Poolcontract",str(UniswapV2Poolcontract))
            # UniswapV3Poolcontract=get_deployed_contract(web3,fname="uniswap_v3/UniswapV3Pool.json",address=UNISWAP_V3_routeraddress)#获取部署在特定地址的合约的 Contract 代理对象
            # print("UniswapV3Poolcontract",str(UniswapV3Poolcontract))
            #启动uniswapV2服务器
            from eth_defi.uniswap_v2.deployment import fetch_deployment as fetch_deploymentV2
            uniswap_v2_cliet=fetch_deploymentV2(
                web3=web3,
                factory_address=UNISWAP_V2_factoryaddress,
                router_address=UNISWAP_V2_routeraddress,
                init_code_hash='0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f',
            )# 这个init hash code除了合约字节码之外还是需要跟账号的nonce计算的,自己模拟构建的一般不对,最好是生成新的pair的时候能直接抓到,这个没必要纠结应该用哪个了
            #启动uniswapV3服务器
            from eth_defi.uniswap_v3.deployment import fetch_deployment as fetch_deploymentV3
            uniswap_v3=fetch_deploymentV3(
                web3=web3,
                factory_address=UNISWAP_V3_factoryaddress,
                router_address=UNISWAP_V3_routeraddress,
                position_manager_address=UNISWAP_V3_position_manager_address,
                quoter_address=UNISWAP_V3_quoteraddress,
            )# fetch_deployment(web3,factory_address,router_address,position_manager_address,quoter_address)[source]
            print(uniswap_v3,uniswap_v3)
            #获取最佳gas费【BNB链用其他方式】EIP-1559 伦敦硬分叉链（Ethereumm 主网）,传统 EVM：Polygon、BNB Chain
            from eth_defi.gas import estimate_gas_fees
            def getgas():
                gas=estimate_gas_fees(web3)#查询伦敦硬分叉后的主网代币的最近gas费用
                # print("当前最佳gas费用",gas,type(gas))
                return gas#返回了一个特殊的类
            #将字符串地址转换成为可以参与计算的地址
            def checkaddress(thisaddress):
                thataddress=Web3.to_checksum_address(thisaddress)
                return thataddress
            address="0x85D773eAA2E9847018090241d9cc80D01f6635D5"#钱包地址
            private_key="0x8b831119a1b2790476531ed826d47bb7a67d1c631d6826cce96e85a650aa98c8"#钱包私钥
            targetusdtnum=1000#设置单笔金额（获取ETH交易对的时候默认除以1000）
            watchrate=0.01#价差提示阈值
            from eth_defi.abi import get_deployed_contract
            import json#df当中存储的字符串转json
            #遍历每个代币每一行的交易对
            truenum=0#判断有多少符合可交易条件的代币
            for index,thisdf in df.iterrows():
                # gas=getgas()
                # print("当前最佳gas费用",gas,type(gas))
                thissymbol=thisdf["symbol"]
                # #有可能存在weth的问题
                # print(thissymbol.replace("USDT","").replace("USDC","").replace("_",""))#去掉后缀之后是否是SOL
                # if (thissymbol.replace("USDT","").replace("USDC","").replace("_","")=="ETH"):#平台母币在交易所内没有对应的地址
                #     thisaddress=wethaddresseth
                thisaddress=thisdf["智能合约地址"]
                print(thissymbol,thisaddress)
                try:#以bitget为例，原来164个符合要求的标的，但是ERC20代币这里过滤出来了2个，只剩下162个了
                    #合约精度换算
                    thiscontract=fetch_erc20_details(web3,checkaddress(thisaddress))
                    thismint=thiscontract.decimals
                    thistotalsupply=thiscontract.total_supply
                    print("合约精度",thismint,type(thismint),"总发行量",thistotalsupply,type(thistotalsupply))#就是int类型，不用转换
                except:
                    print("不是ERC20代币不执行交易")
                    continue#跳过后面的逻辑执行循环的下一行
                #有一些标的没有交易对,如bitget官方的bgb在uniswap上就没交易
                if "链上pairs" in thisdf:#要求有这个参数
                    thispairs=thisdf["链上pairs"]
                    print(thispairs,type(thispairs))
                    if not ((isinstance(thispairs,float)) and (np.isnan(thispairs))):#这里要求不是浮点数non
                        #全部交易对处理及过滤(未区分交易所)
                        thispairs=thispairs.replace("\'","\"")#需要替换成双引号才能拆解字符串变成json
                        thispairs=pd.DataFrame(json.loads(thispairs))#字符串转回json
                        thispairs=thispairs.sort_values(by="Liquidity",ascending=False)#降序排列,但是尽量只做流动性最好的那一个标的,或者只做某个市场上的某个标的
                        print(f"过滤前,{len(thispairs)},{thispairs}")
                        # print(thispairs["Pair"],type(thispairs["Pair"]))
                        thispairs=thispairs[thispairs["Liquidity"]>100000]#只做大于100000USDT资金池的代币[]主要是规避资金池过小的标的
                        thispairs=thispairs[thispairs['Pair'].apply(lambda x: (
                            ethaddress in str(x))
                            or(
                            wethaddress in str(x))
                            or(
                            usdtaddress in str(x))
                            or(
                            usdcaddress in str(x))
                            )]
                        print(f"过滤后,{len(thispairs)},{thispairs}")
                        if len(thispairs)>0:#如果有相关交易对
                            #thispairsV2ETH交易对处理
                            dexpair="thispairsV2ETH"
                            print(f"执行交易对{dexpair}")
                            targetaddress=wethaddress
                            thispairsV2ETH=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V2" in str(x)))].copy()
                            thispairsV2ETH=thispairsV2ETH[thispairsV2ETH['Pair'].apply(lambda x: (targetaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            print("thispairsV2ETH",thispairsV2ETH)
                            if len(thispairsV2ETH)>0:#如果有相关交易对
                                pairaddress=thispairsV2ETH['Pair'].values[0]["Address"]
                                print("V2pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V2流动性数据
                                pool_instance=get_deployed_contract(web3,"sushi/UniswapV2Pair.json",pairaddress)
                                # token0_address=pool_instance.functions.token0().call()
                                # token1_address=pool_instance.functions.token1().call()
                                # token0=fetch_erc20_details(web3,token0_address)
                                # token1=fetch_erc20_details(web3,token1_address)
                                # #计算流动性（总的）
                                # liquidity_result=pool_instance.functions.getReserves().call()#这里尽量是交易对合约
                                # print(liquidity_result)#前面两个分别是token0和token1的池子的流动性,第三个值是区块号,0是左边那个,1是右边那个
                                # token0amount=liquidity_result[0]
                                # token1amount=liquidity_result[1]
                                # print("V2token0amount,token1amount",token0_address,token0amount,token1_address,token1amount)

                                #V2交易手续费默认千分之三
                                fee=int(30)
                                #获取交易对细节pairaddress#V2里面30就是千三的fee，基点是万分之一
                                from eth_defi.uniswap_v2.pair import fetch_pair_details
                                pair=fetch_pair_details(web3,pairaddress,reverse_token_order=True)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V2gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V2非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum/preprice

                                #V2价格计算
                                from eth_defi.uniswap_v2.fees import UniswapV2FeeCalculator
                                fee_helper=UniswapV2FeeCalculator(uniswap_v2_cliet)
                                dexaskprice=fee_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fee=int(30),#V2里面30就是千三的fee，基点是万分之一
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=fee_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fee=int(30),
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V2dexbidprice,dexaskprice",dexbidprice,dexaskprice)

                                # #V2价格计算【多加点钱测试价格冲击】V2流动性差所以滑点大
                                # from eth_defi.uniswap_v2.fees import UniswapV2FeeCalculator
                                # fee_helper=UniswapV2FeeCalculator(uniswap_v2_cliet)
                                # dexaskprice=fee_helper.get_amount_out(
                                #     amount_in=int(1000*targetamount*10**basetoken.decimals),
                                #     path=[basetoken.address,targettoken.address],
                                #     fee=int(30),#V2里面30就是千三的fee，基点是万分之一
                                #     slippage=50,
                                #     )/(1000*targetamount*(10**targettoken.decimals))
                                # dexaskprice=1/dexaskprice
                                # dexbidprice=fee_helper.get_amount_in(
                                #     amount_out=int(1000*targetamount*10**basetoken.decimals),
                                #     path=[targettoken.address,basetoken.address],
                                #     fee=int(30),
                                #     slippage=50,
                                #     )/(1000*targetamount*(10**targettoken.decimals))
                                # dexbidprice=1/dexbidprice
                                # print("1000倍金额V2dexbidprice,dexaskprice",dexbidprice,dexaskprice)

                                #dex价格换算
                                dexbidprice=dexbidprice*ethbids1p#针对dex代币为eth的标的将价格按照cex的以太坊的卖价计算回USDT
                                dexaskprice=dexaskprice*ethasks1p#针对dex代币为eth的标的将价格按照cex的以太坊的买价计算回USDT
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)


                            #thispairsV3ETH交易对处理
                            dexpair="thispairsV3ETH"
                            print(f"执行交易对{dexpair}")
                            targetaddress=wethaddress
                            thispairsV3ETH=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V3" in str(x)))].copy()
                            thispairsV3ETH=thispairsV3ETH[thispairsV3ETH['Pair'].apply(lambda x: (targetaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            if len(thispairsV3ETH)>0:#如果有相关交易对
                                pairaddress=thispairsV3ETH['Pair'].values[0]["Address"]
                                print("V3pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V3流动性数据
                                pool_instance=get_deployed_contract(web3,"uniswap_v3/UniswapV3Pool.json",pairaddress)
                                print(pool_instance)#前面两个分别是token0和token1的池子的流动性,第三个值是区块号,0是左边那个,1是右边那个
                                # token0_address=pool_instance.functions.token0().call()
                                # token1_address=pool_instance.functions.token1().call()
                                # token0=fetch_erc20_details(web3,token0_address)
                                # token1=fetch_erc20_details(web3,token1_address)
                                # #计算流动性（总的）
                                # liquidity=pool_instance.functions.liquidity().call()
                                # sqrtPriceX96=pool_instance.functions.slot0().call()[0]
                                # print(pool_instance.functions.liquidity().call(),pool_instance.functions.slot0().call())
                                # sqrtPrice=sqrtPriceX96 / (2**96)
                                # token0amount=liquidity / sqrtPrice/(10**pair.token0.decimals)
                                # token1amount=liquidity * sqrtPrice/(10**pair.token1.decimals)
                                # print("V3token0amount,token1amount",token0_address,token0amount,token1_address,token1amount)

                                #根据交易对地址换算交易费用
                                from eth_defi.uniswap_v3.pool import get_raw_fee_from_pool_address
                                fee=get_raw_fee_from_pool_address(web3,pairaddress)
                                print("V3fee",fee)
                                #获取交易对细节pairaddress
                                from eth_defi.uniswap_v3.pool import fetch_pool_details
                                pair=fetch_pool_details(web3,pairaddress)
                                print("pair",pair)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                # #获取实时价格【最后一笔交易的兑换比例,如果跟当前加偏离过多则有问题（但是这个数据是没有排除掉蜜罐风险的）】
                                # from eth_defi.uniswap_v3.price import get_onchain_price
                                # price=get_onchain_price(web3,pairaddress,reverse_token_order=True)
                                # print(f"base_token_address/quote_token_address的兑换比例{price:.2f}")
                                
                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V3gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V3非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum/preprice

                                #V3价格计算【V3里面,fee的基点是百万分之一，10000就是百一的fee,slippage滑点的基点是10000，10就是千分之一】，价格不同可能是估计出来的滑点不同
                                from eth_defi.uniswap_v3.price import estimate_buy_received_amount,estimate_sell_received_amount,UniswapV3PriceHelper
                                price_helper=UniswapV3PriceHelper(uniswap_v3)
                                dexaskprice=price_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=price_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V3dexbidprice,dexaskprice",dexbidprice,dexaskprice)

                                # # 【多加点钱测试价格冲击】V3流动性好所以滑点小
                                # dexaskprice=price_helper.get_amount_out(
                                #     amount_in=int(1000*targetamount*10**basetoken.decimals),
                                #     path=[basetoken.address,targettoken.address],
                                #     fees=[fee],
                                #     slippage=30,
                                #     # block_identifier=block_identifier,
                                #     )/(1000*targetamount*(10**targettoken.decimals))
                                # dexaskprice=1/dexbidprice
                                # dexbidprice=price_helper.get_amount_in(
                                #     amount_out=int(1000*targetamount*10**basetoken.decimals),
                                #     path=[targettoken.address,basetoken.address],
                                #     fees=[fee],
                                #     slippage=30,
                                #     # block_identifier=block_identifier,
                                #     )/(1000*targetamount*(10**targettoken.decimals))
                                # dexbidprice=1/dexbidprice
                                # print("1000倍金额V3dexbidprice,dexaskprice",dexbidprice,dexaskprice)

                                #dex价格换算
                                dexbidprice=dexbidprice*ethbids1p#针对dex代币为eth的标的将价格按照cex的以太坊的卖价计算回USDT
                                dexaskprice=dexaskprice*ethasks1p#针对dex代币为eth的标的将价格按照cex的以太坊的买价计算回USDT
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)


                            #thispairsV2USDT交易对处理
                            dexpair="thispairsV2USDT"
                            print(f"执行交易对{dexpair}")
                            targetaddress=usdtaddress
                            thispairsV2USDT=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V2" in str(x)))].copy()
                            thispairsV2USDT=thispairsV2USDT[thispairsV2USDT['Pair'].apply(lambda x: (targetaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            print("thispairsV2USDT",thispairsV2USDT)
                            if len(thispairsV2USDT)>0:#如果有相关交易对
                                pairaddress=thispairsV2USDT['Pair'].values[0]["Address"]
                                print("V2pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V2流动性数据
                                pool_instance=get_deployed_contract(web3,"sushi/UniswapV2Pair.json",pairaddress)

                                #V2交易手续费默认千分之三
                                fee=int(30)
                                #获取交易对细节pairaddress#V2里面30就是千三的fee，基点是万分之一
                                from eth_defi.uniswap_v2.pair import fetch_pair_details
                                pair=fetch_pair_details(web3,pairaddress,reverse_token_order=True)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V2gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V2非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum

                                #V2价格计算
                                from eth_defi.uniswap_v2.fees import UniswapV2FeeCalculator
                                fee_helper=UniswapV2FeeCalculator(uniswap_v2_cliet)
                                dexaskprice=fee_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fee=int(30),#V2里面30就是千三的fee，基点是万分之一
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=fee_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fee=int(30),
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V2dexbidprice,dexaskprice",dexbidprice,dexaskprice)
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)


                            #thispairsV3USDT交易对处理
                            dexpair="thispairsV3USDT"
                            print(f"执行交易对{dexpair}")
                            targetaddress=usdtaddress
                            thispairsV3USDT=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V3" in str(x)))].copy()
                            thispairsV3USDT=thispairsV3USDT[thispairsV3USDT['Pair'].apply(lambda x: (usdtaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            if len(thispairsV3USDT)>0:#如果有相关交易对
                                pairaddress=thispairsV3USDT['Pair'].values[0]["Address"]
                                print("V3pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V3流动性数据
                                pool_instance=get_deployed_contract(web3,"uniswap_v3/UniswapV3Pool.json",pairaddress)
                                print(pool_instance)#前面两个分别是token0和token1的池子的流动性,第三个值是区块号,0是左边那个,1是右边那个

                                #根据交易对地址换算交易费用
                                from eth_defi.uniswap_v3.pool import get_raw_fee_from_pool_address
                                fee=get_raw_fee_from_pool_address(web3,pairaddress)
                                print("V3fee",fee)
                                #获取交易对细节pairaddress
                                from eth_defi.uniswap_v3.pool import fetch_pool_details
                                pair=fetch_pool_details(web3,pairaddress)
                                print("pair",pair)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                # #获取实时价格【最后一笔交易的兑换比例,如果跟当前加偏离过多则有问题（但是这个数据是没有排除掉蜜罐风险的）】
                                # from eth_defi.uniswap_v3.price import get_onchain_price
                                # price=get_onchain_price(web3,pairaddress,reverse_token_order=True)
                                # print(f"base_token_address/quote_token_address的兑换比例{price:.2f}")
                                
                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V3gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V3非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum

                                #V3价格计算【V3里面,fee的基点是百万分之一，10000就是百一的fee,slippage滑点的基点是10000，10就是千分之一】，价格不同可能是估计出来的滑点不同
                                from eth_defi.uniswap_v3.price import estimate_buy_received_amount,estimate_sell_received_amount,UniswapV3PriceHelper
                                price_helper=UniswapV3PriceHelper(uniswap_v3)
                                dexaskprice=price_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=price_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V3dexbidprice,dexaskprice",dexbidprice,dexaskprice)
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)


                            #thispairsV2USDC交易对处理
                            dexpair="thispairsV2USDT"
                            print(f"执行交易对{dexpair}")
                            targetaddress=usdcaddress
                            thispairsV2USDT=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V2" in str(x)))].copy()
                            thispairsV2USDT=thispairsV2USDT[thispairsV2USDT['Pair'].apply(lambda x: (targetaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            print("thispairsV2USDT",thispairsV2USDT)
                            if len(thispairsV2USDT)>0:#如果有相关交易对
                                pairaddress=thispairsV2USDT['Pair'].values[0]["Address"]
                                print("V2pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V2流动性数据
                                pool_instance=get_deployed_contract(web3,"sushi/UniswapV2Pair.json",pairaddress)

                                #V2交易手续费默认千分之三
                                fee=int(30)
                                #获取交易对细节pairaddress#V2里面30就是千三的fee，基点是万分之一
                                from eth_defi.uniswap_v2.pair import fetch_pair_details
                                pair=fetch_pair_details(web3,pairaddress,reverse_token_order=True)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V2gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V2非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum

                                #V2价格计算
                                from eth_defi.uniswap_v2.fees import UniswapV2FeeCalculator
                                fee_helper=UniswapV2FeeCalculator(uniswap_v2_cliet)
                                dexaskprice=fee_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fee=int(30),#V2里面30就是千三的fee，基点是万分之一
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=fee_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fee=int(30),
                                    slippage=50,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V2dexbidprice,dexaskprice",dexbidprice,dexaskprice)
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)


                            #thispairsV3USDC交易对处理
                            dexpair="thispairsV3USDC"
                            print(f"执行交易对{dexpair}")
                            targetaddress=usdcaddress
                            thispairsV3USDT=thispairs[thispairs['Pair'].apply(lambda x: ("Uniswap V3" in str(x)))].copy()
                            thispairsV3USDT=thispairsV3USDT[thispairsV3USDT['Pair'].apply(lambda x: (usdcaddress in str(x)))]#只要weth交易对(也可以试试只要usdt交易对)
                            if len(thispairsV3USDT)>0:#如果有相关交易对
                                pairaddress=thispairsV3USDT['Pair'].values[0]["Address"]
                                print("V3pairaddress",pairaddress,type(pairaddress))

                                #根据池状态获取V3流动性数据
                                pool_instance=get_deployed_contract(web3,"uniswap_v3/UniswapV3Pool.json",pairaddress)
                                print(pool_instance)#前面两个分别是token0和token1的池子的流动性,第三个值是区块号,0是左边那个,1是右边那个

                                #根据交易对地址换算交易费用
                                from eth_defi.uniswap_v3.pool import get_raw_fee_from_pool_address
                                fee=get_raw_fee_from_pool_address(web3,pairaddress)
                                print("V3fee",fee)
                                #获取交易对细节pairaddress
                                from eth_defi.uniswap_v3.pool import fetch_pool_details
                                pair=fetch_pool_details(web3,pairaddress)
                                print("pair",pair)

                                #区分token0和token1那个是买方哪个是卖方【小写】
                                if pair.token0.address.lower()==targetaddress.lower():
                                    basetoken=pair.token0
                                    targettoken=pair.token1
                                    # baseaomunt=token0amount
                                elif pair.token1.address.lower()==targetaddress.lower():
                                    basetoken=pair.token1
                                    targettoken=pair.token0
                                    # baseaomunt=token1amount
                                else:
                                    print("地址不对")

                                # #获取实时价格【最后一笔交易的兑换比例,如果跟当前加偏离过多则有问题（但是这个数据是没有排除掉蜜罐风险的）】
                                # from eth_defi.uniswap_v3.price import get_onchain_price
                                # price=get_onchain_price(web3,pairaddress,reverse_token_order=True)
                                # print(f"base_token_address/quote_token_address的兑换比例{price:.2f}")
                                
                                #获取eth现价【对以太坊交易对的DEX价格进行处理】
                                if cexname=="gate":
                                    ethprice=gettick("ETH_USDT")
                                    print("V3gate")
                                if (cexname=="binance")or(cexname=="bitget")or(cexname=="mexc"):
                                    ethprice=gettick("ETHUSDT")
                                    print("V3非gate")
                                print(ethprice)
                                ethbids1p=float(ethprice["bids"][1][0])
                                ethbids1v=float(ethprice["bids"][1][1])
                                ethasks1p=float(ethprice["asks"][1][0])
                                ethasks1v=float(ethprice["asks"][1][1])
                                print(ethbids1p,ethbids1v,ethasks1p,ethasks1v)
                                preprice=(ethasks1p+ethasks1v)/2
                                targetamount=targetusdtnum

                                #V3价格计算【V3里面,fee的基点是百万分之一，10000就是百一的fee,slippage滑点的基点是10000，10就是千分之一】，价格不同可能是估计出来的滑点不同
                                from eth_defi.uniswap_v3.price import estimate_buy_received_amount,estimate_sell_received_amount,UniswapV3PriceHelper
                                price_helper=UniswapV3PriceHelper(uniswap_v3)
                                dexaskprice=price_helper.get_amount_out(
                                    amount_in=int(targetamount*10**basetoken.decimals),
                                    path=[basetoken.address,targettoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexaskprice=1/dexaskprice
                                dexbidprice=price_helper.get_amount_in(
                                    amount_out=int(targetamount*10**basetoken.decimals),
                                    path=[targettoken.address,basetoken.address],
                                    fees=[fee],
                                    slippage=30,
                                    # block_identifier=block_identifier,
                                    )/(targetamount*(10**targettoken.decimals))
                                dexbidprice=1/dexbidprice
                                print("V3dexbidprice,dexaskprice",dexbidprice,dexaskprice)
                                try:
                                    #获取代币价格
                                    price=gettick(thissymbol)
                                    print(price)
                                    bids1p=float(price["bids"][1][0])
                                    bids1v=float(price["bids"][1][1])
                                    asks1p=float(price["asks"][1][0])
                                    asks1v=float(price["asks"][1][1])
                                    print(bids1p,bids1v,asks1p,asks1v)
                                    thistime=datetime.datetime.now()
                                    print(thistime)
                                    thisdf=pd.DataFrame({"datetime":[thistime.strftime('%Y-%m-%d %H:%M:%S')],
                                                        "cexname":cexname,
                                                        "dexname":dexname,
                                                        "cex交易对":[thissymbol],
                                                        "bids1p":[bids1p],"bids1v":[bids1v],
                                                        "asks1p":[asks1p],"asks1v":[asks1v],
                                                        "dex交易对":dexpair,
                                                        "dex合约地址":[thisaddress],
                                                        "dex默认单笔金额":f"{targetusdtnum}USDT",
                                                        "dexbidprice":[dexbidprice],
                                                        "dexaskprice":[dexaskprice],
                                                        })
                                    thisdf["cex-taker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["asks1p"]-1
                                    thisdf["cex-taker卖dex买利润"]=thisdf["bids1p"]/thisdf["dexaskprice"]-1
                                    thisdf["cex-maker买dex卖利润"]=thisdf["dexbidprice"]/thisdf["bids1p"]-1
                                    thisdf["cex-maker卖dex买利润"]=thisdf["asks1p"]/thisdf["dexaskprice"]-1
                                    print(thisdf)
                                    logdf=pd.concat([logdf,thisdf])
                                    logdf.to_csv("logdf.csv")
                                    mes=thisdf.to_json(orient="columns",force_ascii=False)
                                    logger.info(f"{mes}")
                                    if thisdf["cex-taker卖dex买利润"].values[0]>watchrate:
                                        postmessage(title=thissymbol,
                                                    mes=f"""taker价差提示阈值{watchrate}
                                                    \n\n标的{thissymbol}
                                                    \n\n合约地址{thisaddress}
                                                    \n\n{dexname}买入{cexname}卖出
                                                    \n\nDEX交易对{dexpair}
                                                    \n\ntaker价差{thisdf["cex-taker卖dex买利润"].values[0]}，
                                                    \n\nmaker价差{thisdf["cex-maker卖dex买利润"].values[0]}，
                                                    \n\ndex默认单笔金额:{targetusdtnum}USDT""",
                                                    secret=secret,
                                                    access_token=access_token
                                                    )
                                except Exception as e:
                                    print("交易对没有K线（疑似退市）",e)
                        

                        #计算价格和执行交易在这里
                        truenum+=1
                        print(truenum)#bitget上大概171个代币符合条件
                    else:
                        print("没有合适的交易对")
                else:
                    print("缺乏链上pairs数据")
                    break
                # time.sleep(1000)
        else:
            print("最新区块的时间戳超时无法执行交易（任务结束）")



# #【】【每3个小时执行一轮】【】# #
# 【注意所有前端显示的交易对当中包含ETH的标的，其实都是用WETH的地址计算的交易对】那么执行交易的时候要如何设置呢
# 【蜜罐识别和精度数据在策略启动时已经执行了一次，后面对精度进行了二次确认】
# 【卖价和买价都比前端低，说明前端数据有一定的延迟，以API为准】
# 【无法在L2上实现，主网充值可交易时间是6次确认{不到2分钟}，另外很多币没L2的充值{压根没法交易}，bitget充值是需要64个区块确认（但是相应的流动性比较好，有没有问题需要试试才知道）】

# #【】【报错处理】【】# #
# #【观点1：即便是发起了nonce错误的交易，被以太坊虚拟机判定为双花攻击而失败，也因为发起了交易类事件所以会扣gas费用】
# #【观点2：为了平衡系统安全性、性能和用户体验；通过拒绝明显无效的交易，系统可以保护自身免受潜在攻击。被剔除的交易通常不会被执行，则需要重新发起；而通过排队和剔除机制，系统可以在资源有限的情况下优化交易处理流程】
# BadChainId#报错类型gas费用超了
# BroadcastFailure#报错类型无法广播事务
# ConfirmationTimedOut#报错类型交易确认超时
# NonRetryableBroadcastException#报错类型不要试图传播这些
# NonceMismatch#报错类型nonce不匹配
# NonceTooLow#报错类型gas费用超
# OutOfGasFunds#报错类型gas费用超
# OutOfGasDuringSale#报错类型该代币可能是某种限制转账的庞氏骗局。eth_defi.uniswap_v2.token_tax 的文档。OutOfGasDuringSell 异常。
# BadTimestampValueReturned#时间戳看起来不太好，eth_defi.event_reader.reader.BadTimestampValueReturned 异常的文档。
# ReadingLogsFailed#eth_getLogs 调用失败，eth_defi.event_reader.reader.ReadingLogsFailed 异常的文档。
# TimestampNotFound#时间戳服务没有给定块的 timestasmp，eth_defi.event_reader.reader.TimestampNotFound 异常的文档。
# PartialHttpResponseException#IPCProvider 需要 JSONDecodeErrors，而不是 value 错误，eth_defi.event_reader.fast_json_rpc 的文档。PartialHttpResponseException 异常。

# #重放报错原因
# receipts=wait_transactions_to_complete(web3,[tx_hash])
# # Check that the transaction reverted
# assert len(receipts) == 1
# receipt=receipts[tx_hash]
# assert receipt.status == 0
# reason=fetch_transaction_revert_reason(web3,tx_hash)
# VM Exception while processing transaction: revert BEP20: transfer amount exceeds balance"
