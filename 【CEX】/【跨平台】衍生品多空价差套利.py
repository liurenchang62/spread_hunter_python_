##pip install python-binance
# import logging#打印日志
import pandas as pd
import math
import time
import datetime


#获取gate数据
import requests#配置post访问头
gate_host_prefix="https://api.gateio.ws/api/v4"#实盘
gate_headers={'Accept': 'application/json','Content-Type': 'application/json'}
#获取所有标的
gate_chain_df=pd.DataFrame(requests.request('GET',gate_host_prefix+'/spot/currencies',headers=gate_headers).json())
gate_chain_df=gate_chain_df[gate_chain_df["trade_disabled"]==False]#去掉当前不可交易的标的
gate_chain_df=gate_chain_df[~gate_chain_df['chain'].apply(lambda x: any(c.isdigit() for c in str(x)))]#去掉杠杆代币
def getgatespot():#获取现货交易对【只要非杠杆代币】
    gate_spot_info_df=pd.DataFrame(requests.request('GET',gate_host_prefix+'/spot/currency_pairs', headers=gate_headers).json())
    gate_spot_info_df=gate_spot_info_df[gate_spot_info_df["id"].isin([chainsymbol+"_USDT" for chainsymbol in gate_chain_df["currency"]])]
    gate_spot_info_df=gate_spot_info_df[gate_spot_info_df["trade_status"]=="tradable"]#只保留可以交易的标的【还有一种sellable是临近上市的标的】
    gate_spot_symbols = gate_spot_info_df["id"].tolist()
    return gate_spot_symbols
def getgatefuture():#获取合约交易对【只要非杠杆代币】
    gate_contract_info_df=pd.DataFrame(requests.request('GET',gate_host_prefix+'/futures/usdt/contracts',headers=gate_headers).json())
    gate_contract_info_df=gate_contract_info_df[gate_contract_info_df["name"].isin([chainsymbol+"_USDT" for chainsymbol in gate_chain_df["currency"]])]#只保留非杠杆代币
    gate_contract_info_df=gate_contract_info_df[gate_contract_info_df["in_delisting"]==False]#去掉已退市标的
    # [
    #   {
    #     "name": "BTC_USDT",
    #     "type": "direct",
    #     "quanto_multiplier": "0.0001",量子乘法器
    #     "ref_discount_rate": "0",#参考贴现率
    #     "order_price_deviate": "0.5",#订单价格偏差
    #     "maintenance_rate": "0.005",#维护速率
    #     "mark_type": "index",#标记价格
    #     "last_price": "38026",#最新价格
    #     "mark_price": "37985.6",
    #     "index_price": "37954.92",
    #     "funding_rate_indicative": "0.000219",#资金费率（预测）
    #     "mark_price_round": "0.01",#最小变动价（标记）
    #     "funding_offset": 0,
    #     "in_delisting": false,
    #     "risk_limit_base": "1000000",
    #     "interest_rate": "0.0003",#利率
    #     "order_price_round": "0.1",
    #     "order_size_min": 1,
    #     "ref_rebate_rate": "0.2",
    #     "funding_interval": 28800,
    #     "risk_limit_step": "1000000",
    #     "leverage_min": "1",#最小杠杆
    #     "leverage_max": "100",#最大杠杆
    #     "risk_limit_max": "8000000",
    #     "maker_fee_rate": "-0.00025",#maker手续费
    #     "taker_fee_rate": "0.00075",#taker手续费
    #     "funding_rate": "0.002053",#资金费率
    #     "order_size_max": 1000000,#最大下单规模
    #     "funding_next_apply": 1610035200,
    #     "short_users": 977,#空头用户
    #     "config_change_time": 1609899548,
    #     "trade_size": 28530850594,
    #     "position_size": 5223816,
    #     "long_users": 455,#多头用户
    #     "funding_impact_value": "60000",
    #     "orders_limit": 50,
    #     "trade_id": 10851092,
    #     "orderbook_id": 2129638396,
    #     "enable_bonus": true,
    #     "enable_credit": true,
    #     "create_time": 1669688556,#创建时间
    #     "funding_cap_ratio": "0.75"
    #   }
    # ]
    gate_contract_symbols=gate_contract_info_df["name"].tolist()
    return gate_contract_symbols
gate_spot_symbols=getgatespot()
gate_contract_symbols=getgatefuture()
#获取所有现货交易对tick信息
gate_spot_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/spot/tickers', headers=gate_headers).json())#现货ticker
gate_spot_ticker=gate_spot_ticker[gate_spot_ticker["currency_pair"].isin(gate_contract_symbols)]#只要非杠杆代币
gate_spot_ticker=gate_spot_ticker.rename(columns={
        "currency_pair":"代码",
        "last":"比特儿现货现价",
        "quote_volume":"比特儿现货24小时成交额",#计价货币
        "base_volume":"比特儿现货24小时成交量",#基础货币
        "change_percentage":"比特儿现货涨跌幅",
        "lowest_ask":"比特儿现货卖一",
        "highest_bid":"比特儿现货买一",
    })
gate_spot_ticker=gate_spot_ticker[["代码","比特儿现货现价","比特儿现货24小时成交额","比特儿现货24小时成交量","比特儿现货涨跌幅","比特儿现货卖一","比特儿现货买一",]]

#获取所有标的的当期或下期资金费率【这里默认获取的是交割合约的费率】
# gate_contract_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/delivery/usdt/tickers', headers=gate_headers).json())#交割合约ticker
gate_contract_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/futures/usdt/tickers', headers=gate_headers).json())#永续合约ticker
gate_contract_ticker=gate_contract_ticker[gate_contract_ticker["contract"].isin(gate_contract_symbols)]#只要非杠杆代币
gate_contract_ticker=gate_contract_ticker.rename(columns={
        "contract":"代码",
        "last":"比特儿合约现价",
        "volume_24h_quote":"比特儿合约24小时成交额",#计价货币
        "volume_24h_base":"比特儿合约24小时成交量",#基础货币
        "change_percentage":"比特儿合约涨跌幅",
        "lowest_ask":"比特儿合约卖一",
        "highest_bid":"比特儿合约买一",
        # "basis_rate":"比特儿合约基差率",
        # "total_size":"比特儿合约总持仓量",
        # "funding_rate_indicative":"比特儿合约下一周期预测资金费率",
        "funding_rate":"比特儿合约资金费率",#这里的资金费率是动态的所以基本上结算的时候偏差不会太大
    })
gate_contract_ticker=gate_contract_ticker[["代码","比特儿合约现价","比特儿合约24小时成交额","比特儿合约24小时成交量","比特儿合约涨跌幅","比特儿合约卖一","比特儿合约买一","比特儿合约资金费率",]]

#####获取币安数据
from binance.client import Client
# 创建Binance客户端【实盘服务器】
# binanceclient=Client(api_key="0jmNVvNZusoXKGkwnGLBghPh8Kmc0klh096VxNS9kn8P0nkAEslVUlsuOcRoGrtm",api_secret="PbSWkno1meUckhmkLyz8jQ2RRG7KgmZyAWhIF0qPdCJrmDSFxoxGdMG5gZeYYCgy")
#子账户
binanceclient=Client(api_key="1ilJNqNVbQamDv7bYYt6I1xkJP529niFmOehi8mmPSiJqXStzphgc4Ie5he1rdHu",api_secret="CYCBFYCuCljLdMeUV66pSlXztn9Q625iQ88rF4tgvP569X8jslrEg7s6cpdH85s7")
# #合约测试服务器
# funturebinanceclient=Client(api_key="266950dec031270d32fed06a552c2698cf662f0e32c4788acf25646bba7ef2c6",api_secret="1a2b9793419db20e99a307be8ac04fec7a43bd77d46b71b161456105161b164d",testnet=True,base_endpoint="https://testnet.binancefuture.com/fapi")
# #现货测试服务器
# spotbinanceclient=Client(api_key="I5To2CwMIp74EB6zkulpwo4eioWPrYyp4JwBDLBR6QFNHalQUnm595ZEy3Z3JWzK", api_secret="37DJ4aGGfTTLuNtKHQC7p8IMRN3fx0kM5QY0iZGqFwZ9GDeBfi3YUF3FHCngInH3", testnet=True)

#这里应该是获取的现货余额
binance_spot_balances=binanceclient.get_account()
binance_spot_balances=pd.json_normalize(binance_spot_balances["balances"])
binance_spot_balances["free"]=binance_spot_balances["free"].astype(float)
binance_spot_balances=binance_spot_balances[~(binance_spot_balances["free"]==0)]
print("总余额",binance_spot_balances)
#获取现货余额
spot_balance=binanceclient.get_asset_balance(asset="USDT")
binance_spot_amount=float(spot_balance["free"])
print(f"现货USDT余额",binance_spot_amount)
#获取合约余额
futures_balance=binanceclient.futures_account_balance()#获取永续合约账户资产余额
futures_balance_df=pd.json_normalize(futures_balance)#永续合约账户资产余额转DataFrame
futures_balance_df=futures_balance_df[futures_balance_df["asset"]== "USDT"]#只计算USDT本位合约的资产信息
binance_futures_amount=float(futures_balance_df["balance"].values[0])
print(f"合约USDT余额",binance_futures_amount)
#合约现货资产再平衡
if (binance_spot_amount>0)or(binance_futures_amount>0):
    if (binance_spot_amount-binance_futures_amount)>(binance_spot_amount+binance_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
        thisamount=(binance_spot_amount-binance_futures_amount)/2
        print("现货仓位减去合约仓位较重，需要平衡以下金额的仓位",thisamount)
        transfer_info=binanceclient.universal_transfer(asset="USDT",amount=thisamount,type="MAIN_UMFUTURE")#现货转合约
    elif (binance_futures_amount-binance_spot_amount)>(binance_spot_amount+binance_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
        thisamount=(binance_spot_amount-binance_futures_amount)/2
        print("现货仓位减去合约仓位较轻，需要平衡以下金额的仓位",thisamount)
        transfer_info=binanceclient.universal_transfer(asset="USDT",amount=-thisamount,type="MAIN_UMFUTURE")#现货转合约
    else:
        print("资金均匀不用调整")
def getbinancespot():#获取现货交易对【只要非杠杆代币】
    binance_spot_info_df=pd.json_normalize(binanceclient.get_exchange_info(),record_path="symbols")
    binance_spot_info_df=binance_spot_info_df[binance_spot_info_df["status"]=="TRADING"]#只要仍然在交易的代币
    #TRADING状态是可交易，PENDING_TRADING状态是待上市，SETTLING状态是退市
    binance_spot_info_df=binance_spot_info_df[binance_spot_info_df["quoteAsset"]=="USDT"]#以USDT结算
    binance_spot_info_df=binance_spot_info_df[binance_spot_info_df['symbol'].str.endswith('USDT')]#以USDT结尾
    binance_spot_info_df=binance_spot_info_df[~binance_spot_info_df['symbol'].apply(lambda x: any(c.isdigit() for c in str(x)))] # 去掉交割合约等包含数字的合约标的
    binance_spot_info_df["minPrice"]=binance_spot_info_df["filters"].apply(lambda x :x[0]["minPrice"])#最小价格
    binance_spot_info_df["minQty"]=binance_spot_info_df["filters"].apply(lambda x :x[1]["minQty"])#最小数量
    binance_spot_info_df["tickSize"]=binance_spot_info_df["filters"].apply(lambda x :x[0]["tickSize"])#价格步长
    binance_spot_info_df["stepSize"]=binance_spot_info_df["filters"].apply(lambda x :x[1]["stepSize"])#数量步长
    # binance_spot_info_df.to_csv("binance_spot_info_df.csv")
    binance_spot_usdt_symbols=binance_spot_info_df["symbol"].tolist()
    return binance_spot_usdt_symbols
def getbinancefutures():#获取合约交易对【只要非杠杆代币】
    binance_futures_info_df=pd.json_normalize(binanceclient.futures_exchange_info(),record_path="symbols")
    binance_futures_info_df=binance_futures_info_df[binance_futures_info_df["status"]=="TRADING"]#只要仍然在交易的代币
    #TRADING状态是可交易，PENDING_TRADING状态是待上市，SETTLING状态是退市
    binance_futures_info_df=binance_futures_info_df[binance_futures_info_df["quoteAsset"]=="USDT"]#以USDT结算
    binance_futures_info_df=binance_futures_info_df[binance_futures_info_df['symbol'].str.endswith('USDT')]#以USDT结尾
    binance_futures_info_df=binance_futures_info_df[~binance_futures_info_df['symbol'].apply(lambda x: any(c.isdigit() for c in str(x)))] # 去掉交割合约等包含数字的合约标的
    binance_futures_info_df["minPrice"]=binance_futures_info_df["filters"].apply(lambda x :x[0]["minPrice"])#最小价格
    binance_futures_info_df["minQty"]=binance_futures_info_df["filters"].apply(lambda x :x[1]["minQty"])#最小数量
    binance_futures_info_df["tickSize"]=binance_futures_info_df["filters"].apply(lambda x :x[0]["tickSize"])#价格步长
    binance_futures_info_df["stepSize"]=binance_futures_info_df["filters"].apply(lambda x :x[1]["stepSize"])#数量步长
    binance_futures_info_df.to_csv(f"binance_futures_info_df.csv")
    binance_futures_usdt_symbols=binance_futures_info_df["symbol"].tolist()
    return binance_futures_usdt_symbols
binance_spot_usdt_symbols=getbinancespot()
binance_futures_usdt_symbols=getbinancefutures()
# 获取币安溢价率
binance_contract_coin_mark_price=binanceclient.futures_mark_price()#这里是USDT本位合约
# binance_contract_coin_mark_price=binanceclient.futures_coin_mark_price()#这里是币本位合约
binance_contract_coin_mark_price=pd.DataFrame(binance_contract_coin_mark_price)
binance_contract_coin_mark_price=binance_contract_coin_mark_price[binance_contract_coin_mark_price["symbol"].isin(binance_futures_usdt_symbols)]
binance_contract_coin_mark_price=binance_contract_coin_mark_price.rename(columns={
    "symbol":"代码","markPrice":"币安合约现价","indexPrice":"币安指数价格",
    "estimatedSettlePrice":"币安预估结算价","lastFundingRate":"币安合约资金费率",#这里的合约资金费率也是动态的
    "nextFundingTime":"币安下次资金费时间","interestRate":"币安标的资产基础利率","time":"币安合约标记时间",
    })
binance_contract_coin_mark_price["日期"]=binance_contract_coin_mark_price["币安合约标记时间"].apply(lambda x: time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime(int(x)/1000)))#这里是用的标准时的数据
# binance_contract_coin_mark_price=binance_contract_coin_mark_price[binance_contract_coin_mark_price["代码"]=="ORDIUSDT"]
binance_contract_coin_mark_price.to_csv("binance_contract_coin_mark_price.csv")
print("当前溢价率",binance_contract_coin_mark_price)

# 现货ticker
binance_spot_ticker=pd.json_normalize(binanceclient.get_ticker())
binance_spot_ticker=binance_spot_ticker[binance_spot_ticker["symbol"].isin(binance_futures_usdt_symbols)]
binance_spot_ticker=binance_spot_ticker.rename(columns={
        "symbol":"代码",
        "lastPrice":"币安现货现价",
        "quoteVolume":"币安现货24小时成交额",#计价货币
        "volume":"币安现货24小时成交量",#基础货币
        "priceChangePercent":"币安现货涨跌幅",
        "closeTime":"币安现货标记时间",
        "askPrice":"币安现货卖一",
        "askQty":"币安现货卖一量",
        "bidPrice":"币安现货买一",
        "bidQty":"币安现货买一量",
    })
binance_spot_ticker.to_csv("binance_spot_ticker.csv")
print("现货ticker",binance_spot_ticker)
binance_spot_ticker=binance_spot_ticker[["代码","币安现货现价","币安现货24小时成交额","币安现货24小时成交量","币安现货涨跌幅","币安现货标记时间","币安现货卖一","币安现货卖一量","币安现货买一","币安现货买一量",]]

# 当多平台套利的时候因为拼接需要才使用下面的代码
binance_spot_ticker["代码"] = binance_spot_ticker["代码"].str.replace("USDT","").astype(str)
binance_contract_coin_mark_price["代码"] = binance_contract_coin_mark_price["代码"].str.replace("USDT","").astype(str)
gate_spot_ticker["代码"] = gate_spot_ticker["代码"].str.replace("_USDT","").astype(str)
gate_contract_ticker["代码"] = gate_contract_ticker["代码"].str.replace("_USDT","").astype(str)

# # 币安平台内期现套利
# tradedf=pd.merge(binance_spot_ticker,binance_contract_coin_mark_price, on='代码', how='inner')
# # 【这里是空现货多合约】
# # tradedf["币安现货溢价率"]=(tradedf["币安现货买一"].astype(float))/(tradedf["币安合约现价"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# # tradedf=tradedf[tradedf["币安现货溢价率"]>1]
# # tradedf["性价比"]=(-tradedf["币安现货溢价率"].astype(float))*(tradedf["币安合约溢价率"]-1)#做空合约所以资金费率最好是正的
# # 【这里是空合约多现货】
# tradedf["币安合约溢价率"]=(tradedf["币安合约现价"].astype(float))/(tradedf["币安现货卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[tradedf["币安合约溢价率"]>1.002]#大于千分之二的话扣除手续费之后还有利润
# tradedf["性价比"]=(tradedf["币安合约资金费率"].astype(float))*(tradedf["币安合约溢价率"]-1)#做空合约所以资金费率最好是正的
# tradedf.to_csv("tradedf币安期现.csv")

# 比特儿平台内期现套利
tradedf=pd.merge(gate_spot_ticker,gate_contract_ticker, on='代码', how='inner')
# 【这里是空现货多合约】
# tradedf["比特儿现货溢价率"]=tradedf["比特儿现货买一"].astype(float)/tradedf["比特儿合约卖一"].astype(float)#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[tradedf["比特儿现货溢价率"]>1]
# tradedf["性价比"]=(-tradedf["比特儿现货溢价率"].astype(float))*(tradedf["比特儿合约溢价率"]-1)#做空合约所以资金费率最好是正的
# 【这里是空合约多现货】
tradedf["比特儿合约溢价率"]=tradedf["比特儿合约买一"].astype(float)/tradedf["比特儿现货卖一"].astype(float)#买一比卖一的贵了才有套利空间【这个数越大越好】
tradedf=tradedf[tradedf["比特儿合约溢价率"]>1.002]#大于千分之二的话扣除手续费之后还有利润
tradedf["性价比"]=(tradedf["比特儿合约资金费率"].astype(float))*(tradedf["比特儿合约溢价率"]-1)#做空合约所以资金费率最好是正的
print(tradedf)
tradedf.to_csv("tradedf比特儿期现.csv")

# 做空币安做多比特儿
tradedf=pd.merge(gate_contract_ticker,binance_contract_coin_mark_price, on='代码', how='inner')
tradedf["币安合约溢价率"]=(tradedf["币安合约现价"].astype(float))/(tradedf["比特儿合约卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
tradedf=tradedf[(tradedf["币安合约溢价率"]>1.002)]
tradedf.to_csv("tradedf做空币安做多比特儿.csv")

# # 做多币安做空比特儿
# tradedf=pd.merge(gate_contract_ticker,binance_contract_coin_mark_price, on='代码', how='inner')
# tradedf["比特儿合约溢价率"]=(tradedf["比特儿合约买一"].astype(float))/(tradedf["币安合约现价"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["比特儿合约溢价率"]>1.002)]
# tradedf.to_csv("tradedf做多币安做空比特儿.csv")

# # 融券币安现货持仓比特儿现货
# tradedf=pd.merge(gate_spot_ticker,binance_spot_ticker, on='代码', how='inner')
# # 【这里是持仓币安现货做空比特儿期货】
# tradedf["币安现货溢价"]=(tradedf["币安现货买一"].astype(float))/(tradedf["比特儿现货卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["币安现货溢价"]>1.002)]
# tradedf.to_csv("tradedf融券币安现货持仓比特儿现货.csv")

# # 融券比特儿现货持仓币安现货
# tradedf=pd.merge(gate_spot_ticker,binance_spot_ticker, on='代码', how='inner')
# # 【这里是持仓币安现货做空比特儿期货】
# tradedf["比特儿现货溢价"]=(tradedf["比特儿现货买一"].astype(float))/(tradedf["币安现货卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["比特儿现货溢价"]>1.002)]
# tradedf.to_csv("tradedf融券比特儿现货持仓币安现货.csv")

# # 币安现货比特儿期货套利
# tradedf=pd.merge(gate_contract_ticker,binance_spot_ticker, on='代码', how='inner')
# # 【这里是持仓币安现货做空比特儿期货】
# tradedf["持仓币安现货做空比特儿"]=(tradedf["比特儿合约卖一"].astype(float))/(tradedf["币安现货买一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["持仓币安现货做空比特儿"]>1.002)]
# tradedf=tradedf[tradedf["比特儿合约资金费率"].astype(float)>0]
# tradedf.to_csv("tradedf持仓币安现货做空比特儿.csv")

# # 持仓币安现货做空比特儿期货
# tradedf=pd.merge(gate_contract_ticker,binance_spot_ticker, on='代码', how='inner')
# tradedf["持仓币安现货做空比特儿期货"]=(tradedf["比特儿合约买一"].astype(float))/(tradedf["币安现货卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["持仓币安现货做空比特儿期货"]>1.002)]
# tradedf=tradedf[tradedf["比特儿合约资金费率"].astype(float)>0]
# tradedf.to_csv("tradedf持仓币安现货做空比特儿期货.csv")

# # 持仓比特儿现货做空币安期货
# tradedf=pd.merge(gate_spot_ticker,binance_contract_coin_mark_price, on='代码', how='inner')
# tradedf["持仓比特儿现货做空币安期货"]=(tradedf["币安合约现价"].astype(float))/(tradedf["比特儿现货卖一"].astype(float))#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf=tradedf[(tradedf["持仓比特儿现货做空币安期货"]>1.002)]
# tradedf=tradedf[tradedf["币安合约资金费率"].astype(float)>0]
# tradedf.to_csv("tradedf持仓比特儿现货做空币安期货.csv")