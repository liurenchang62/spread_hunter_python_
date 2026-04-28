import requests
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional , Tuple
import pandas as pd
#价差基本都是bitget买入，资金均衡很难做


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



# # pip install gate-api
# import pandas as pd
# import requests
# host = "https://api.gateio.ws"
# prefix = "/api/v4"
# headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
# # 获取所有现货标的
# # 状态码	含义	描述	格式
# # 200	OK(opens new window)	列表查询成功	[Inline]
# # 名称	类型	描述
# # None	array	
# # » currency	string	币种名称
# # » delisted	boolean	是否下架
# # » withdraw_disabled	boolean	是否暂停提现
# # » withdraw_delayed	boolean	提现是否存在延迟
# # » deposit_disabled	boolean	是否暂停充值
# # » trade_disabled	boolean	是否暂停交易
# # » fixed_rate	string	固定交易手续费率。仅限固定交易费率的币种，普通币种该字段无效
# # » chain	string	币对应的链
# url = '/spot/currencies'
# query_param = ''
# r = requests.request('GET', host + prefix + url, headers=headers)
# if r.status_code == 200: # 如果响应值为200也就是获取成功，则生成csv
#     df=pd.DataFrame(r.json())
#     df.to_csv("__gate标的.csv")
#     print(df)
# chain=df[~df['chain'].apply(lambda x: any(c.isdigit() for c in str(x)))]
# # chain=df[(df["chain"]=="BTC")|(df["chain"]=="ETH")]
# print(len(chain),"\n",chain)
# chain.to_csv("__gate标的【非杠杆代币】.csv")



# # pip install python-okx
# # 实时交易网址：https://www.okx.com/docs-v5/en/#overview-production-trading-services
# # 模拟交易网址：https://www.okx.com/docs-v5/en/#overview-demo-trading-services
# from okx import *
# from okx import Account, MarketData, PublicData
# import pandas as pd
# import time
# # API配置
# api_key = '8635667b-0702-4034-ab65-ff58275a0556'
# secret_key = '5A133B8EDFA08199FD4733DD4338D712'
# passphrase_key = 'wthWTH00.'
# flag_key='0'#等于0的时候是实盘，等于1的时候是模拟盘
# # 获取所有 USDT 现货交易对 
# publicDataApi = PublicData.PublicAPI(api_key=api_key, api_secret_key=secret_key, passphrase=passphrase_key, use_server_time=False, flag=flag_key)
# # # df=publicDataApi.get_price_limit("BTC-USD-SWAP") # 交易对限价
# # # print(df)
# # # df=publicDataApi.get_interest_rate_loan_quota() # 利率贷款额度
# # # print(df)
# # data=publicDataApi.get_instruments("SPOT") # 现货交易对
# # df=pd.DataFrame(data["data"])
# # df=df.rename(columns={"instId":"代码","instType":"类型"})
# # df=df[df["quoteCcy"]=="USDT"]
# # df.to_csv("__okx现货交易对.csv")
# # usdt_symbols=df["代码"].tolist()
# # print(df)



# # pip install pymexc#可能要求python11以上版本
# from pymexc import spot, futures
# api_key = "mx0vglxeUz5UQL4wlI"
# api_secret = "81a7ca1cf2d8497fb4d95e43552cc5ad"
# def handle_message(message): 
#     # handle websocket message
#     print(message)
# # 现货SPOT V3
# # initialize HTTP client
# spot_client = spot.HTTP(api_key = api_key, api_secret = api_secret)
# # initialize WebSocket client
# ws_spot_client = spot.WebSocket(api_key = api_key, api_secret = api_secret)
# # 现货make http request to api
# exchange_info=spot_client.exchange_info()
# # for index in exchange_info:#解析返回值的内部结构
# #     # print(index,exchange_info[index])
# exchange_infodf=pd.DataFrame(exchange_info["symbols"])
# exchange_infodf.to_csv("mexc_exchange_infodf.csv")#这个是各个标的的详情
# # create websocket connection to public channel (spot@public.deals.v3.api@BTCUSDT)
# # all messages will be handled by function `handle_message`
# # res=ws_spot_client.deals_stream(handle_message,"BTCUSDT")#创建websocket链接
# # print(res)#None
# # order_book = spot_client.order_book("TUNAUSDT")#获取盘口数据
# # bids1p=order_book["bids"][0][0]
# # bids1v=order_book["bids"][0][1]
# # asks1p=order_book["asks"][0][0]
# # asks1v=order_book["asks"][0][1]
# # # print(order_book)
# # print(bids1p,bids1v,asks1p,asks1v)



# # pip install python-binance#安装币安的python库
# from binance.client import Client  as binanceClient
# ### 在线读取 ###
# # 币安的api配置
# api_key = "0jmNVvNZusoXKGkwnGLBghPh8Kmc0klh096VxNS9kn8P0nkAEslVUlsuOcRoGrtm"
# api_secret = "PbSWkno1meUckhmkLyz8jQ2RRG7KgmZyAWhIF0qPdCJrmDSFxoxGdMG5gZeYYCgy"
# # 创建Binance客户端
# binance_Client = binanceClient(api_key, api_secret)
# # # 获取所有USDT计价的现货交易对及其详情
# # df=pd.json_normalize(binance_Client.get_exchange_info(),record_path='symbols')
# # df=df[df["quoteAsset"]=="USDT"]
# # df=df[~df["symbol"].str.contains("DOWN")]
# # df=df[~df["symbol"].str.contains("UP")]
# # df.to_csv("__binance现货交易对.csv")



# # pip install python-bitget
# # 【参考文档】https://bitgetlimited.github.io/apidoc/en/mix/#get-account-list
# from pybitget import Client as bitgetClient
# # 配置您的Bitget API密钥和密码短语
# api_key="bg_5e69f9e32e87c9bb8087f97cc6adb910"
# api_secret='b0682a6e4a0e0c50493a4be19b4f56de4fa81f07d6e7d010a71e1971a7c3bbb4'#默认HMAC方式解码
# api_passphrase="wthWTH00"
# bitget_Client=bitgetClient(api_key,api_secret,passphrase=api_passphrase)



# 配置参数
MONITORED_SYMBOLS = ["BTC/USDT", "ETH/USDT"]  # 监控的币种[反而是大标的更有利润]
# MONITORED_SYMBOLS = ["TRX/USDT", "TON/USDT", "TRUMP/USDT"]  # 监控的币种
CHECK_INTERVAL = 5  # 检查间隔(秒)
MIN_SPREAD_THRESHOLD = 0.005  # 最小价差阈值(5‰)

# 交易所API配置
EXCHANGES_CONFIG = {
    "binance": {
        "depth_url": "https://api.binance.com/api/v3/depth",
        "enabled": True
    },
    "okx": {
        "depth_url": "https://www.okx.com/api/v5/market/books",
        "enabled": True
    },
    "mexc": {
        "depth_url": "https://api.mexc.com/api/v3/depth",
        "enabled": True
    },
    "bitget": {
        "depth_url": "https://api.bitget.com/api/mix/v1/market/depth",
        "enabled": True
    },
    "gate": {
        "depth_url": "https://api.gateio.ws/api/v4/spot/order_book",
        "enabled": True
    }
}

# 全局深度数据存储，格式: {symbol: {exchange: {'bid': (price, amount), 'ask': (price, amount)}}}
orderbook_data: Dict[str, Dict[str, Dict[str, Tuple[float, float]]]] = {
    symbol: {} for symbol in MONITORED_SYMBOLS
}

def format_symbol(symbol: str, exchange: str) -> str:
    """根据各交易所要求格式化交易对"""
    base, quote = symbol.split('/')
    
    if exchange == "binance" or exchange == "mexc":
        return f"{base}{quote}"  # 如BTCUSDT
    elif exchange == "okx":
        return f"{base}-{quote}"  # 如BTC-USDT
    elif exchange == "gate":
        return f"{base}_{quote}"  # 如BTC_USDT
    elif exchange == "bitget":
        return f"{base}{quote}_UMCBL"  # 如BTCUSDT
    return symbol.replace('/', '')

def get_binance_depth(symbol: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """获取Binance深度数据（买一卖一及数量）"""
    try:
        formatted_symbol = format_symbol(symbol, "binance")
        url = f"{EXCHANGES_CONFIG['binance']['depth_url']}?symbol={formatted_symbol}&limit=1"
        response = requests.get(url, timeout=3)
        data = response.json()
        # 买一价和数量 (bid)，卖一价和数量 (ask)
        return {
            'bid': (float(data['bids'][0][0]), float(data['bids'][0][1])),
            'ask': (float(data['asks'][0][0]), float(data['asks'][0][1]))
        }
    except Exception as e:
        logger.info(f"Binance获取{symbol}深度失败: {str(e)}")
        return None

def get_okx_depth(symbol: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """获取OKX深度数据（买一卖一及数量）"""
    try:
        formatted_symbol = format_symbol(symbol, "okx")
        url = f"{EXCHANGES_CONFIG['okx']['depth_url']}?instId={formatted_symbol}&depth=1"
        response = requests.get(url, timeout=3)
        data = response.json()
        if data['code'] == '0':
            books = data['data'][0]
            return {
                'bid': (float(books['bids'][0][0]), float(books['bids'][0][1])),
                'ask': (float(books['asks'][0][0]), float(books['asks'][0][1]))
            }
        return None
    except Exception as e:
        logger.info(f"OKX获取{symbol}深度失败: {str(e)}")
        return None

def get_mexc_depth(symbol: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """获取MEXC深度数据（买一卖一及数量）"""
    try:
        formatted_symbol = format_symbol(symbol, "mexc")
        url = f"{EXCHANGES_CONFIG['mexc']['depth_url']}?symbol={formatted_symbol}&limit=1"
        response = requests.get(url, timeout=3)
        data = response.json()
        return {
            'bid': (float(data['bids'][0][0]), float(data['bids'][0][1])),
            'ask': (float(data['asks'][0][0]), float(data['asks'][0][1]))
        }
    except Exception as e:
        logger.info(f"MEXC获取{symbol}深度失败: {str(e)}")
        return None

def get_bitget_depth(symbol: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """获取Bitget深度数据（买一卖一及数量）"""
    try:
        formatted_symbol = format_symbol(symbol, "bitget")
        url = f"{EXCHANGES_CONFIG['bitget']['depth_url']}?symbol={formatted_symbol}&limit=1"
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        depth_data = data.get('data',{})
        # logger.info(f'''depth_data
        #     'bid': {(float(depth_data['bids'][0][0]), float(depth_data['bids'][0][1]))},
        #     'ask': {(float(depth_data['asks'][0][0]), float(depth_data['asks'][0][1]))}'''
        #     )
        return {
            'bid': (float(depth_data['bids'][0][0]), float(depth_data['bids'][0][1])),
            'ask': (float(depth_data['asks'][0][0]), float(depth_data['asks'][0][1]))
        }
    except Exception as e:
        logger.info(f"Bitget获取{symbol}深度失败: {str(e)}")
        return None

def get_gate_depth(symbol: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """获取Gate.io深度数据（买一卖一及数量）"""
    try:
        formatted_symbol = format_symbol(symbol, "gate")
        url = f"{EXCHANGES_CONFIG['gate']['depth_url']}?currency_pair={formatted_symbol}&limit=1"
        response = requests.get(url, timeout=3)
        data = response.json()
        return {
            'bid': (float(data['bids'][0][0]), float(data['bids'][0][1])),
            'ask': (float(data['asks'][0][0]), float(data['asks'][0][1]))
        }
    except Exception as e:
        logger.info(f"Gate.io获取{symbol}深度失败: {str(e)}")
        return None

# 深度数据获取函数映射
DEPTH_FETCHERS = {
    "binance": get_binance_depth,
    "okx": get_okx_depth,
    "mexc": get_mexc_depth,
    "bitget": get_bitget_depth,
    "gate": get_gate_depth
}

def fetch_depth_worker(exchange: str, symbol: str):
    """深度数据获取工作线程"""
    while True:
        if not EXCHANGES_CONFIG[exchange]['enabled']:
            time.sleep(CHECK_INTERVAL)
            continue
        fetcher = DEPTH_FETCHERS.get(exchange)
        if fetcher:
            depth_data = fetcher(symbol)
            if depth_data:
                with threading.Lock():
                    orderbook_data[symbol][exchange] = depth_data
        time.sleep(CHECK_INTERVAL)

def monitor_spreads(symbol: str):
    """监控价差线程，基于买一卖一数据"""
    while True:
        with threading.Lock():
            symbol_depth = orderbook_data[symbol].copy()
        # 确保有足够的交易所数据
        if len(symbol_depth) < 2:
            time.sleep(CHECK_INTERVAL)
            continue
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"\n[{current_time}] {symbol} 深度监控:")
        # 收集所有交易所的买一卖一数据
        exchange_rates = []
        for exchange, data in symbol_depth.items():
            bid_price, bid_amount = data['bid']
            ask_price, ask_amount = data['ask']
            exchange_rates.append((exchange, bid_price, bid_amount, ask_price, ask_amount))
            logger.info(f"  {exchange}:")
            logger.info(f"    买一: {bid_price:.2f} USDT, 数量: {bid_amount:.4f} {symbol.split('/')[0]}")
            logger.info(f"    卖一: {ask_price:.2f} USDT, 数量: {ask_amount:.4f} {symbol.split('/')[0]}")
        # 找出最低卖价和最高买价，计算套利空间
        lowest_ask = min(exchange_rates, key=lambda x: x[3])  # (交易所, 买价, 买量, 卖价, 卖量)
        highest_bid = max(exchange_rates, key=lambda x: x[1])
        # 计算潜在套利利润空间
        spread = (highest_bid[1] - lowest_ask[3]) / lowest_ask[3] if lowest_ask[3] > 0 else 0
        if spread > 0:  # 存在套利空间
            logger.info(f"\n📈 套利机会:")
            logger.info(f"   在{lowest_ask[0]}以卖一价{lowest_ask[3]:.2f}买入")
            logger.info(f"   在{highest_bid[0]}以买一价{highest_bid[1]:.2f}卖出")
            logger.info(f"   单位利润: {highest_bid[1] - lowest_ask[3]:.2f} USDT")
            logger.info(f"   利润率: {spread:.2%}")
            logger.info(f"   最大可套利数量: {min(lowest_ask[4], highest_bid[2]):.4f} {symbol.split('/')[0]}")
        elif spread >= -MIN_SPREAD_THRESHOLD:
            logger.info(f"\n   无显著套利机会，价差: {spread:.2%}")
        else:
            logger.info(f"\n   正常市场，价差: {spread:.2%}")
        time.sleep(CHECK_INTERVAL)

def main():
    """主函数"""
    logger.info(f"开始监控以下币种深度数据: {', '.join(MONITORED_SYMBOLS)}")
    logger.info(f"监控交易所: {[k for k, v in EXCHANGES_CONFIG.items() if v['enabled']]}")
    logger.info(f"价差阈值: {MIN_SPREAD_THRESHOLD:.2%}，检查间隔: {CHECK_INTERVAL}秒")
    logger.info("----------------------------------------")
    # 启动深度数据获取线程
    for symbol in MONITORED_SYMBOLS:
        for exchange in EXCHANGES_CONFIG:
            if EXCHANGES_CONFIG[exchange]['enabled']:
                t = threading.Thread(
                    target=fetch_depth_worker,
                    args=(exchange, symbol),
                    daemon=True,
                    name=f"{exchange}-{symbol}-depth"
                )
                t.start()
                time.sleep(0.1)  # 错开请求时间
    # 启动价差监控线程
    for symbol in MONITORED_SYMBOLS:
        t = threading.Thread(
            target=monitor_spreads,
            args=(symbol,),
            daemon=True,
            name=f"monitor-{symbol}"
        )
        t.start()
    # 保持主线程运行
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("\n程序已停止")
if __name__ == "__main__":
    main()

