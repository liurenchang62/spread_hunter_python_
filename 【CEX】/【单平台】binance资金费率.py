# # # #  安装币安的python库
# # # # pip install python-binance
# # # from binance.client import Client
# # # import time
# # # import pandas as pd

# # # ### 在线读取 ###
# # # # 币安的api配置
# # # api_key = "0jmNVvNZusoXKGkwnGLBghPh8Kmc0klh096VxNS9kn8P0nkAEslVUlsuOcRoGrtm"
# # # api_secret = "PbSWkno1meUckhmkLyz8jQ2RRG7KgmZyAWhIF0qPdCJrmDSFxoxGdMG5gZeYYCgy"
# # # # 创建Binance客户端
# # # client = Client(api_key, api_secret)
# # # # 获取所有USDT计价的现货交易对及其详情
# # # df=pd.json_normalize(client.get_exchange_info(),record_path='symbols')
# # # df=df[df["quoteAsset"]=="USDT"]
# # # df=df[~df["symbol"].str.contains("DOWN")]
# # # df=df[~df["symbol"].str.contains("UP")]
# # # df.to_csv("__binance现货交易对.csv")


# # # # pip install gate-api

# # # import pandas as pd
# # # import requests
# # # host = "https://api.gateio.ws"
# # # prefix = "/api/v4"
# # # headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

# # # # 获取所有现货标的
# # # # 状态码	含义	描述	格式
# # # # 200	OK(opens new window)	列表查询成功	[Inline]
# # # # 名称	类型	描述
# # # # None	array	
# # # # » currency	string	币种名称
# # # # » delisted	boolean	是否下架
# # # # » withdraw_disabled	boolean	是否暂停提现
# # # # » withdraw_delayed	boolean	提现是否存在延迟
# # # # » deposit_disabled	boolean	是否暂停充值
# # # # » trade_disabled	boolean	是否暂停交易
# # # # » fixed_rate	string	固定交易手续费率。仅限固定交易费率的币种，普通币种该字段无效
# # # # » chain	string	币对应的链
# # # url = '/spot/currencies'
# # # query_param = ''
# # # r = requests.request('GET', host + prefix + url, headers=headers)
# # # if r.status_code == 200: # 如果响应值为200也就是获取成功，则生成csv
# # #     df=pd.DataFrame(r.json())
# # #     df.to_csv("__gate标的.csv")
# # #     print(df)
# # # chain=df[~df['chain'].apply(lambda x: any(c.isdigit() for c in str(x)))]
# # # # chain=df[(df["chain"]=="BTC")|(df["chain"]=="ETH")]
# # # print(len(chain),"\n",chain)
# # # chain.to_csv("__gate标的【非杠杆代币】.csv")







# # # # pip install pymexc#可能要求python11以上版本
# # # from pymexc import spot, futures
# # # api_key = "mx0vglxeUz5UQL4wlI"
# # # api_secret = "81a7ca1cf2d8497fb4d95e43552cc5ad"
# # # def handle_message(message): 
# # #     # handle websocket message
# # #     print(message)
# # # # 现货SPOT V3
# # # # initialize HTTP client
# # # spot_client = spot.HTTP(api_key = api_key, api_secret = api_secret)
# # # # initialize WebSocket client
# # # ws_spot_client = spot.WebSocket(api_key = api_key, api_secret = api_secret)
# # # # 现货make http request to api
# # # exchange_info=spot_client.exchange_info()
# # # # for index in exchange_info:#解析返回值的内部结构
# # # #     # print(index,exchange_info[index])
# # # exchange_infodf=pd.DataFrame(exchange_info["symbols"])
# # # exchange_infodf.to_csv("mexc_exchange_infodf.csv")#这个是各个标的的详情
# # # # create websocket connection to public channel (spot@public.deals.v3.api@BTCUSDT)
# # # # all messages will be handled by function `handle_message`
# # # # res=ws_spot_client.deals_stream(handle_message,"BTCUSDT")#创建websocket链接
# # # # print(res)#None
# # # # order_book = spot_client.order_book("TUNAUSDT")#获取盘口数据
# # # # bids1p=order_book["bids"][0][0]
# # # # bids1v=order_book["bids"][0][1]
# # # # asks1p=order_book["asks"][0][0]
# # # # asks1v=order_book["asks"][0][1]
# # # # # print(order_book)
# # # # print(bids1p,bids1v,asks1p,asks1v)



# # # # pip install python-okx

# # # # 实时交易网址：https://www.okx.com/docs-v5/en/#overview-production-trading-services
# # # # 模拟交易网址：https://www.okx.com/docs-v5/en/#overview-demo-trading-services
# # # from okx import *
# # # from okx import Account, MarketData, PublicData
# # # import pandas as pd
# # # import time
# # # # API配置
# # # api_key = '8635667b-0702-4034-ab65-ff58275a0556'
# # # secret_key = '5A133B8EDFA08199FD4733DD4338D712'
# # # passphrase_key = 'wthWTH00.'
# # # flag_key='0'#等于0的时候是实盘，等于1的时候是模拟盘

# # # # 获取所有 USDT 现货交易对 
# # # publicDataApi = PublicData.PublicAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# # # # df=publicDataApi.get_price_limit("BTC-USD-SWAP") # 交易对限价
# # # # print(df)
# # # # df=publicDataApi.get_interest_rate_loan_quota() # 利率贷款额度
# # # # print(df)
# # # data=publicDataApi.get_instruments("SPOT") # 现货交易对
# # # df=pd.DataFrame(data["data"])
# # # df=df.rename(columns={"instId":"代码","instType":"类型"})
# # # df=df[df["quoteCcy"]=="USDT"]
# # # df.to_csv("__okx现货交易对.csv")
# # # usdt_symbols=df["代码"].tolist()
# # # print(df)

# # # # 获取所有 USDT 现货交易对 
# # # MarketDataApi=MarketData.MarketAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# # # # # df=MarketDataApi.get_oracle() # 获取账户状态
# # # # # df=MarketDataApi.get_exchange_rate() # 获取交易费率
# # # # df=MarketDataApi.get_history_candlesticks('BTC-USDT',limit=1000) # 获取历史k线
# # # # print(df)



# # # # 启动账户服务器
# # # okx_AccountAPI=Account.AccountAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# # # # print(okx_AccountAPI.get_account_balance())
# # # okx_account=pd.DataFrame(okx_AccountAPI.get_account_balance()["data"])
# # # print("账户余额",okx_account)
# # # okx_positions=pd.DataFrame(okx_AccountAPI.get_positions()["data"])
# # # print("当前持仓",okx_positions)


# # # # pip install python-bitget
# # # # 【参考文档】https://bitgetlimited.github.io/apidoc/en/mix/#get-account-list
# # # from pybitget import Client
# # # from pybitget.utils import *
# # # from pybitget.enums import *
# # # from pybitget import logger










# # import time
# # import threading
# # import pandas as pd
# # from datetime import datetime
# # import requests

# # # 交易所API配置（请替换为实际密钥）
# # EXCHANGES_CONFIG = {
# #     'binance': {
# #         'api_key': 'your_binance_api_key',
# #         'api_secret': 'your_binance_api_secret',
# #         'spot_url': 'https://api.binance.com/api/v3',
# #         'symbol': 'BTCUSDT'
# #     },
# #     'okx': {
# #         'api_key': 'your_okx_api_key',
# #         'secret_key': 'your_okx_secret_key',
# #         'passphrase': 'your_okx_passphrase',
# #         'spot_url': 'https://www.okx.com/api/v5/market',
# #         'symbol': 'BTC-USDT'
# #     },
# #     'gate': {
# #         'api_key': 'your_gate_api_key',
# #         'api_secret': 'your_gate_api_secret',
# #         'spot_url': 'https://api.gateio.ws/api/v4',
# #         'symbol': 'BTC_USDT'
# #     }
# # }

# # # 全局价格存储
# # prices = {
# #     'binance': None,
# #     'okx': None,
# #     'gate': None,
# #     'updated_at': None
# # }

# # # 持仓配置
# # TARGET_BTC_RATIO = 0.8  # 80% BTC
# # TARGET_USDT_RATIO = 0.2  # 20% USDT
# # MIN_SPREAD = 0.002  # 最小价差（0.2%）

# # # 币安API调用
# # class BinanceAPI:
# #     def __init__(self, config):
# #         self.api_key = config['api_key']
# #         self.api_secret = config['api_secret']
# #         self.base_url = config['spot_url']
# #         self.symbol = config['symbol']

# #     def get_price(self):
# #         """获取BTC/USDT最新价格"""
# #         try:
# #             url = f"{self.base_url}/ticker/price?symbol={self.symbol}"
# #             response = requests.get(url)
# #             data = response.json()
# #             return float(data['price'])
# #         except Exception as e:
# #             print(f"Binance价格获取失败: {e}")
# #             return None

# #     def get_balance(self):
# #         """获取账户余额"""
# #         try:
# #             # 实际调用需要签名，这里简化处理
# #             url = f"{self.base_url}/account"
# #             # 签名逻辑省略（需添加timestamp和signature参数）
# #             # 实际使用时参考币安API文档实现签名
# #             print("Binance余额获取（模拟）")
# #             return {
# #                 'btc': 0.005,  # 模拟BTC余额
# #                 'usdt': 1000,  # 模拟USDT余额
# #                 'total': 0.005 * prices['binance'] + 1000 if prices['binance'] else 0
# #             }
# #         except Exception as e:
# #             print(f"Binance余额获取失败: {e}")
# #             return None

# # # OKX API调用
# # class OkxAPI:
# #     def __init__(self, config):
# #         self.api_key = config['api_key']
# #         self.secret_key = config['secret_key']
# #         self.passphrase = config['passphrase']
# #         self.base_url = config['spot_url']
# #         self.symbol = config['symbol']

# #     def get_price(self):
# #         """获取BTC/USDT最新价格"""
# #         try:
# #             url = f"{self.base_url}/ticker?instId={self.symbol}"
# #             headers = {'OK-ACCESS-KEY': self.api_key}
# #             response = requests.get(url, headers=headers)
# #             data = response.json()
# #             return float(data['data'][0]['last'])
# #         except Exception as e:
# #             print(f"OKX价格获取失败: {e}")
# #             return None

# #     def get_balance(self):
# #         """获取账户余额"""
# #         try:
# #             # 实际调用需要签名，这里简化处理
# #             print("OKX余额获取（模拟）")
# #             return {
# #                 'btc': 0.004,  # 模拟BTC余额
# #                 'usdt': 800,   # 模拟USDT余额
# #                 'total': 0.004 * prices['okx'] + 800 if prices['okx'] else 0
# #             }
# #         except Exception as e:
# #             print(f"OKX余额获取失败: {e}")
# #             return None

# # # Gate.io API调用
# # class GateAPI:
# #     def __init__(self, config):
# #         self.api_key = config['api_key']
# #         self.api_secret = config['api_secret']
# #         self.base_url = config['spot_url']
# #         self.symbol = config['symbol']

# #     def get_price(self):
# #         """获取BTC/USDT最新价格"""
# #         try:
# #             url = f"{self.base_url}/spot/tickers?currency_pair={self.symbol}"
# #             response = requests.get(url)
# #             data = response.json()
# #             return float(data[0]['last'])
# #         except Exception as e:
# #             print(f"Gate价格获取失败: {e}")
# #             return None

# #     def get_balance(self):
# #         """获取账户余额"""
# #         try:
# #             # 实际调用需要签名，这里简化处理
# #             print("Gate余额获取（模拟）")
# #             return {
# #                 'btc': 0.003,  # 模拟BTC余额
# #                 'usdt': 600,   # 模拟USDT余额
# #                 'total': 0.003 * prices['gate'] + 600 if prices['gate'] else 0
# #             }
# #         except Exception as e:
# #             print(f"Gate余额获取失败: {e}")
# #             return None

# # # 初始化交易所API
# # exchanges = {
# #     'binance': BinanceAPI(EXCHANGES_CONFIG['binance']),
# #     'okx': OkxAPI(EXCHANGES_CONFIG['okx']),
# #     'gate': GateAPI(EXCHANGES_CONFIG['gate'])
# # }

# # def fetch_price(exchange_name):
# #     """获取指定交易所价格"""
# #     while True:
# #         price = exchanges[exchange_name].get_price()
# #         if price:
# #             prices[exchange_name] = price
# #             prices['updated_at'] = datetime.now()
# #             print(f"[{datetime.now()}] {exchange_name} 价格: {price}")
# #         time.sleep(1)

# # def adjust_position(exchange_name):
# #     """调整指定交易所的持仓比例"""
# #     balance = exchanges[exchange_name].get_balance()
# #     if not balance or not prices[exchange_name]:
# #         return False

# #     target_btc_value = balance['total'] * TARGET_BTC_RATIO
# #     current_btc_value = balance['btc'] * prices[exchange_name]

# #     try:
# #         if current_btc_value < target_btc_value:
# #             # 需要买入BTC
# #             buy_amount = (target_btc_value - current_btc_value) / prices[exchange_name]
# #             print(f"{exchange_name} 需要买入 {buy_amount:.6f} BTC")
# #             # 实际交易需添加下单逻辑

# #         elif current_btc_value > target_btc_value:
# #             # 需要卖出BTC
# #             sell_amount = (current_btc_value - target_btc_value) / prices[exchange_name]
# #             print(f"{exchange_name} 需要卖出 {sell_amount:.6f} BTC")
# #             # 实际交易需添加下单逻辑
# #         return True
# #     except Exception as e:
# #         print(f"{exchange_name} 调仓失败: {e}")
# #         return False

# # def check_arbitrage():
# #     """检查套利机会并执行交易"""
# #     while True:
# #         if None in prices.values():
# #             time.sleep(2)
# #             continue

# #         # 获取各交易所价格
# #         binance_price = prices['binance']
# #         okx_price = prices['okx']
# #         gate_price = prices['gate']

# #         # 找出最低和最高价格的交易所
# #         price_list = [
# #             ('binance', binance_price),
# #             ('okx', okx_price),
# #             ('gate', gate_price)
# #         ]
# #         sorted_prices = sorted(price_list, key=lambda x: x[1])
# #         lowest_exchange, lowest_price = sorted_prices[0]
# #         highest_exchange, highest_price = sorted_prices[-1]

# #         # 计算价差
# #         spread = (highest_price - lowest_price) / lowest_price
# #         if spread > MIN_SPREAD:
# #             print(f"\n发现套利机会! 价差: {spread:.2%}")
# #             print(f"{lowest_exchange} 价格最低: {lowest_price}")
# #             print(f"{highest_exchange} 价格最高: {highest_price}")
            
# #             # 调整持仓并执行套利
# #             adjust_position(lowest_exchange)  # 确保有足够资金买入
# #             adjust_position(highest_exchange) # 确保有足够BTC卖出
# #             print(f"执行套利: 在{lowest_exchange}买入，在{highest_exchange}卖出")

# #         time.sleep(5)

# # def main():
# #     # 启动多线程获取各交易所价格
# #     threads = []
# #     for exchange in ['binance', 'okx', 'gate']:
# #         t = threading.Thread(target=fetch_price, args=(exchange,), daemon=True)
# #         threads.append(t)
# #         t.start()

# #     # 启动套利检查线程
# #     arbitrage_thread = threading.Thread(target=check_arbitrage, daemon=True)
# #     arbitrage_thread.start()

# #     # 保持主程序运行
# #     try:
# #         while True:
# #             time.sleep(3600)
# #     except KeyboardInterrupt:
# #         print("程序已停止")

# # if __name__ == "__main__":
# #     main()



import requests
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional
import json
import hmac
import hashlib
# 配置参数
MONITORED_SYMBOLS = ["BTC/USDT", "ETH/USDT"]  # 监控的币种
CHECK_INTERVAL = 5  # 检查间隔(秒)
MIN_SPREAD_THRESHOLD = 0.005  # 最小价差阈值(5‰)，超过此值则报警
# 交易所API配置
EXCHANGES_CONFIG = {
    "binance": {
        "spot_url": "https://api.binance.com/api/v3/ticker/price",
        "symbol_format": "BTCUSDT",  # 示例格式
        "enabled": True
    },
    "okx": {
        "spot_url": "https://www.okx.com/api/v5/market/ticker",
        "symbol_format": "BTC-USDT",  # 示例格式
        "enabled": True
    },
    "mexc": {
        "spot_url": "https://api.mexc.com/api/v3/ticker/price",
        "symbol_format": "BTCUSDT",  # 示例格式
        "enabled": True
    },
    "bitget": {
        "spot_url": "https://api.bitget.com/api/v2/spot/market/ticker",
        "symbol_format": "BTCUSDT",  # 示例格式
        "enabled": True
    },
    "gate": {
        "spot_url": "https://api.gateio.ws/api/v4/spot/tickers",
        "symbol_format": "BTC_USDT",  # 示例格式
        "enabled": True
    }
}
# 全局价格存储
prices: Dict[str, Dict[str, float]] = {symbol: {} for symbol in MONITORED_SYMBOLS}
last_updated: Dict[str, datetime] = {}
def format_symbol(symbol: str, exchange: str) -> str:
    """根据交易所要求格式化交易对符号"""
    base, quote = symbol.split('/')
    if exchange == "binance" or exchange == "mexc":
        return f"{base}{quote}"
    elif exchange == "okx":
        return f"{base}-{quote}"
    elif exchange == "gate":
        return f"{base}_{quote}"
    elif exchange == "bitget":
        return f"{base}{quote}"
    return symbol.replace('/', '')
def get_binance_price(symbol: str) -> Optional[float]:
    """获取Binance价格"""
    try:
        formatted_symbol = format_symbol(symbol, "binance")
        url = f"{EXCHANGES_CONFIG['binance']['spot_url']}?symbol={formatted_symbol}"
        response = requests.get(url, timeout=3)
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"Binance获取{symbol}价格失败: {str(e)}")
        return None
def get_okx_price(symbol: str) -> Optional[float]:
    """获取OKX价格"""
    try:
        formatted_symbol = format_symbol(symbol, "okx")
        url = f"{EXCHANGES_CONFIG['okx']['spot_url']}?instId={formatted_symbol}"
        response = requests.get(url, timeout=3)
        data = response.json()
        if data['code'] == '0':
            return float(data['data'][0]['last'])
        return None
    except Exception as e:
        print(f"OKX获取{symbol}价格失败: {str(e)}")
        return None
def get_mexc_price(symbol: str) -> Optional[float]:
    """获取MEXC价格"""
    try:
        formatted_symbol = format_symbol(symbol, "mexc")
        url = f"{EXCHANGES_CONFIG['mexc']['spot_url']}?symbol={formatted_symbol}"
        response = requests.get(url, timeout=3)
        data = response.json()
        return float(data['price'])
    except Exception as e:
        print(f"MEXC获取{symbol}价格失败: {str(e)}")
        return None
def get_bitget_price(symbol: str) -> Optional[float]:
    """获取Bitget价格"""
    try:
        formatted_symbol = format_symbol(symbol, "bitget")
        url = f"{EXCHANGES_CONFIG['bitget']['spot_url']}?symbol={formatted_symbol}"
        response = requests.get(url, timeout=3)
        data = response.json()
        if data['code'] == 0:
            return float(data['data']['lastPr'])
        return None
    except Exception as e:
        print(f"Bitget获取{symbol}价格失败: {str(e)}")
        return None
def get_gate_price(symbol: str) -> Optional[float]:
    """获取Gate.io价格"""
    try:
        formatted_symbol = format_symbol(symbol, "gate")
        url = f"{EXCHANGES_CONFIG['gate']['spot_url']}?currency_pair={formatted_symbol}"
        response = requests.get(url, timeout=3)
        data = response.json()
        return float(data[0]['last'])
    except Exception as e:
        print(f"Gate.io获取{symbol}价格失败: {str(e)}")
        return None
# 价格获取函数映射
PRICE_FETCHERS = {
    "binance": get_binance_price,
    "okx": get_okx_price,
    "mexc": get_mexc_price,
    "bitget": get_bitget_price,
    "gate": get_gate_price
}
def fetch_price_worker(exchange: str, symbol: str):
    """价格获取工作线程"""
    while True:
        if not EXCHANGES_CONFIG[exchange]['enabled']:
            time.sleep(CHECK_INTERVAL)
            continue
        fetcher = PRICE_FETCHERS.get(exchange)
        if fetcher:
            price = fetcher(symbol)
            if price:
                with threading.Lock():
                    prices[symbol][exchange] = price
                    last_updated[symbol] = datetime.now()
        time.sleep(CHECK_INTERVAL)
def monitor_spreads(symbol: str):
    """监控价差线程"""
    while True:
        with threading.Lock():
            symbol_prices = prices[symbol].copy()
        # 确保有足够的交易所数据
        if len(symbol_prices) < 2:
            time.sleep(CHECK_INTERVAL)
            continue
        # 找出最高和最低价格【缺少交易所】
        sorted_prices = sorted(symbol_prices.items(), key=lambda x: x[1])
        lowest_exchange, lowest_price = sorted_prices[0]
        highest_exchange, highest_price = sorted_prices[-1]
        # 计算价差
        spread = (highest_price - lowest_price) / lowest_price
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 打印所有价格
        print(f"\n[{current_time}] {symbol} 价格监控:")
        for exchange, price in sorted_prices:
            print(f"  {exchange}: {price:.2f} USDT")
        # 价差超过阈值时报警
        if spread >= MIN_SPREAD_THRESHOLD:
            print(f"⚠️价差警报: {spread:.2%}")
            print(f"套利机会: 在{lowest_exchange}买入，在{highest_exchange}卖出")
            print(f"差价: {highest_price - lowest_price:.2f} USDT")
        else:
            print(f"当前价差: {spread:.2%} (低于阈值{MIN_SPREAD_THRESHOLD:.2%})")
        time.sleep(CHECK_INTERVAL)

def main():
    """主函数"""
    print(f"开始监控以下币种: {', '.join(MONITORED_SYMBOLS)}")
    print(f"监控交易所: {[k for k, v in EXCHANGES_CONFIG.items() if v['enabled']]}")
    print(f"价差阈值: {MIN_SPREAD_THRESHOLD:.2%}，检查间隔: {CHECK_INTERVAL}秒")
    print("----------------------------------------")
    # 启动价格获取线程【专门获取价格放到字典当中】
    threads = []
    for symbol in MONITORED_SYMBOLS:
        for exchange in EXCHANGES_CONFIG:
            if EXCHANGES_CONFIG[exchange]['enabled']:
                t = threading.Thread(
                    target=fetch_price_worker,
                    args=(exchange, symbol),
                    daemon=True,
                    name=f"{exchange}-{symbol}"
                )
                threads.append(t)
                t.start()
    # 启动价差监控线程
    for symbol in MONITORED_SYMBOLS:
        t = threading.Thread(
            target=monitor_spreads,
            args=(symbol,),
            daemon=True,
            name=f"monitor-{symbol}"
        )
        threads.append(t)
        t.start()
    # 保持主线程运行
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n程序已停止")

if __name__ == "__main__":
    main()
