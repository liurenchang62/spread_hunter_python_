#!/bin/bash
# =============================================================================
# 服务器安全部署脚本
#
# 用途：在 Vultr 等云服务器上安全部署 Spread Hunter 交易系统
# 功能：
#   1. 安装 Python 依赖
#   2. 创建安全的密钥存储目录
#   3. 设置文件权限保护
#   4. 配置实盘/模拟盘 API Key
#
# 使用方法（SSH 登录后，仓库根目录 /root/spread_hunter_python）：
#   chmod +x server/deploy_server.sh
#   ./server/deploy_server.sh
# =============================================================================

set -e  # 遇到错误立即退出

echo "=========================================="
echo "Spread Hunter 服务器安全部署脚本"
echo "=========================================="

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在 root 目录
cd /root/spread_hunter_python || {
    echo -e "${RED}错误：未找到 /root/spread_hunter_python 目录${NC}"
    echo "请先将代码克隆到 /root/spread_hunter_python"
    exit 1
}

echo -e "${GREEN}[1/6] 安装 Python 依赖...${NC}"
pip3 install -q aiohttp websockets numpy pandas || {
    echo -e "${RED}依赖安装失败${NC}"
    exit 1
}
echo -e "${GREEN}✓ 依赖安装完成${NC}"

echo -e "${GREEN}[2/6] 创建安全密钥存储目录...${NC}"
# 创建目录（如果不存在）
mkdir -p /root/.secrets
mkdir -p /root/.secrets_demo

# 设置目录权限（仅 root 可访问）
chmod 700 /root/.secrets
chmod 700 /root/.secrets_demo

echo -e "${GREEN}✓ 安全目录创建完成${NC}"
echo "  - /root/.secrets    (实盘密钥，权限 700)"
echo "  - /root/.secrets_demo (模拟盘密钥，权限 700)"

echo -e "${YELLOW}[3/6] 配置文件权限...${NC}"
# 设置代码文件权限
chmod -R 644 /root/spread_hunter_python/*.py
chmod -R 644 /root/spread_hunter_python/*/*.py
chmod -R 755 /root/spread_hunter_python/*/  # 目录保持可执行

# 保护敏感文件（如果不存在则创建空文件）
touch /root/spread_hunter_python/clients/api_keys_live.py
chmod 600 /root/spread_hunter_python/clients/api_keys_live.py

touch /root/spread_hunter_python/clients/api_keys_demo.py
chmod 600 /root/spread_hunter_python/clients/api_keys_demo.py

# 如果旧的 api_keys.py 存在，也保护它
if [ -f "/root/spread_hunter_python/clients/api_keys.py" ]; then
    chmod 600 /root/spread_hunter_python/clients/api_keys.py
fi

echo -e "${GREEN}✓ 文件权限设置完成${NC}"
echo "  - api_keys_live.py: 600 (仅 root 可读写)"
echo "  - api_keys_demo.py: 600 (仅 root 可读写)"

echo -e "${YELLOW}[4/6] 检查 API Key 配置...${NC}"
# 检查是否配置了密钥
python3 << 'PYTHON_EOF'
import sys
sys.path.insert(0, '/root/spread_hunter_python')

try:
    from clients.api_keys_live import check_live_keys
    live_status = check_live_keys()
    print("实盘 API Key 配置状态:")
    for ex, ok in live_status.items():
        status = "✓ 已配置" if ok else "✗ 未配置"
        print(f"  - {ex}: {status}")
except Exception as e:
    print(f"检查失败: {e}")

try:
    from clients.api_keys_demo import check_demo_keys
    demo_status = check_demo_keys()
    print("\n模拟盘 API Key 配置状态:")
    for ex, ok in demo_status.items():
        status = "✓ 已配置" if ok else "✗ 未配置"
        print(f"  - {ex}: {status}")
except Exception as e:
    print(f"检查失败: {e}")
PYTHON_EOF

echo -e "${YELLOW}[5/6] 安全提示...${NC}"
cat << 'EOF'

┌─────────────────────────────────────────────────────────────┐
│  ⚠️  安全警告                                                │
├─────────────────────────────────────────────────────────────┤
│  1. 实盘 API Key 已设置 600 权限，仅 root 可读写          │
│  2. 禁止将 api_keys_live.py 提交到 Git                     │
│  3. 建议定期更换 API Key（每 3 个月）                       │
│  4. 服务器防火墙仅开放必要端口（22/SSH）                    │
│  5. 建议禁用 root 密码登录，改用 SSH 密钥                   │
└─────────────────────────────────────────────────────────────┘

EOF

echo -e "${GREEN}[6/6] 运行测试...${NC}"
cd /root/spread_hunter_python
python3 -m test_demo.test_balance 2>&1 | head -20 || true

echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}部署完成！${NC}"
echo ""
echo "下一步："
echo "  1. 配置 API Key: nano /root/spread_hunter_python/clients/api_keys_live.py"
echo "  2. 或使用文件方式: echo 'your_key' > /root/.secrets/binance_api_key.txt"
echo "  3. 运行测试: python3 -m test_demo.run_all"
echo "  4. 启动系统: python3 main.py"
echo ""
echo -e "${YELLOW}实盘交易警告：${NC}"
echo "  启动实盘前务必确认："
echo "  - API Key 已配置并检查状态"
echo "  - 交易所白名单已添加服务器 IP"
echo "  - LIVE_TRADING_ON = True 已设置"
echo ""
