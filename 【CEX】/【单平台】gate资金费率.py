# #【APIkey需要绑定IP，香港IP可以执行交易】
# 【gate的资金费率水平略低与bitget】大概千分之七左右，说明老交易所做套利的多，竞争比较激烈

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
    gate_contract_symbols=gate_contract_info_df["name"].tolist()
    return gate_contract_symbols
def getsymbol():
    # gate_spot_symbols=getgatespot()#获取现货标的
    gate_contract_symbols=getgatefuture()#获取合约标的
    ##获取所有现货交易对tick信息
    gate_spot_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/spot/tickers', headers=gate_headers).json())#现货ticker
    gate_spot_ticker=gate_spot_ticker[["currency_pair","last","quote_volume","lowest_ask","highest_bid",]]
    gate_spot_ticker=gate_spot_ticker[gate_spot_ticker["currency_pair"].isin(gate_contract_symbols)]#只要非杠杆代币
    gate_spot_ticker=gate_spot_ticker.rename(columns={
            "currency_pair":"代码",
            "last":"比特儿现货现价",
            "quote_volume":"比特儿现货24小时成交额",#计价货币
            # "base_volume":"比特儿现货24小时成交量",#基础货币
            # "change_percentage":"比特儿现货涨跌幅",
            "lowest_ask":"比特儿现货卖一",
            "highest_bid":"比特儿现货买一",
        })
    # gate_spot_ticker.to_csv("gate_spot_ticker.csv")
    ##获取所有标的的当期或下期资金费率【这里默认获取的是交割合约的费率】
    # gate_contract_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/delivery/usdt/tickers', headers=gate_headers).json())#交割合约ticker
    gate_contract_ticker=pd.DataFrame(requests.request('GET', gate_host_prefix + '/futures/usdt/tickers', headers=gate_headers).json())#永续合约ticker
    gate_contract_ticker=gate_contract_ticker[["contract","last","volume_24h_quote","lowest_ask","highest_bid","funding_rate",]]
    gate_contract_ticker=gate_contract_ticker[gate_contract_ticker["contract"].isin(gate_contract_symbols)]#只要非杠杆代币
    gate_contract_ticker=gate_contract_ticker.rename(columns={
            "contract":"代码",
            "last":"比特儿合约现价",
            "volume_24h_quote":"比特儿合约24小时成交额",#计价货币
            # "volume_24h_base":"比特儿合约24小时成交量",#基础货币
            # "change_percentage":"比特儿合约涨跌幅",
            "lowest_ask":"比特儿合约卖一",
            "highest_bid":"比特儿合约买一",
            # "basis_rate":"比特儿合约基差率",
            # "total_size":"比特儿合约总持仓量",
            # "funding_rate_indicative":"比特儿合约下一周期预测资金费率",
            "funding_rate":"比特儿合约资金费率",#这里的资金费率是动态的所以基本上结算的时候偏差不会太大
        })
    return gate_spot_ticker,gate_contract_ticker
# 比特儿平台内期现套利
print("选股开始",datetime.datetime.now())
gate_spot_ticker,gate_contract_ticker=getsymbol()
tradedf=pd.merge(gate_spot_ticker,gate_contract_ticker,on='代码',how='inner')

tradedf["比特儿合约买一"]=tradedf["比特儿合约买一"].astype(float)
tradedf["比特儿合约卖一"]=tradedf["比特儿合约卖一"].astype(float)
tradedf["比特儿现货买一"]=tradedf["比特儿现货买一"].astype(float)
tradedf["比特儿现货卖一"]=tradedf["比特儿现货卖一"].astype(float)
tradedf["比特儿合约资金费率"]=tradedf["比特儿合约资金费率"].astype(float)

tradedf["比特儿现货盘口价差"]=tradedf["比特儿现货买一"]/tradedf["比特儿现货卖一"]
tradedf["比特儿合约盘口价差"]=tradedf["比特儿合约买一"]/tradedf["比特儿合约卖一"]
tradedf["比特儿现货溢价率"]=tradedf["比特儿现货买一"]/tradedf["比特儿合约卖一"]#买一比卖一的贵了才有套利空间【这个数越大越好】
tradedf["比特儿合约溢价率"]=tradedf["比特儿合约买一"]/tradedf["比特儿现货卖一"]#买一比卖一的贵了才有套利空间【这个数越大越好】
# tradedf["比特儿现货溢价率（理论）"]=tradedf["比特儿现货盘口价差"]*tradedf["比特儿合约盘口价差"]*tradedf["比特儿合约溢价率"]


# 【合约maker手续费万二taker手续费万五，现货maker和taker手续费都是千二】
tradedf["比特儿现货24小时成交额"]=tradedf["比特儿现货24小时成交额"].astype(float)
# tradedf=tradedf.nlargest(math.ceil(len(tradedf)/2), "比特儿现货24小时成交额")
# tradedf=tradedf[tradedf["比特儿现货24小时成交额"]>100000]
tradedf["比特儿合约24小时成交额"]=tradedf["比特儿合约24小时成交额"].astype(float)
# tradedf=tradedf.nlargest(math.ceil(len(tradedf)/2), "比特儿合约24小时成交额")
# tradedf=tradedf[tradedf["比特儿合约24小时成交额"]>100000]

tradedf=tradedf.sort_values(by="比特儿合约资金费率")
tradedf.to_csv("gatetradedf.csv")

# # # 【空合约多现货】先挂现货，成交后去合约对冲
# # buydf=tradedf
# # buydf=buydf[buydf["比特儿合约资金费率"]>0.00001]
# # buydf=buydf[buydf["比特儿合约溢价率"]>1.001]#大于千分之二的话扣除手续费之后还有利润
# # buydf=buydf.nlargest(math.ceil(5),"比特儿合约资金费率")
# buydf.to_csv("gatebuydf.csv")

# # 【卖出时多合约卖现货】
# selldf=tradedf
# selldf=selldf[selldf["比特儿合约溢价率"]>0.999]
# selldf.to_csv("gateselldf.csv")

# #配置gate服务器【下面的报错应该是改了api了】
# import gate_api
# configuration=gate_api.Configuration(
# host="https://api.gateio.ws/api/v4",
# key="94df526c2e81d2030138c99caac1e106",
# secret="4372cac9f4424605e959661d4871a7a9cb394207eadf7a1e969d9943d55709d2",
# )
# gateclient=gate_api.ApiClient(configuration)

# #查询账户信息
# gate_accountclient=gate_api.AccountApi(gateclient)#启动账户API服务器
# gate_account=gate_accountclient.get_account_detail()
# print("account账户信息",gate_account)

# # 获取钱包总余额
# gate_walletclient=gate_api.WalletApi(gateclient)#启动钱包API服务器
# gate_account=gate_walletclient.get_total_balance()#检查各模块余额
# gate_account=gate_walletclient.list_sub_account_balances()#检查子账户余额
# # gate_account=gate_walletclient.list_sub_account_margin_balances()#检查子账户保证金余额
# # gate_account=gate_walletclient.list_sub_account_futures_balances()#检查子账户期货账户余额

# print("各模块资产余额",gate_account,gate_account.details["futures"].amount,gate_account.details["spot"].amount)
# gate_futures_amount=float(gate_account.details["futures"].amount)
# gate_spot_amount=float(gate_account.details["spot"].amount)
# print("合约余额",gate_futures_amount,"现货余额",gate_spot_amount)
# if (gate_spot_amount>0)or(gate_futures_amount>0):
#     if (gate_spot_amount-gate_futures_amount)>(gate_spot_amount+gate_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
#         thisamount=(gate_spot_amount-gate_futures_amount)/2
#         print("现货仓位减去合约仓位较重，需要平衡以下金额的仓位",thisamount)
#         transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',settle="USDT",_from='spot',to='futures',amount=thisamount))#合约转现货
#     elif (gate_futures_amount-gate_spot_amount)>(gate_spot_amount+gate_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
#         thisamount=(gate_spot_amount-gate_futures_amount)/2
#         print("现货仓位减去合约仓位较轻，需要平衡以下金额的仓位",thisamount)
#         transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',settle="USDT",_from='futures',to='spot',amount=-thisamount))#合约转现货
#     else:
#         print("资金均匀不用调整")

# #获取gate合约各个标的的手续费
# gate_futures_fee=gate_futureclient.get_futures_fee(settle='usdt')
# gate_futures_fee_df=pd.json_normalize(gate_futures_fee)
# # gate_futures_fee_df.to_csv(f"gate_futures_fee.csv")#这里是纵向排列的
# print(gate_futures_fee_df)
# # print("BTC_USDT手续费",gate_futures_fee_df["BTC_USDT"].values[0].maker_fee)


# #查询期货余额和期货持仓
# gate_futureclient=gate_api.FuturesApi(gateclient)#启动期货API服务器
# positions=gate_futureclient.list_positions(settle='usdt')#查询期货账户持仓
# print(positions)
# account_book=gate_futureclient.list_futures_accounts(settle='usdt')#查询期货账户余额
# print(account_book)

# #启动杠杆交易服务器【主要用于交易】
# gate_marginclient=gate_api.MarginApi(gateclient)
# transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',currency_pair="BTC_USDT",_from='spot',to='cross_margin',amount=0.1))#现货转杠杆
# # transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',currency_pair="BTC_USDT",_from='cross_margin',to='spot',amount=0.1))#杠杆转现货
# # margin_estimate_rate=gate_marginclient.create_cross_margin_loan(gate_api.CrossMarginLoan())#借入全仓杠杆代币
# # margin_estimate_rate=gate_marginclient.repay_cross_margin_loan(gate_api.CrossMarginRepayRequest())#全仓杠杆代币还款
# margin_estimate_rate=gate_marginclient.get_cross_margin_estimate_rate("BTC")
# print("杠杆借币利率",margin_estimate_rate)


# # # 查询深度信息
# # buysymbols=["BTC_USDT","ETH_USDT"]
# buysymbols=["BTC_USDT"]
# # buysymbols=["LTC_USDT"]

# #设置交易参数并且获取买卖计划
# bidrate=0.01#实盘的时候设置盘口价差为0.001
# timetickwait=1#设置每次下单时确认是否是最新tick的确认时间
# buyorderroad=False#买入进程默认关闭,只有卖出计划结束时才重启
# print(f"gate选股结束，执行交易计划")
# dfordercancelled=pd.DataFrame({})#初始化存储已经撤销订单的列表【只初始化一次,不要重置】

# # gate_ticker=gate_futureclient.list_futures_order_book(settle='usdt',contract=buysymbol)#当前买卖十档
# # print("当前十档",gate_ticker)









# #【【【一个没有实际价值多头轮动策略】】】
# # import logging#打印日志
# import pandas as pd
# import math
# import time
# import datetime

# #获取gate数据
# import requests#配置post访问头
# # gate_host_prefix="https://api.gateio.ws/api/v4"#实盘
# gate_host_prefix="https://fx-api-testnet.gateio.ws/api/v4"#模拟
# gate_headers={'Accept':'application/json','Content-Type':'application/json'}
# # 比特儿平台内期现套利
# print("选股开始",datetime.datetime.now())
# #获取合约交易对【只要非杠杆代币】
# gate_contract_info_df=pd.DataFrame(requests.request('GET',gate_host_prefix+'/futures/usdt/contracts',headers=gate_headers).json())
# gate_contract_info_df=gate_contract_info_df[gate_contract_info_df["in_delisting"]==False]#去掉已退市标的
# gate_contract_info_df=gate_contract_info_df.rename(columns={
#                             "name":"代码",
#                             "quanto_multiplier":"下单量最小变动单位",#价格为空就表面当日停牌
#                             "order_price_round":"下单价格最小变动单位",#一张代表多少币
#                             "mark_price_round":"标记价格最小变动单位",
#                             "leverage_min": "最小杠杆",
#                             "leverage_max": "最大杠杆",
#                             "maker_fee_rate": "maker手续费",
#                             "taker_fee_rate": "taker手续费",
#                             "funding_rate": "资金费率",
#                             "order_size_max": "最大下单规模",
#                             "short_users": "空头用户",
#                             "long_users": "多头用户",
#                             "create_time": "创建时间",
#                         })
# gate_contract_info_df.to_csv("gate_contract_info_df.csv")
# print("选股结束",datetime.datetime.now())
# # [
# #   {
# #     "name": "BTC_USDT",
# #     "type": "direct",
# #     "quanto_multiplier": "0.0001",#下单量的最小变动单位
# #     "ref_discount_rate": "0",#参考贴现率
# #     "order_price_deviate": "0.5",#订单价格偏差
# #     "maintenance_rate": "0.005",#维护速率
# #     "mark_type": "index",#标记价格
# #     "last_price": "38026",#最新价格
# #     "mark_price": "37985.6",
# #     "index_price": "37954.92",
# #     "funding_rate_indicative": "0.000219",#资金费率（预测）
# #     "mark_price_round": "0.01",#最小变动价（标记）
# #     "funding_offset": 0,
# #     "in_delisting": false,
# #     "risk_limit_base": "1000000",
# #     "interest_rate": "0.0003",#利率
# #     "order_price_round": "0.1",
# #     "order_size_min": 1,
# #     "ref_rebate_rate": "0.2",
# #     "funding_interval": 28800,
# #     "risk_limit_step": "1000000",
# #     "leverage_min": "1",#最小杠杆
# #     "leverage_max": "100",#最大杠杆
# #     "risk_limit_max": "8000000",
# #     "maker_fee_rate": "-0.00025",#maker手续费
# #     "taker_fee_rate": "0.00075",#taker手续费
# #     "funding_rate": "0.002053",#资金费率
# #     "order_size_max": 1000000,#最大下单规模
# #     "funding_next_apply": 1610035200,
# #     "short_users": 977,#空头用户
# #     "config_change_time": 1609899548,
# #     "trade_size": 28530850594,
# #     "position_size": 5223816,
# #     "long_users": 455,#多头用户
# #     "funding_impact_value": "60000",
# #     "orders_limit": 50,
# #     "trade_id": 10851092,
# #     "orderbook_id": 2129638396,
# #     "enable_bonus": true,
# #     "enable_credit": true,
# #     "create_time": 1669688556,#创建时间
# #     "funding_cap_ratio": "0.75"
# #   }
# # ]

# # 47.242.111.133【阿里云服务器IP】绑定了之后需要等几分钟才能使用
# import pandas as pd
# import math
# import time
# import datetime
# #配置gate服务器【下面的报错应该是改了api了】
# import gate_api

# configuration=gate_api.Configuration(
# # #实盘
# host="https://api.gateio.ws/api/v4",
# key="7bbe5f1899b5fcfdf05b57d92ba603c1",
# secret="9e073f55f7abc9bb856c3c02f14e8c44adb1da791f7d0950d13cda3f04579c0c",
# # #模拟
# # host="https://fx-api-testnet.gateio.ws/api/v4",
# # key="6dde70328d93c6c4918605b39ff86e36",
# # secret="5ffd37cfd686037d97fafc5699fd9716a3ef6699300e311838b67eb167022c23",
# #username=None,
# #password=None,
# #discard_unknown_keys=False,
# )
# gateclient=gate_api.ApiClient(configuration)

# #查询账户信息
# gate_accountclient=gate_api.AccountApi(gateclient)#启动账户API服务器
# gate_account=gate_accountclient.get_account_detail()
# print("account账户信息",gate_account)

# #启动钱包API服务器
# gate_walletclient=gate_api.WalletApi(gateclient)
# gate_account=gate_walletclient.get_total_balance()#检查各模块余额# 获取钱包总余额
# print("各模块资产余额",gate_account,"期货余额",gate_account.details["futures"].amount,"现货余额",gate_account.details["spot"].amount)
# # gate_account=gate_walletclient.list_sub_account_balances()#检查子账户余额
# # gate_account=gate_walletclient.list_sub_account_margin_balances()#检查子账户保证金余额
# # gate_account=gate_walletclient.list_sub_account_futures_balances()#检查子账户期货账户余额

# #启动期货API服务器
# gate_futureclient=gate_api.FuturesApi(gateclient)
# #查询期货账户持仓
# # positions=gate_futureclient.list_positions(settle='usdt')
# # print(positions)
# # #查询期货账户余额
# account_book=gate_futureclient.list_futures_accounts(settle='usdt')
# available_money=account_book.available
# total_money=account_book.total
# print(account_book,available_money,total_money)

# # #【合约现货平衡】改成理财现货平衡[应该就是金融账户]gate_spot
# # details【-cross_margin:全仓杠杆账户
# # -spot:现货账户
# # -finance:金融账户
# # -margin:杠杆账户
# # -quant:量化账户
# # -futures:永续合约账户
# # -delivery:交割合约账户
# # -warrant:warrant 账户
# # -cbbc:牛熊证账户】
# # gate_futures_amount=float(gate_account.details["futures"].amount)
# # gate_spot_amount=float(gate_account.details["spot"].amount)
# # print("合约余额",gate_futures_amount,"现货余额",gate_spot_amount)
# # if (gate_spot_amount>0)or(gate_futures_amount>0):
# #     if (gate_spot_amount-gate_futures_amount)>(gate_spot_amount+gate_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
# #         thisamount=(gate_spot_amount-gate_futures_amount)/2
# #         print("现货仓位减去合约仓位较重，需要平衡以下金额的仓位",thisamount)
# #         transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',settle="USDT",_from='spot',to='futures',amount=thisamount))#合约转现货
# #     elif (gate_futures_amount-gate_spot_amount)>(gate_spot_amount+gate_futures_amount)*0.1:#这里是差大概百分之五【0.1的一半】就会触发资金管理
# #         thisamount=(gate_spot_amount-gate_futures_amount)/2
# #         print("现货仓位减去合约仓位较轻，需要平衡以下金额的仓位",thisamount)
# #         transfer_response =gate_walletclient.transfer(gate_api.Transfer(currency='USDT',settle="USDT",_from='futures',to='spot',amount=-thisamount))#合约转现货
# #     else:
# #         print("资金均匀不用调整")

# gate_spotclient=gate_api.SpotApi(gateclient)#启动现货API服务器
# #获取gate合约各个标的的手续费
# gate_spot_fee=gate_spotclient.get_fee()
# print(gate_spot_fee)#gt_maker_fee是使用gt抵扣后的费用{'currency_pair': None, 'debit_fee': 1, 'gt_discount': True, 'gt_maker_fee': '0.0009', 'gt_taker_fee': '0.0009', 'loan_fee': '0.18', 'maker_fee': '0.001', 'point_type': '1', 'taker_fee': '0.001', 'user_id': 462377}
# print("手续费",gate_spot_fee.maker_fee,gate_spot_fee.taker_fee)




# # 查询深度信息
# buysymbol="BTC_USDT"
# gate_ticker=gate_spotclient.list_order_book(currency_pair=buysymbol)#当前买卖十档
# bid1=gate_ticker.bids[0][0]
# bid1v=gate_ticker.bids[0][1]
# bid2=gate_ticker.bids[1][0]
# bid2v=gate_ticker.bids[1][1]
# ask1=gate_ticker.asks[0][0]
# ask1v=gate_ticker.asks[0][1]
# ask2=gate_ticker.asks[1][0]
# ask2v=gate_ticker.asks[1][1]
# print("当前十档",gate_ticker)
# print(bid1,bid1v,bid2,bid2v,ask1,ask1v,ask2,ask2v,)



# #设置交易参数并且获取买卖计划
# bidrate=0.01#实盘的时候设置盘口价差为0.001
# timetickwait=1#设置每次下单时确认是否是最新tick的确认时间
# buyorderroad=False#买入进程默认关闭,只有卖出计划结束时才重启
# print(f"~~~选股结束，执行交易计划")
# dfordercancelled=pd.DataFrame({})#初始化存储已经撤销订单的列表【只初始化一次,不要重置】
# buysymbol="BTC_USDT"
# while True:
#     dfordercancelled.to_csv(f"___dfordercancelled.csv")
#     dforderthiscancelled=pd.DataFrame({})#初始化存储全部订单的列表【每一轮都可以重置】【仅仅针对开放订单】
#     time.sleep(2)#在这里为撤单函数保留时间【不通过计算挂单时间，因为这里没有针对持仓的冻结说明】
#     # 遍历所有合约交易对，并获取历史 K 线数据  
#     klines = gate_futureclient.list_futures_candlesticks(settle='usdt',contract=buysymbol, limit=20, interval="1m")  
#     data_list = []  
#     for kline in klines: 
#         timestamp = int(kline.t)  
#         date = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(timestamp))  
#         data_list.append({  
#             "timestamp": timestamp,  
#             "代码": buysymbol,  
#             "日期": date,  
#             "成交额": float(kline.sum),  
#             "收盘": float(kline.c),  
#             "最高": float(kline.h),  
#             "最低": float(kline.l),  
#             "开盘": float(kline.o),  
#             "成交量": float(kline.v),  
#         })  
#     df_line = pd.DataFrame(data_list)
#     df_line["grow"]=df_line["收盘"]/df_line["开盘"]
#     # df_line=df_line[df_line["grow"]>1.001]
#     # print(df_line,len(df_line))
#     # if len(df_line)>=20:
#     df_line=df_line[df_line["grow"]>0.5]#测试
#     print(df_line,len(df_line))
#     if len(df_line)>=2:#测试
#         # thisticker=gate_futureclient.list_futures_order_book(settle='usdt',contract=buysymbol)#当前买卖十档
#         # ask_price_1=thisticker.asks[0].p#卖一价
#         # ask_vol_1=thisticker.asks[0].s#卖一量
#         # bid_price_1=thisticker.bids[0].p#买一价
#         # bid_vol_1=thisticker.bids[0].s#买一量
#         # print("当前十档",thisticker,"卖一",ask_price_1,"买一",bid_price_1)
#         # open_price=ask_price_1#多头开单价格为卖一价格
#         # # futures_order=gate_futureclient.create_futures_order(settle='usdt',futures_order = gate_api.FuturesOrder(contract=buysymbol,size=int(100),price=open_price))
#         # futures_order=gate_futureclient.create_futures_order(
#         #     settle='usdt',futures_order = gate_api.FuturesOrder(
#         #         contract=buysymbol,size=int(100),price="40000"))
#         # print(f"~~~创建新的订单",futures_order)

#         # {'amend_text': '-',
#         # 'auto_size': None,
#         # 'biz_info': '-',
#         # 'close': False,#设置为“true”平仓，“size”设置为 0
#         # 'contract': 'BTC_USDT',#期货交易合同
#         # 'create_time': 1702883594.174,
#         # 'fill_price': '0',
#         # 'finish_as': None,#订单是如何完成的。- filled： 全部填充 - cancelled：手动取消 - liquidated：因清算而取消 - ioc：生效时间为“IOC”，立即完成 - auto_deleveraged：由 ADL 完成 - reduce_only：由
#         # 'finish_time': None,#订单完成时间。如果订单未结，则不予退还
#         # 'iceberg': 0,
#         # 'id': 933479298,
#         # 'is_close': False,#是平仓订单
#         # 'is_liq': False,
#         # 'is_reduce_only': False,
#         # 'left': 100,#剩余待交易规模
#         # 'mkfr': '0.00015',
#         # 'price': '40000',#订单价格。0 表示市价单，将“tif”设置为“ioc”
#         # 'reduce_only': False,
#         # 'refu': 0,
#         # 'size': 100,#订单大小【单位是张】，指定正数进行出价，指定负数进行询价
#         # 'status': 'open',#订单状态 - 'open'： 等待交易 - 'finished'： 完成
#         # 'stp_act': '-',
#         # 'stp_id': 0,
#         # 'text': 'api',
#         # 'tif': 'gtc',
#         # 'tkfr': '0.00046',
#         # 'user': 462377}
#         open_futures_orders=gate_futureclient.list_futures_orders(settle='usdt',status='open')#获取未成交订单
#         print(f"~~~获取未成交订单",open_futures_orders)
#         # # cancel_futures_orders=gate_futureclient.cancel_futures_orders(settle='usdt',contract=buysymbol)#好像是因为没钱报错
#         # # print(f"~~~撤销所有订单",cancel_futures_orders)
#         for open_futures_order in open_futures_orders:
#             print(open_futures_order)
#             this_futures_order=open_futures_order.id#获取开放订单的id
#             cancel_futures_order=gate_futureclient.cancel_futures_order(settle='usdt',order_id=this_futures_order)#撤空单的返回值是没找到这个订单
#             print(f"~~~撤销个别订单",cancel_futures_order)
#             cancel_vol=cancel_futures_order.left#撤销掉的数量【剩余数量】
#             trade_vol=cancel_futures_order.size-cancel_futures_order.left#已经成交的数量


#     # 固定时间清仓【这里是获取持仓状态】
#     list_futures_positions=gate_futureclient.list_positions(settle='usdt')
#     for futures_position in list_futures_positions:
#         print(f"~~~持仓处理",futures_position)
#         close_contract=futures_position.contract
#         close_size=futures_position.size
#         thisticker=gate_futureclient.list_futures_order_book(settle='usdt',contract=buysymbol)#当前买卖十档
#         ask_price_1=thisticker.asks[0].p#卖一价
#         ask_vol_1=thisticker.asks[0].s#卖一量
#         bid_price_1=thisticker.bids[0].p#买一价
#         bid_vol_1=thisticker.bids[0].s#买一量
#         if close_size>0:
#             #清仓成功之后数据仍然保留在持仓列表当中，但是size为0，这样的话有一个好处，就是所有平仓都是将仓位调整为0，不会过度平仓导致了仓位反转
#             close_price=bid_price_1
#             close_futures_order=gate_futureclient.create_futures_order(
#                 settle='usdt',futures_order = gate_api.FuturesOrder(
#                     contract=close_contract,size=0,price=close_price,close=True))
#             print(close_futures_order)
#     break