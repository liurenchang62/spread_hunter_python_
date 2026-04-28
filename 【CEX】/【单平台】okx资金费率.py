# #【APIkey需要绑定IP，香港IP可以执行交易】

# import logging#打印日志
import pandas as pd
import math
import time
import datetime
# pip install python-okx
import okx.Trade as Trade
import okx.Funding as Funding
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as MarketData
import okx.PublicData as PublicData
# 实时交易网址：https://www.okx.com/docs-v5/en/#overview-production-trading-services
# 模拟交易网址：https://www.okx.com/docs-v5/en/#overview-demo-trading-services
# API配置
api_key = '8635667b-0702-4034-ab65-ff58275a0556'
secret_key = '5A133B8EDFA08199FD4733DD4338D712'
passphrase_key = 'wthWTH00.'
flag_key="0"#等于0的时候是实盘，等于1的时候是模拟盘

# 启动账户服务器
okx_AccountAPI=Account.AccountAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# print(okx_AccountAPI.get_account_balance())
okx_account=pd.DataFrame(okx_AccountAPI.get_account_balance()["data"])
print("账户余额",okx_account)
okx_positions=pd.DataFrame(okx_AccountAPI.get_positions()["data"])
print("当前持仓",okx_positions)

# # 获取币种列表
# okx_FundingAPI=Funding.FundingAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# okx_funding=pd.DataFrame(okx_FundingAPI.get_currencies()["data"])
# okx_funding=okx_funding.rename(columns={"name":"代码","chain":"链名","canInternal":"当前是否可以内部转账","expTime":"下线时间","listTime":"上线时间"})
# okx_funding.to_csv("__okx_funding.csv")
# print(okx_funding)

# 启动公共数据服务器
okx_PublicAPI = PublicData.PublicAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)

# # 获取市场借币杠杆利率和借币限额
# okx_interest_rate_loan_quota=okx_PublicAPI.get_interest_rate_loan_quota() # 利率贷款额度
# print("市场借币杠杆利率和借币限额",okx_interest_rate_loan_quota)

# 获取现货交易对
okx_spot=pd.DataFrame(okx_PublicAPI.get_instruments("SPOT")["data"]) # 获取所有现货交易对
okx_spot=okx_spot[okx_spot["state"]=="live"] # 去掉已经退市的标的
okx_spot=okx_spot[okx_spot["instId"].str.endswith("USDT")] # 去掉非USDT交易对之后是84个
okx_spot=okx_spot.rename(columns={"instId":"代码","instType":"类型","instFamily":"对应的现货标的","expTime":"下线时间","listTime":"上线时间"})
okx_spot_symbols=okx_spot["代码"].tolist()
okx_spot.to_csv("okx现货交易对详情.csv")
print("okx现货交易对详情",okx_spot)
# 获取合约交易对
okx_swap=pd.DataFrame(okx_PublicAPI.get_instruments("SWAP")["data"]) # 获取所有永续合约交易对【118个】
okx_swap=okx_swap[okx_swap["state"]=="live"] # 去掉已经退市的标的
okx_swap=okx_swap[okx_swap["instFamily"].str.endswith("USDT")] # 去掉非USDT交易对之后是84个
okx_swap=okx_swap.rename(columns={"instId":"代码","instType":"类型","instFamily":"对应的现货标的","expTime":"下线时间","listTime":"上线时间"})
okx_swap_symbols=okx_swap["代码"].tolist()
okx_swap.to_csv("okx合约交易对详情.csv")
print("okx合约交易对详情",okx_swap)
# okx_futures=pd.DataFrame(okx_PublicAPI.get_instruments("FUTURES")["data"]) # 获取所有交割合约交易对
# okx_margin=pd.DataFrame(okx_PublicAPI.get_instruments("MARGIN")["data"]) # 获取所有币币杠杆交易对
# okx_option=pd.DataFrame(okx_PublicAPI.get_instruments("OPTION")["data"]) # 获取所有期权交易对

# 启动市场数据服务器
okx_MarketAPI=MarketData.MarketAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# # 获取现货ticker
# okx_spot_ticker=pd.DataFrame(okx_MarketAPI.get_tickers(instType="SPOT")["data"])
# okx_spot_ticker=okx_spot_ticker.rename(columns={"instId":"代码","askPx":"OK现货买一","askSz":"OK现货买一量","bidPx":"OK现货卖一","bidSz":"OK现货卖一量","volCcy24h":"OK现货24小时成交量","ts":"时间戳"})
# print(okx_spot_ticker)
# okx_spot_ticker.to_csv("okx_spot_ticker.csv")
# # 获取合约ticker
# okx_swap_ticker=pd.DataFrame(okx_MarketAPI.get_tickers(instType="SWAP")["data"])
# okx_swap_ticker=okx_swap_ticker.rename(columns={"instId":"代码","askPx":"OK合约买一","askSz":"OK合约买一量","bidPx":"OK合约卖一","bidSz":"OK合约卖一量","volCcy24h":"OK合约24小时成交量","ts":"时间戳"})
# print(okx_swap_ticker)
# okx_swap_ticker.to_csv("okx_swap_ticker.csv")
# okx_swap_ticker["代码"] = okx_swap_ticker["代码"].str.replace("-SWAP","").astype(str)#去掉合约的后缀
# # OK平台内期现套利
# print(datetime.datetime.now())
# okx_tradedf=pd.merge(okx_spot_ticker,okx_swap_ticker, on='代码', how='inner')
# # 【这里是空现货多合约】
# # okx_tradedf["OK现货溢价率"]=okx_tradedf["OK现货买一"].astype(float)/okx_tradedf["OK合约卖一"].astype(float)#买一比卖一的贵了才有套利空间【这个数越大越好】
# # okx_tradedf=okx_tradedf[okx_tradedf["OK现货溢价率"]>1]
# # 【这里是空合约多现货】
# okx_tradedf["OK合约溢价率"]=okx_tradedf["OK合约买一"].astype(float)/okx_tradedf["OK现货卖一"].astype(float)#买一比卖一的贵了才有套利空间【这个数越大越好】
# okx_tradedf=okx_tradedf[okx_tradedf["OK合约溢价率"]>1.002]#大于千分之二的话扣除手续费之后还有利润
# print(okx_tradedf)
# okx_tradedf.to_csv("okx期现价差.csv")

# 获取永续合约当前资金费率【okx的费率非常小，最大的仅仅千分之三左右】
for symbol in okx_swap["代码"].tolist():
    time.sleep(0.1)#避免限频
    result = okx_PublicAPI.get_funding_rate(instId=symbol)['data']#查询对应交易对的资金费率
    print(result)
    okx_swap.loc[okx_swap["代码"]==symbol,"资金费率"]=result[0]["fundingRate"]
okx_swap=okx_swap.sort_values(by="资金费率")
okx_swap.to_csv("okx_swap资金费率.csv")