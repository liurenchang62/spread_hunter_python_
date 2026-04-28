# 【使用原版的cookie方式能够访问公告页面的数据，但是获取cookie之后确实可以登录账户并交易】
# 【cookie尽量使用对应的IP地址所获取到的cookie，避免风控问题导致公告获取失败】
#cookie处理
import os
# 获取当前文件的完整路径
current_file_path = os.path.abspath(__file__)
# 获取当前文件所在的目录
current_dir = os.path.dirname(current_file_path)
print("current_dir",current_dir)

import json
#cookie是在浏览器插件采集出来的【这里保存为字符粗格式再转json格式】
cookie='''[
{
    "domain": ".binance.com",
    "expirationDate": 1774865093.234455,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_ga",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "GA1.1.1202023219.1740304875",
    "id": 1
},
{
    "domain": ".binance.com",
    "expirationDate": 1774868372.477553,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_ga_3WP50LGEEC",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "GS1.1.1740308372.2.0.1740308372.60.0.0",
    "id": 2
},
{
    "domain": ".binance.com",
    "expirationDate": 1748081093,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_gcl_au",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "1.1.1855933532.1740305093",
    "id": 3
},
{
    "domain": ".binance.com",
    "expirationDate": 1740391493,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_gid",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "GA1.2.1483946861.1740304875",
    "id": 4
},
{
    "domain": ".binance.com",
    "expirationDate": 1740391496,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_uetsid",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "a2411e60f1cd11ef8f5f43b43394f82c",
    "id": 5
},
{
    "domain": ".binance.com",
    "expirationDate": 1774001096,
    "hostOnly": false,
    "httpOnly": false,
    "name": "_uetvid",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "a2415ce0f1cd11ef93c24588d70cb4a9",
    "id": 6
},
{
    "domain": ".binance.com",
    "expirationDate": 1771840874.738972,
    "hostOnly": false,
    "httpOnly": false,
    "name": "BNC_FV_KEY",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "3378ca60e1f1ac1cab5f824563d7bed5095f41ba",
    "id": 7
},
{
    "domain": ".binance.com",
    "expirationDate": 1771840874.73977,
    "hostOnly": false,
    "httpOnly": false,
    "name": "BNC_FV_KEY_EXPIRE",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "1740326474738",
    "id": 8
},
{
    "domain": ".binance.com",
    "expirationDate": 1771840874.73944,
    "hostOnly": false,
    "httpOnly": false,
    "name": "BNC_FV_KEY_T",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "101-z0XJSWGlA1X7zNloS8YSxSWc9n0Y8tiRqEwjYUe66VWr5GqJ4Rt3%2BlCZfU28lYkHdRU87QeGM0Dt0bXXEQfvHg%3D%3D-TVZ3XSfrY%2FsFtFMfGkw8YA%3D%3D-2d",
    "id": 9
},
{
    "domain": ".binance.com",
    "expirationDate": 1774864867.126003,
    "hostOnly": false,
    "httpOnly": false,
    "name": "bnc-uuid",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "5efe26a3-85e6-4558-a4e2-f99e216ab56b",
    "id": 10
},
{
    "domain": ".binance.com",
    "expirationDate": 1771846347,
    "hostOnly": false,
    "httpOnly": false,
    "name": "OptanonAlertBoxClosed",
    "path": "/",
    "sameSite": "lax",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "2025-02-23T11:32:27.958Z",
    "id": 11
},
{
    "domain": ".binance.com",
    "expirationDate": 1771846347,
    "hostOnly": false,
    "httpOnly": false,
    "name": "OptanonConsent",
    "path": "/",
    "sameSite": "lax",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "isGpcEnabled=0&datestamp=Sun+Feb+23+2025+19%3A32%3A27+GMT%2B0800+(%E4%B8%AD%E5%9B%BD%E6%A0%87%E5%87%86%E6%97%B6%E9%97%B4)&version=202411.2.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=04f95176-0c07-4814-9fb2-858006c93b48&interactionCount=2&isAnonUser=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0004%3A1%2CC0002%3A1&AwaitingReconsent=false&intType=1",
    "id": 12
},
{
    "domain": ".binance.com",
    "expirationDate": 1740326399,
    "hostOnly": false,
    "httpOnly": false,
    "name": "sajssdk_2015_cross_new_user",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "1",
    "id": 13
},
{
    "domain": ".binance.com",
    "expirationDate": 1771409092,
    "hostOnly": false,
    "httpOnly": false,
    "name": "sensorsdata2015jssdkcross",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": false,
    "storeId": "0",
    "value": "%7B%22distinct_id%22%3A%221953240e3fbccd-0455e52bc15a1c-4c657b58-1327104-1953240e3fc769%22%2C%22first_id%22%3A%22%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTk1MzI0MGUzZmJjY2QtMDQ1NWU1MmJjMTVhMWMtNGM2NTdiNTgtMTMyNzEwNC0xOTUzMjQwZTNmYzc2OSJ9%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%22%2C%22value%22%3A%22%22%7D%7D",
    "id": 14
},
{
    "domain": ".binance.com",
    "hostOnly": false,
    "httpOnly": false,
    "name": "theme",
    "path": "/",
    "sameSite": "unspecified",
    "secure": false,
    "session": true,
    "storeId": "0",
    "value": "dark",
    "id": 15
},
{
    "domain": ".www.binance.com",
    "expirationDate": 1740650463,
    "hostOnly": false,
    "httpOnly": false,
    "name": "aws-waf-token",
    "path": "/",
    "sameSite": "lax",
    "secure": true,
    "session": false,
    "storeId": "0",
    "value": "de91a739-dca1-4837-83df-d3cfc7fb6499:EQoAnsRF12Q0AAAA:qSO4EYmwiXmpEjpqk1GrBziISRsr1ZB1XmntYuTl0od++tGbHcfK0Vc9gPvu2tTdBDRr0xeGADYpy/8nWxEZFdSv/X2qH0LwYySJmbZxt7F88RVjwUd6JwZIPIhf3hx0Pvvk1OXAbFBVubszerwG6XAbAflu0WWm0DBgT5z3piTQr83MwAKMhoWVXw6h4ipAsqY=",
    "id": 16
}
]'''
cookies=json.loads(cookie)
# 定义需要的键的顺序
cookie_dict = {}
# 按照定义的顺序遍历并添加到字典
for cookie in cookies:
    cookie_dict[cookie["name"]] = cookie["value"]
print(cookie_dict)

with open(f'cookie.json', 'w') as f:
    f.write(json.dumps(cookie_dict))
print("Cookies已保存到文件")

#【requests访问】
import requests
# 发起请求时传递 cookies 参数
response = requests.get('https://www.binance.com/en/support/announcement/new-cryptocurrency-listing?c=48&navId=48', cookies=cookie_dict)
print(response.text)

# #【selenium访问】
# # 初始化浏览器
# driver = webdriver.Edge()
# driver.get('https://www.binance.com')
# time.sleep(1) # 等待页面加载
# # 加载Cookies
# for cookie in cookie_dict:
#     print(cookie,cookie_dict[cookie])
#     driver.add_cookie({"name":cookie,"value":cookie_dict[cookie]})
# # 刷新页面以应用Cookies
# driver.get('https://www.binance.com/en/support/announcement/new-cryptocurrency-listing?c=48&navId=48')
# # time.sleep(1) # 等待页面加载
# time.sleep(5000) # 等待页面加载
# # # 关闭浏览器
# # driver.quit()