# API 配置指南 / API Configuration Guide

本文档说明如何配置交易所 API Key，支持实盘交易和模拟盘测试。

---

## 📁 配置文件结构

```
clients/
├── urls.py                        # WebSocket/REST URL（公开）
├── config.py                      # 交易所分级、格式转换（公开）
├── api_keys_live.py               # 本地创建，勿提交（见 *.example.py）
├── api_keys_demo.example.py       # 模拟盘 Key 模板（可提交）
├── api_keys_demo.py               # 本地复制 example 后填写，勿提交
├── withdrawal_addresses.example.py
├── withdrawal_addresses.py        # 充值地址，勿提交
└── __init__.py

trader/
├── config.example.py              # 可提交
└── config.py                      # 本地复制 example 后修改，勿提交
```

**克隆仓库后：** 将各 `*.example.py` 复制为同名去掉 `.example` 的文件，再填入密钥与地址。

---

## 🔐 安全警告

| 文件 | 敏感度 | Git 提交 | 服务器权限 |
|------|--------|----------|-----------|
| `api_keys_live.py` | ⚠️ **极高**（实盘，真实资金）| ❌ 禁止 | `chmod 600` |
| `api_keys_demo.py` | 凭证 | ❌ 禁止 | `chmod 600` |
| `withdrawal_addresses.py` | 链上地址 | ❌ 禁止 | `chmod 600` |
| `trader/config.py` | 代理 URL、实盘开关等 | ❌ 禁止 | 按需 |
| `urls.py`, `clients/config.py` | 无 | ✅ 允许 | 普通权限 |
| `*.example.py` | 无密钥 | ✅ 允许 | 普通权限 |

---

## 🚀 快速配置（二选一）

### 方式 A：直接填写（适合本地开发）

编辑 `clients/api_keys_live.py`：

```python
# 方式 A：直接填写
BINANCE_API_KEY = "your_actual_api_key_here"
BINANCE_SECRET_KEY = "your_actual_secret_here"

OKX_API_KEY = "your_okx_api_key"
OKX_SECRET_KEY = "your_okx_secret"
OKX_PASSPHRASE = "your_passphrase"

# ... 其他交易所
```

### 方式 B：文件读取（推荐服务器部署）

1. 创建安全目录：
```bash
mkdir -p /root/.secrets
chmod 700 /root/.secrets
```

2. 将 Key 保存到文件：
```bash
echo "your_api_key" > /root/.secrets/binance_api_key.txt
echo "your_secret" > /root/.secrets/binance_secret.txt
chmod 600 /root/.secrets/*.txt
```

3. 在 `api_keys_live.py` 中启用文件模式：
```python
USE_KEY_FILES = True  # 启用文件读取模式
```

---

## 🧪 模拟盘配置（测试用）

编辑 `clients/api_keys_demo.py`，获取方式：

| 交易所 | 测试网地址 |
|--------|-----------|
| Binance | https://testnet.binance.vision/ |
| OKX | https://www.okx.com/account/my-api (Demo Trading) |
| Gate | https://www.gate.io/futures_testnet |
| Bitget | https://www.bitget.com/demo-trading |

---

## 🖥️ 服务器部署步骤

### 1. 上传代码到服务器

```bash
# 本地
scp -r spread_hunter_python root@45.63.61.93:/root/
```

### 2. 运行部署脚本

```bash
ssh root@45.63.61.93
cd /root/spread_hunter_python
chmod +x deploy_server.sh
./deploy_server.sh
```

### 3. 配置实盘 API Key

**方式一：直接编辑文件**
```bash
nano /root/spread_hunter_python/clients/api_keys_live.py
# 填入 Key 后保存
```

**方式二：使用密钥文件（更安全）**
```bash
# 创建目录
mkdir -p /root/.secrets
chmod 700 /root/.secrets

# 写入密钥
echo "your_binance_key" > /root/.secrets/binance_api_key.txt
echo "your_binance_secret" > /root/.secrets/binance_secret.txt
chmod 600 /root/.secrets/*.txt
```

### 4. 验证配置

```bash
cd /root/spread_hunter_python
python3 -m test.test_balance
```

### 5. 启动系统

```bash
# 模拟盘测试
python3 main.py

# 实盘（慎用！）
python3 main.py --live
```

---

## ⚙️ 实盘/模拟盘切换

### 自动判断

系统根据 `trader/config.py` 中的 `LIVE_TRADING_ON` 自动选择：

```python
# trader/config.py
LIVE_TRADING_ON = False  # False=模拟盘, True=实盘
```

### 环境变量覆盖

```bash
# 设置环境变量强制使用实盘
export LIVE_TRADING_ON=1
python3 main.py
```

### 命令行参数（实盘模式）

```bash
python3 main.py --live  # 强制实盘模式（会要求确认）
```

---

## 🔒 服务器安全加固

### 1. 文件权限检查

```bash
# 检查敏感文件权限
ls -la /root/spread_hunter_python/clients/api_keys_*.py
# 应该是：-rw------- (600)

# 检查密钥目录权限
ls -la /root/.secrets
# 应该是：drwx------ (700)
```

### 2. SSH 安全建议

编辑 `/etc/ssh/sshd_config`：

```bash
# 禁用 root 密码登录（改用密钥）
PermitRootLogin prohibit-password
PubkeyAuthentication yes

# 修改默认端口（可选）
Port 2222

# 重启 SSH
systemctl restart sshd
```

### 3. 防火墙配置

```bash
# 仅开放 SSH 端口
ufw default deny incoming
ufw allow 22/tcp  # 或 2222 如果你改了端口
ufw enable
```

---

## 🆘 紧急情况处理

### API Key 泄露

1. **立即撤销 API Key**
   - 登录各交易所，删除该 API Key

2. **创建新 Key**
   - 重新生成 API Key 和 Secret

3. **更新服务器**
   ```bash
   nano /root/spread_hunter_python/clients/api_keys_live.py
   # 填入新 Key
   ```

4. **检查账户**
   - 查看交易记录、余额变动
   - 如有异常立即冻结账户并联系交易所

---

## 📞 常见问题

**Q: 可以同时配置实盘和模拟盘吗？**  
A: 可以。`api_keys_live.py` 用于实盘，`api_keys_demo.py` 用于模拟盘。通过 `LIVE_TRADING_ON` 切换。

**Q: 服务器 IP 变了怎么办？**  
A: 需要更新所有交易所的 API 白名单。建议购买固定 IP 的服务器避免此问题。

**Q: 使用文件方式还是直接填写更好？**  
A: 服务器部署推荐文件方式（更安全），本地开发可以直接填写。

**Q: 如何验证 Key 配置正确？**  
A: 运行 `python3 -m test.test_balance`，看能否正确查询余额。

---

## ✅ 配置检查清单

- [ ] 实盘 API Key 已填入 `api_keys_live.py` 或 `.secrets/` 目录
- [ ] 模拟盘 API Key 已填入 `api_keys_demo.py`（如需测试）
- [ ] 敏感文件权限已设置为 600
- [ ] 交易所白名单已添加服务器 IP
- [ ] 运行测试通过
- [ ] 实盘交易前已双重确认配置
