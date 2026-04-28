# 跨交易所现货套利策略
# 监控5家交易所(Binance, Bitget, Gate, OKX, Getcoin/MEXC)的BTC价格差异，实现低买高卖的现货套利

import pandas as pd
import time
import datetime
import requests
from binance.client import Client
from pybitget import Client as BitgetClient
import okx.MarketData as MarketData
import okx.Account as Account
import okx.Trade as Trade
from pymexc import spot as MexcSpot
import logging
import numpy as np
import hmac
import hashlib
import json
import os
from pathlib import Path

# 配置文件支持 - 从配置文件加载API密钥和策略参数
def load_config(config_file='arbitrage_config.json'):
    """从配置文件加载参数，如果文件不存在则创建默认配置"""
    config_path = Path(config_file)
    
    # 默认配置
    default_config = {
        "api_keys": {
            "binance": {
                "api_key": "",
                "api_secret": ""
            },
            "bitget": {
                "api_key": "",
                "api_secret": "",
                "passphrase": ""
            },
            "gate": {
                "api_key": "",
                "api_secret": ""
            },
            "okx": {
                "api_key": "",
                "api_secret": "",
                "passphrase": ""
            },
            "mexc": {
                "api_key": "",
                "api_secret": ""
            }
        },
        "trading_params": {
            "arbitrage_threshold": 0.005,
            "min_trade_amount": 0.001,
            "max_trade_amount": 0.1,
            "check_interval": 30,
            "trade_symbol": "BTCUSDT",
            "max_slippage": 0.002,
            "max_position_ratio": 0.1,
            "fee_rate": 0.001,
            "enable_actual_trade": False,
            "max_retry_count": 3,
            "retry_interval": 5
        }
    }
    
    if not config_path.exists():
        logging.info(f"配置文件{config_file}不存在，创建默认配置")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        return default_config
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        return default_config

# 配置日志
logging.basicConfig(
    filename='arbitrage.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# 加载配置
config_data = load_config()

# 配置文件，实际使用时需要替换为自己的API密钥
class Config:
    # Binance配置
    BINANCE_API_KEY = config_data['api_keys']['binance']['api_key']
    BINANCE_API_SECRET = config_data['api_keys']['binance']['api_secret']
    
    # Bitget配置
    BITGET_API_KEY = config_data['api_keys']['bitget']['api_key']
    BITGET_API_SECRET = config_data['api_keys']['bitget']['api_secret']
    BITGET_PASSPHRASE = config_data['api_keys']['bitget']['passphrase']
    
    # Gate配置
    GATE_API_KEY = config_data['api_keys']['gate']['api_key']
    GATE_API_SECRET = config_data['api_keys']['gate']['api_secret']
    GATE_HOST_PREFIX = "https://api.gateio.ws/api/v4"
    GATE_HEADERS = {'Accept': 'application/json', 'Content-Type': 'application/json'}
    
    # OKX配置
    OKX_API_KEY = config_data['api_keys']['okx']['api_key']
    OKX_API_SECRET = config_data['api_keys']['okx']['api_secret']
    OKX_PASSPHRASE = config_data['api_keys']['okx']['passphrase']
    OKX_FLAG = "0"  # 0-实盘，1-模拟盘
    
    # MEXC配置
    MEXC_API_KEY = config_data['api_keys']['mexc']['api_key']
    MEXC_API_SECRET = config_data['api_keys']['mexc']['api_secret']
    
    # 套利配置
    ARBITRAGE_THRESHOLD = config_data['trading_params']['arbitrage_threshold']  # 套利阈值，大于0.5%的价差才进行套利
    MIN_TRADE_AMOUNT = config_data['trading_params']['min_trade_amount']  # 最小交易BTC数量
    MAX_TRADE_AMOUNT = config_data['trading_params']['max_trade_amount']  # 最大交易BTC数量
    CHECK_INTERVAL = config_data['trading_params']['check_interval']  # 价格检查间隔（秒）
    TRADE_SYMBOL = config_data['trading_params']['trade_symbol']  # 交易对
    MAX_SLIPPAGE = config_data['trading_params']['max_slippage']  # 最大滑点，2%
    MAX_POSITION_RATIO = config_data['trading_params']['max_position_ratio']  # 单个交易所最大持仓比例
    FEE_RATE = config_data['trading_params']['fee_rate']  # 手续费率预估
    ENABLE_ACTUAL_TRADE = config_data['trading_params']['enable_actual_trade']  # 是否启用实际交易，默认为False（模拟交易）
    MAX_RETRY_COUNT = config_data['trading_params']['max_retry_count']  # 最大重试次数
    RETRY_INTERVAL = config_data['trading_params']['retry_interval']  # 重试间隔

# Gate交易所API签名工具
class GateAPISignature:
    @staticmethod
    def sign_request(method, path, query_string, body):
        """为Gate交易所API请求生成签名"""
        if Config.GATE_API_KEY and Config.GATE_API_SECRET:
            t = str(int(time.time()))
            m = hashlib.sha512()
            m.update((body if body else "").encode('utf-8'))
            hashed_body = m.hexdigest()
            s = f'{t}{method}{path}{query_string}{hashed_body}'
            sign = hmac.new(Config.GATE_API_SECRET.encode('utf-8'), s.encode('utf-8'), hashlib.sha512).hexdigest()
            return t, sign
        return None, None

# 初始化各交易所客户端
class ExchangeClients:
    def __init__(self):
        # 初始化Binance客户端
        self.binance_client = Client(api_key=Config.BINANCE_API_KEY, api_secret=Config.BINANCE_API_SECRET)
        
        # 初始化Bitget客户端
        self.bitget_client = BitgetClient(api_key=Config.BITGET_API_KEY, api_secret=Config.BITGET_API_SECRET, passphrase=Config.BITGET_PASSPHRASE)
        
        # 初始化OKX客户端
        self.okx_market_api = MarketData.MarketAPI(api_key=Config.OKX_API_KEY, api_secret_key=Config.OKX_API_SECRET,
                                                  passphrase=Config.OKX_PASSPHRASE, use_server_time=False, flag=Config.OKX_FLAG)
        self.okx_account_api = Account.AccountAPI(api_key=Config.OKX_API_KEY, api_secret_key=Config.OKX_API_SECRET,
                                                 passphrase=Config.OKX_PASSPHRASE, use_server_time=False, flag=Config.OKX_FLAG)
        self.okx_trade_api = Trade.TradeAPI(api_key=Config.OKX_API_KEY, api_secret_key=Config.OKX_API_SECRET,
                                           passphrase=Config.OKX_PASSPHRASE, use_server_time=False, flag=Config.OKX_FLAG)
        
        # 初始化MEXC客户端
        self.mexc_client = MexcSpot.HTTP(api_key=Config.MEXC_API_KEY, api_secret=Config.MEXC_API_SECRET)

# 重试装饰器
def retry_on_exception(max_retries=Config.MAX_RETRY_COUNT, retry_interval=Config.RETRY_INTERVAL):
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries >= max_retries:
                        logging.error(f"函数 {func.__name__} 重试 {max_retries} 次后失败: {e}")
                        raise
                    logging.warning(f"函数 {func.__name__} 调用失败，{retry_interval}秒后重试 ({retries}/{max_retries}): {e}")
                    time.sleep(retry_interval)
        return wrapper
    return decorator

# 获取各交易所BTC价格
class PriceFetcher:
    def __init__(self, clients):
        self.clients = clients
        
    @retry_on_exception()
    def get_binance_price(self):
        """获取Binance交易所的BTC价格"""
        try:
            ticker = self.clients.binance_client.get_symbol_ticker(symbol=Config.TRADE_SYMBOL)
            return float(ticker['price'])
        except Exception as e:
            logging.error(f"获取Binance价格失败: {e}")
            raise
    
    @retry_on_exception()
    def get_bitget_price(self):
        """获取Bitget交易所的BTC价格"""
        try:
            request_path = "/api/v2/spot/market/ticker"
            params = {"symbol": Config.TRADE_SYMBOL}
            ticker = self.clients.bitget_client._request_with_params(params=params, request_path=request_path, method="GET")
            return float(ticker["data"][0]["last"])
        except Exception as e:
            logging.error(f"获取Bitget价格失败: {e}")
            raise
    
    @retry_on_exception()
    def get_gate_price(self):
        """获取Gate交易所的BTC价格"""
        try:
            response = requests.request('GET', f"{Config.GATE_HOST_PREFIX}/spot/tickers", headers=Config.GATE_HEADERS)
            data = response.json()
            for item in data:
                if item['currency_pair'] == 'BTC_USDT':
                    return float(item['last'])
            return None
        except Exception as e:
            logging.error(f"获取Gate价格失败: {e}")
            raise
    
    @retry_on_exception()
    def get_okx_price(self):
        """获取OKX交易所的BTC价格"""
        try:
            result = self.clients.okx_market_api.get_ticker(instId="BTC-USDT")
            if result['code'] == "0" and result['data']:
                return float(result['data'][0]['last'])
            return None
        except Exception as e:
            logging.error(f"获取OKX价格失败: {e}")
            raise
    
    @retry_on_exception()
    def get_mexc_price(self):
        """获取MEXC交易所的BTC价格"""
        try:
            ticker = self.clients.mexc_client.ticker(symbol=Config.TRADE_SYMBOL)
            return float(ticker["lastPrice"])
        except Exception as e:
            logging.error(f"获取MEXC价格失败: {e}")
            raise
    
    def get_all_prices(self):
        """获取所有交易所的BTC价格"""
        prices = {}
        methods = [
            ('Binance', self.get_binance_price),
            ('Bitget', self.get_bitget_price),
            ('Gate', self.get_gate_price),
            ('OKX', self.get_okx_price),
            ('MEXC', self.get_mexc_price)
        ]
        
        # 并行获取价格以减少延迟
        for name, method in methods:
            try:
                prices[name] = method()
            except Exception as e:
                logging.error(f"获取{name}价格失败: {e}")
                prices[name] = None
        
        # 过滤掉获取失败的价格
        valid_prices = {k: v for k, v in prices.items() if v is not None}
        logging.info(f"获取到{len(valid_prices)}/{len(prices)}家交易所的有效价格")
        
        # 计算价格标准差，用于异常检测
        if len(valid_prices) >= 3:
            prices_values = list(valid_prices.values())
            mean_price = np.mean(prices_values)
            std_price = np.std(prices_values)
            outlier_threshold = 2.0  # 标准差倍数
            
            # 检测并排除异常价格
            outliers = {k: v for k, v in valid_prices.items() if abs(v - mean_price) > outlier_threshold * std_price}
            if outliers:
                logging.warning(f"检测到异常价格: {outliers}")
                valid_prices = {k: v for k, v in valid_prices.items() if k not in outliers}
                logging.info(f"排除异常后剩余{len(valid_prices)}家交易所的有效价格")
        
        return valid_prices

# 套利交易执行器
class ArbitrageTrader:
    def __init__(self, clients):
        self.clients = clients
        self.trade_history = []
        self.balances = {}
        self.update_balances()
        self.running_pnl = 0  # 运行中的盈亏
        self.performance_metrics = {
            "total_trades": 0,
            "successful_trades": 0,
            "failed_trades": 0,
            "total_profit": 0,
            "win_rate": 0,
            "avg_profit_per_trade": 0,
            "max_profit": 0,
            "max_loss": 0
        }
        
        # 创建交易历史文件（如果不存在）
        self.trade_history_file = "arbitrage_trade_history.json"
        self.load_trade_history()
        
    def load_trade_history(self):
        """从文件加载交易历史"""
        if os.path.exists(self.trade_history_file):
            try:
                with open(self.trade_history_file, 'r', encoding='utf-8') as f:
                    self.trade_history = json.load(f)
                logging.info(f"成功加载{len(self.trade_history)}条交易历史记录")
                self.update_performance_metrics()
            except Exception as e:
                logging.error(f"加载交易历史失败: {e}")
    
    def save_trade_history(self):
        """将交易历史保存到文件"""
        try:
            with open(self.trade_history_file, 'w', encoding='utf-8') as f:
                json.dump(self.trade_history, f, indent=4, ensure_ascii=False)
            logging.info(f"成功保存{len(self.trade_history)}条交易历史记录")
        except Exception as e:
            logging.error(f"保存交易历史失败: {e}")
    
    def update_performance_metrics(self):
        """更新业绩指标"""
        if not self.trade_history:
            return
        
        self.performance_metrics["total_trades"] = len(self.trade_history)
        successful_trades = [t for t in self.trade_history if t['profit'] > 0]
        self.performance_metrics["successful_trades"] = len(successful_trades)
        self.performance_metrics["failed_trades"] = self.performance_metrics["total_trades"] - len(successful_trades)
        self.performance_metrics["total_profit"] = sum(t['profit'] for t in self.trade_history)
        self.performance_metrics["win_rate"] = len(successful_trades) / self.performance_metrics["total_trades"] if self.performance_metrics["total_trades"] > 0 else 0
        self.performance_metrics["avg_profit_per_trade"] = self.performance_metrics["total_profit"] / self.performance_metrics["total_trades"] if self.performance_metrics["total_trades"] > 0 else 0
        
        if self.trade_history:
            self.performance_metrics["max_profit"] = max(t['profit'] for t in self.trade_history)
            self.performance_metrics["max_loss"] = min(t['profit'] for t in self.trade_history)
    
    def update_balances(self):
        """更新所有交易所的账户余额"""
        self.balances = self.get_account_balances()
        
    @retry_on_exception()
    def get_account_balances(self):
        """获取各交易所的账户余额"""
        balances = {}
        
        # 获取Binance余额
        try:
            binance_balances = self.clients.binance_client.get_account()
            usdt_balance = next((float(balance['free']) for balance in binance_balances['balances'] if balance['asset'] == 'USDT'), 0)
            btc_balance = next((float(balance['free']) for balance in binance_balances['balances'] if balance['asset'] == 'BTC'), 0)
            balances['Binance'] = {'USDT': usdt_balance, 'BTC': btc_balance}
        except Exception as e:
            logging.error(f"获取Binance余额失败: {e}")
            raise
        
        # 获取Bitget余额
        try:
            request_path = "/api/v2/spot/account/assets"
            params = {"coin": "USDT"}
            usdt_data = self.clients.bitget_client._request_with_params(params=params, request_path=request_path, method="GET")
            usdt_balance = float(usdt_data["data"][0]["available"])
            
            params = {"coin": "BTC"}
            btc_data = self.clients.bitget_client._request_with_params(params=params, request_path=request_path, method="GET")
            btc_balance = float(btc_data["data"][0]["available"])
            balances['Bitget'] = {'USDT': usdt_balance, 'BTC': btc_balance}
        except Exception as e:
            logging.error(f"获取Bitget余额失败: {e}")
            raise
        
        # 获取OKX余额
        try:
            result = self.clients.okx_account_api.get_account_balance()
            if result['code'] == "0" and result['data']:
                usdt_balance = 0
                btc_balance = 0
                for item in result['data'][0]['details']:
                    if item['ccy'] == 'USDT':
                        usdt_balance = float(item['availBal'])
                    elif item['ccy'] == 'BTC':
                        btc_balance = float(item['availBal'])
                balances['OKX'] = {'USDT': usdt_balance, 'BTC': btc_balance}
            else:
                logging.warning(f"OKX余额获取失败，返回代码: {result['code']}")
                balances['OKX'] = {'USDT': 0, 'BTC': 0}
        except Exception as e:
            logging.error(f"获取OKX余额失败: {e}")
            raise
        
        # 获取MEXC余额
        try:
            account_info = self.clients.mexc_client.account()
            usdt_balance = 0
            btc_balance = 0
            for balance in account_info['balances']:
                if balance['asset'] == 'USDT':
                    usdt_balance = float(balance['free'])
                elif balance['asset'] == 'BTC':
                    btc_balance = float(balance['free'])
            balances['MEXC'] = {'USDT': usdt_balance, 'BTC': btc_balance}
        except Exception as e:
            logging.error(f"获取MEXC余额失败: {e}")
            raise
        
        # 获取Gate余额（完整实现）
        try:
            path = "/spot/accounts"
            method = "GET"
            t, sign = GateAPISignature.sign_request(method, path, "", "")
            headers = Config.GATE_HEADERS.copy()
            if t and sign:
                headers['KEY'] = Config.GATE_API_KEY
                headers['Timestamp'] = t
                headers['SIGN'] = sign
            
            response = requests.request(method, f"{Config.GATE_HOST_PREFIX}{path}", headers=headers)
            data = response.json()
            
            usdt_balance = 0
            btc_balance = 0
            for item in data:
                if item['currency'] == 'USDT':
                    usdt_balance = float(item['available'])
                elif item['currency'] == 'BTC':
                    btc_balance = float(item['available'])
            balances['Gate'] = {'USDT': usdt_balance, 'BTC': btc_balance}
        except Exception as e:
            logging.error(f"获取Gate余额失败: {e}")
            # 不抛出异常，而是返回占位符
            balances['Gate'] = {'USDT': 0, 'BTC': 0}
        
        return balances
    
    def format_number(self, num, precision=6):
        """格式化数字，去除多余的小数位"""
        return float(f"%.{precision}f" % num)
    
    @retry_on_exception()
    def buy_on_exchange(self, exchange, amount, price):
        """在指定交易所买入BTC"""
        if not Config.ENABLE_ACTUAL_TRADE:
            logging.info(f"[模拟] 在{exchange}买入{amount} BTC，价格: {price} USDT")
            return True
        
        try:
            if exchange == 'Binance':
                order = self.clients.binance_client.order_market_buy(symbol=Config.TRADE_SYMBOL, quantity=amount)
                logging.info(f"Binance买入订单: {order}")
                return True
            elif exchange == 'Bitget':
                request_path = "/api/v2/spot/trade/place-order"
                params = {
                    "symbol": Config.TRADE_SYMBOL,
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": str(amount)
                }
                order = self.clients.bitget_client._request_with_params(params=params, request_path=request_path, method="POST")
                logging.info(f"Bitget买入订单: {order}")
                return order['code'] == '0'
            elif exchange == 'OKX':
                order = self.clients.okx_trade_api.place_order(
                    instId="BTC-USDT",
                    tdMode="cash",
                    side="buy",
                    ordType="market",
                    sz=str(amount)
                )
                logging.info(f"OKX买入订单: {order}")
                return order['code'] == "0"
            elif exchange == 'MEXC':
                order = self.clients.mexc_client.new_order(
                    symbol=Config.TRADE_SYMBOL,
                    side="BUY",
                    type="MARKET",
                    quantity=amount
                )
                logging.info(f"MEXC买入订单: {order}")
                return order['status'] == 'NEW'
            elif exchange == 'Gate':
                path = "/spot/orders"
                method = "POST"
                body = json.dumps({
                    "currency_pair": "BTC_USDT",
                    "type": "market",
                    "side": "buy",
                    "amount": str(amount * price)  # Gate的市价单使用金额
                })
                t, sign = GateAPISignature.sign_request(method, path, "", body)
                headers = Config.GATE_HEADERS.copy()
                if t and sign:
                    headers['KEY'] = Config.GATE_API_KEY
                    headers['Timestamp'] = t
                    headers['SIGN'] = sign
                
                response = requests.request(method, f"{Config.GATE_HOST_PREFIX}{path}", headers=headers, data=body)
                data = response.json()
                logging.info(f"Gate买入订单: {data}")
                return 'id' in data
            else:
                logging.error(f"不支持的交易所: {exchange}")
                return False
        except Exception as e:
            logging.error(f"在{exchange}买入失败: {e}")
            raise
    
    @retry_on_exception()
    def sell_on_exchange(self, exchange, amount, price):
        """在指定交易所卖出BTC"""
        if not Config.ENABLE_ACTUAL_TRADE:
            logging.info(f"[模拟] 在{exchange}卖出{amount} BTC，价格: {price} USDT")
            return True
        
        try:
            if exchange == 'Binance':
                order = self.clients.binance_client.order_market_sell(symbol=Config.TRADE_SYMBOL, quantity=amount)
                logging.info(f"Binance卖出订单: {order}")
                return True
            elif exchange == 'Bitget':
                request_path = "/api/v2/spot/trade/place-order"
                params = {
                    "symbol": Config.TRADE_SYMBOL,
                    "side": "SELL",
                    "type": "MARKET",
                    "quantity": str(amount)
                }
                order = self.clients.bitget_client._request_with_params(params=params, request_path=request_path, method="POST")
                logging.info(f"Bitget卖出订单: {order}")
                return order['code'] == '0'
            elif exchange == 'OKX':
                order = self.clients.okx_trade_api.place_order(
                    instId="BTC-USDT",
                    tdMode="cash",
                    side="sell",
                    ordType="market",
                    sz=str(amount)
                )
                logging.info(f"OKX卖出订单: {order}")
                return order['code'] == "0"
            elif exchange == 'MEXC':
                order = self.clients.mexc_client.new_order(
                    symbol=Config.TRADE_SYMBOL,
                    side="SELL",
                    type="MARKET",
                    quantity=amount
                )
                logging.info(f"MEXC卖出订单: {order}")
                return order['status'] == 'NEW'
            elif exchange == 'Gate':
                path = "/spot/orders"
                method = "POST"
                body = json.dumps({
                    "currency_pair": "BTC_USDT",
                    "type": "market",
                    "side": "sell",
                    "amount": str(amount)  # Gate的市价卖单使用数量
                })
                t, sign = GateAPISignature.sign_request(method, path, "", body)
                headers = Config.GATE_HEADERS.copy()
                if t and sign:
                    headers['KEY'] = Config.GATE_API_KEY
                    headers['Timestamp'] = t
                    headers['SIGN'] = sign
                
                response = requests.request(method, f"{Config.GATE_HOST_PREFIX}{path}", headers=headers, data=body)
                data = response.json()
                logging.info(f"Gate卖出订单: {data}")
                return 'id' in data
            else:
                logging.error(f"不支持的交易所: {exchange}")
                return False
        except Exception as e:
            logging.error(f"在{exchange}卖出失败: {e}")
            raise
    
    def calculate_trade_amount(self, buy_exchange, sell_exchange, buy_price):
        """计算可交易的BTC数量"""
        # 检查交易所是否在余额记录中
        if buy_exchange not in self.balances or sell_exchange not in self.balances:
            logging.warning(f"无法获取{buy_exchange}或{sell_exchange}的余额信息")
            return 0
        
        # 获取买入交易所的USDT余额和卖出交易所的BTC余额
        usdt_balance = self.balances[buy_exchange].get('USDT', 0)
        btc_balance = self.balances[sell_exchange].get('BTC', 0)
        
        # 计算基于USDT余额可购买的BTC数量
        max_buy_amount = usdt_balance / buy_price if buy_price > 0 else 0
        
        # 可交易的数量受限于：最小交易数量、最大交易数量、USDT余额、BTC余额、持仓比例
        # 考虑最大持仓比例限制
        total_equity = sum(v.get('USDT', 0) + v.get('BTC', 0) * buy_price for v in self.balances.values())
        max_position_by_equity = total_equity * Config.MAX_POSITION_RATIO / buy_price
        
        trade_amount = min(
            max_buy_amount,
            btc_balance,
            Config.MAX_TRADE_AMOUNT,
            max_position_by_equity
        )
        
        # 确保不低于最小交易数量
        if trade_amount < Config.MIN_TRADE_AMOUNT:
            return 0
        
        # 格式化数量，保留适当的小数位
        return self.format_number(trade_amount)
    
    def execute_arbitrage(self, prices):
        """执行套利交易"""
        if len(prices) < 2:
            logging.warning("获取的价格数据不足，无法进行套利")
            return
        
        # 找出价格最高和最低的交易所
        sorted_exchanges = sorted(prices.items(), key=lambda x: x[1])
        lowest_exchange, lowest_price = sorted_exchanges[0]
        highest_exchange, highest_price = sorted_exchanges[-1]
        
        # 计算价差和价差比例
        price_diff = highest_price - lowest_price
        price_diff_ratio = price_diff / lowest_price
        
        logging.info(f"当前价格 - 最低: {lowest_exchange} ({lowest_price:.2f} USDT), 最高: {highest_exchange} ({highest_price:.2f} USDT), 价差: {price_diff_ratio:.4%}")
        
        # 判断是否满足套利条件（考虑手续费和滑点）
        net_profit_ratio = price_diff_ratio - 2 * Config.FEE_RATE - Config.MAX_SLIPPAGE
        if net_profit_ratio >= Config.ARBITRAGE_THRESHOLD:
            logging.info(f"发现套利机会! 净收益{net_profit_ratio:.4%}超过阈值{Config.ARBITRAGE_THRESHOLD:.4%}")
            
            # 更新账户余额信息
            self.update_balances()
            
            # 计算可交易的BTC数量
            trade_amount = self.calculate_trade_amount(lowest_exchange, highest_exchange, lowest_price)
            
            if trade_amount <= 0:
                logging.warning(f"无法进行套利交易，可交易数量为0")
                return
            
            # 执行套利交易：先在高价交易所卖出，再在低价交易所买入
            try:
                # 1. 在高价交易所卖出BTC
                sell_success = self.sell_on_exchange(highest_exchange, trade_amount, highest_price)
                
                if not sell_success:
                    logging.error(f"在{highest_exchange}卖出BTC失败，取消套利")
                    self.performance_metrics["failed_trades"] += 1
                    return
                
                # 短暂等待，确保交易有时间处理
                time.sleep(1)
                
                # 2. 在低价交易所买入BTC
                buy_success = self.buy_on_exchange(lowest_exchange, trade_amount, lowest_price)
                
                if not buy_success:
                    logging.error(f"在{lowest_exchange}买入BTC失败，需要手动处理风险敞口")
                    self.performance_metrics["failed_trades"] += 1
                    return
                
                # 计算实际套利收益
                buy_cost = trade_amount * lowest_price
                sell_revenue = trade_amount * highest_price
                profit = sell_revenue - buy_cost - (buy_cost + sell_revenue) * Config.FEE_RATE
                profit_ratio = profit / buy_cost if buy_cost > 0 else 0
                
                logging.info(f"套利交易成功! 在{lowest_exchange}买入{trade_amount} BTC，在{highest_exchange}卖出，收益: {profit:.2f} USDT ({profit_ratio:.4%})")
                
                # 记录交易历史
                trade_record = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'buy_exchange': lowest_exchange,
                    'buy_price': lowest_price,
                    'sell_exchange': highest_exchange,
                    'sell_price': highest_price,
                    'amount': trade_amount,
                    'profit': profit,
                    'profit_ratio': profit_ratio
                }
                self.trade_history.append(trade_record)
                
                # 保存交易历史
                self.save_trade_history()
                
                # 更新业绩指标
                self.update_performance_metrics()
                
                # 更新运行中的盈亏
                self.running_pnl += profit
                
                # 再次更新余额
                self.update_balances()
                
                # 打印最新余额
                logging.info("交易后账户余额:")
                for exchange, balance in self.balances.items():
                    logging.info(f"  {exchange}: USDT={balance.get('USDT', 0):.2f}, BTC={balance.get('BTC', 0):.6f}")
                
            except Exception as e:
                logging.error(f"套利交易执行异常: {e}", exc_info=True)
                self.performance_metrics["failed_trades"] += 1
        elif price_diff_ratio > 0:
            logging.info(f"价差{price_diff_ratio:.4%}未达到套利阈值（考虑手续费和滑点后：{net_profit_ratio:.4%}）")
    
    def print_trade_history(self):
        """打印交易历史"""
        if not self.trade_history:
            logging.info("暂无交易历史")
            return
        
        logging.info("\n===== 交易历史 =====")
        total_profit = 0
        
        # 只打印最近10条交易记录
        recent_trades = self.trade_history[-10:]
        
        for trade in recent_trades:
            logging.info(f"时间: {trade['timestamp']}")
            logging.info(f"买入: {trade['buy_exchange']} @ {trade['buy_price']:.2f} USDT")
            logging.info(f"卖出: {trade['sell_exchange']} @ {trade['sell_price']:.2f} USDT")
            logging.info(f"数量: {trade['amount']} BTC")
            logging.info(f"收益: {trade['profit']:.2f} USDT ({trade['profit_ratio']:.4%})")
            logging.info("-------------------")
            total_profit += trade['profit']
        
        # 如果有超过10条记录，显示省略信息
        if len(self.trade_history) > 10:
            logging.info(f"... 省略{len(self.trade_history) - 10}条历史记录 ...")
        
        logging.info(f"总收益: {self.performance_metrics['total_profit']:.2f} USDT")
        logging.info(f"交易次数: {self.performance_metrics['total_trades']}")
        logging.info(f"胜率: {self.performance_metrics['win_rate']:.2%}")
        logging.info(f"平均每笔收益: {self.performance_metrics['avg_profit_per_trade']:.2f} USDT")
        logging.info(f"最大盈利: {self.performance_metrics['max_profit']:.2f} USDT")
        logging.info(f"最大亏损: {self.performance_metrics['max_loss']:.2f} USDT")
        
    def print_performance_report(self):
        """打印业绩报告"""
        logging.info("\n===== 业绩报告 =====")
        logging.info(f"总交易次数: {self.performance_metrics['total_trades']}")
        logging.info(f"成功交易: {self.performance_metrics['successful_trades']} ({self.performance_metrics['win_rate']:.2%})")
        logging.info(f"失败交易: {self.performance_metrics['failed_trades']}")
        logging.info(f"总盈利: {self.performance_metrics['total_profit']:.2f} USDT")
        logging.info(f"平均每笔收益: {self.performance_metrics['avg_profit_per_trade']:.2f} USDT")
        logging.info(f"最大盈利: {self.performance_metrics['max_profit']:.2f} USDT")
        logging.info(f"最大亏损: {self.performance_metrics['max_loss']:.2f} USDT")
        if self.performance_metrics['total_trades'] > 0:
            risk_reward_ratio = abs(self.performance_metrics['max_profit'] / self.performance_metrics['max_loss']) if self.performance_metrics['max_loss'] != 0 else float('inf')
            logging.info(f"风险回报比: {risk_reward_ratio:.2f}")
        logging.info("==================")

# 主程序
def main():
    logging.info("跨交易所现货套利策略启动")
    logging.info(f"监控交易所: Binance, Bitget, Gate, OKX, MEXC")
    logging.info(f"套利阈值: {Config.ARBITRAGE_THRESHOLD:.4%}")
    logging.info(f"检查间隔: {Config.CHECK_INTERVAL}秒")
    logging.info(f"交易对: {Config.TRADE_SYMBOL}")
    logging.info(f"模拟交易模式: {not Config.ENABLE_ACTUAL_TRADE}")
    logging.info("=" * 60)
    
    # 创建策略运行状态文件
    status_file = "arbitrage_status.json"
    
    try:
        # 初始化客户端
        clients = ExchangeClients()
        
        # 初始化价格获取器
        price_fetcher = PriceFetcher(clients)
        
        # 初始化套利交易器
        arbitrage_trader = ArbitrageTrader(clients)
        
        # 显示初始余额
        logging.info("初始账户余额:")
        for exchange, balance in arbitrage_trader.balances.items():
            logging.info(f"  {exchange}: USDT={balance.get('USDT', 0):.2f}, BTC={balance.get('BTC', 0):.6f}")
        
        # 显示初始业绩报告
        arbitrage_trader.print_performance_report()
        
        # 主循环
        cycle_count = 0
        while True:
            logging.info(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查价格... (周期 {cycle_count+1})")
            
            # 保存策略运行状态
            try:
                with open(status_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'last_run_time': datetime.datetime.now().isoformat(),
                        'cycle_count': cycle_count,
                        'performance': arbitrage_trader.performance_metrics,
                        'running_pnl': arbitrage_trader.running_pnl
                    }, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logging.error(f"保存策略状态失败: {e}")
            
            # 获取所有交易所的价格
            prices = price_fetcher.get_all_prices()
            
            if not prices:
                logging.warning("未能获取到任何交易所的价格，等待重试...")
                time.sleep(Config.CHECK_INTERVAL)
                continue
            
            # 打印当前价格（按价格排序）
            logging.info("当前各交易所BTC价格:")
            for exchange, price in sorted(prices.items(), key=lambda x: x[1]):
                logging.info(f"  {exchange}: {price:.2f} USDT")
            
            # 执行套利
            arbitrage_trader.execute_arbitrage(prices)
            
            # 每10个周期打印一次详细业绩报告
            cycle_count += 1
            if cycle_count % 10 == 0:
                arbitrage_trader.print_performance_report()
            else:
                # 否则只打印交易历史摘要
                arbitrage_trader.print_trade_history()
            
            # 等待下一次检查
            logging.info(f"等待{Config.CHECK_INTERVAL}秒后再次检查...")
            time.sleep(Config.CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        logging.info("\n程序已停止")
        # 打印最终业绩报告
        arbitrage_trader.print_performance_report()
        # 删除状态文件
        if os.path.exists(status_file):
            try:
                os.remove(status_file)
            except:
                pass
    except Exception as e:
        logging.error(f"程序异常: {e}", exc_info=True)
        # 打印最终业绩报告
        try:
            arbitrage_trader.print_performance_report()
        except:
            pass

if __name__ == "__main__":
    main()