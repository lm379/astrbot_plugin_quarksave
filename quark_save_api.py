import requests
import json
import re
import aiohttp
import asyncio
from astrbot.api import logger

class QuarkSaveApi:
    def __init__(self, config: dict):
        self.cookie = {
            "QUARK_AUTO_SAVE_SESSION": config.get("quark_auto_save_cookie")
        }
        # self.quark_config = {"cookie": [],"push_config":{},"tasklist": [],"crontab": "","emby": {},"magic_regex": {},"plugins": {},"task_plugins_config": {}}
        self.save_path = config.get("quark_save_path")
        self.base_url = config.get("quark_auto_save_url")
        self.username = config.get("quark_auto_save_username") or "admin"
        self.password = config.get("quark_auto_save_password") or "admin123"
        self.run_now = config.get("quark_auto_save_run_now") or False
        self.error_message = {
            "status": "error",
            "message": "未填写Cookie或Cookie失效"
        }
        # 如果保存路径不是以/开头，则添加/
        if self.save_path and self.save_path[0] != "/":
            self.save_path = "/" + self.save_path
        # 如果URL不是以/结尾，则添加/
        if self.base_url and self.base_url[-1] != "/":
            self.base_url += "/"

    async def initialize(self):
        # 检查cookie和URL
        if await self.check_url():
            if await self.check_cookie():
                self.quark_config = await self.fetch_config()
            else:
                logger.info("当前Cookie无效，将尝试自动获取Cookie")
        else:
            logger.error("地址无效")

    # 获取配置
    async def fetch_config(self):
        base_url = self.base_url
        cookies = self.cookie
        url = base_url + "data"
        try:
            # 使用 aiohttp 替代 requests 实现异步
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return self.error_message
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return self.error_message
        
    # 检查地址是否有效
    async def check_url(self):
        base_url = self.base_url  # 直接从 quark_save 获取 base_url
        if not base_url.endswith("/"):
            base_url += "/"
        
        timeout = aiohttp.ClientTimeout(total=10)  # 设置超时时间为10秒
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(base_url) as response:
                    if response.status != 200:
                        return False
                    return True
        except aiohttp.ClientError as e:
            logger.error(f"检查URL超时: {base_url}")
        except Exception as e:
            logger.error(f"检查URL失败: {e}")
        return False
    
    # 检查Cookie是否有效
    async def check_cookie(self):
        base_url = self.base_url
        cookies = self.cookie
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(base_url) as response:
                if response.url == base_url + "login":
                    return False
                return True

    # 获取Cookie
    # async def get_cookies(self):
    #     url = base_url + "login"
    #     async with aiohttp.ClientSession() as session:
    #         async with session.post(url, json={"username": username, "password": password}) as response:
    #             if response.status == 200:
    #                 cookies = response.cookies.get_dict()
    #                 return cookies
    #             else:
    #                 return None

    # 获取分享链接详情
    async def get_share_detail(self, quark_share_link, pwd):
        base_url = self.base_url
        url = base_url + "get_share_detail"
        if pwd:
            share_link = quark_share_link + "?pwd=" + pwd
        else:
            share_link = quark_share_link
        querystring = {"shareurl": share_link}
        async with aiohttp.ClientSession() as session:
            async with session.get(url,querystring=querystring,cookies=self.cookie) as response:
                response_json = response.json()
                if 'error' in response_json:
                    return {
                        "status": "error",
                        "message": response_json["error"]
                    }
                return response_json
        # except Exception as e:
        # response = requests.get(url, params=querystring, cookies=cookies)
        

    # 检查链接是否已经存在
    def check_link_exist(self, share_link):
        pattern = r"/s/([a-f0-9]+)(?:[?#]|$)"  # 匹配分享链接的正则表达式
        share_link = re.search(pattern, share_link).group(1)
        for task in self.quark_config["tasklist"]:
            if re.search(pattern, task["shareurl"]).group(1) == share_link:
                return True
        return False

    # 更新配置
    async def update(self):
        url = self.base_url + "update"
        cookie = self.cookie
        async with aiohttp.ClientSession() as session:
            async with session.post(url,cookies=cookie,json=self.quark_config) as response:
                return response.json()

    # 添加分享任务
    async def add_share_task(self, share_link, pwd, save_path, title):
        if pwd != None:
            share_link = share_link + "?pwd=" + pwd

        task = {
            "taskname": title,
            "shareurl": share_link,
            "savepath": save_path,
            "pattern": "",
            "replace": "",
            "enddate": "",
            "addition": {
                "alist_strm_gen": {
                    "auto_gen": True
                },
                "aria2": {
                    "auto_download": False,
                    "pause": False
                },
                "emby": {
                    "try_match": True,
                    "media_id": ""
                }
            },
            "ignore_extension": False,
            "runweek": [1, 2, 3, 4, 5, 6, 7]
        }
        self.quark_config["tasklist"].append(task)
        resp = await self.update()
        await self.quark_config = self.fetch_config() # 刷新更新后的配置
        return resp

    # 获取任务列表
    async def get_task_list(self):
        task_list = self.quark_config["tasklist"]
        return task_list

    # 运行任务
    async def run_task(self,index):
        url = self.base_url + "run_script_now"
        querystring = {"task_index": index}
        async with aiohttp.ClientSession() as session:
            async with session.get(url,querystring=querystring,cookies=self.cookie) as response:
                response_json = response.json()
                return response_json
    
    # 删除指定任务        
    async def del_task(self,index):
        if 0 <= index < len(self.quark_config["tasklist"]):
            del self.quark_config[index]
            await self.update()
            await self.quark_config = self.fetch_config() # 刷新更新后的配置
            return {"删除成功"}
        else:
            return {"索引越界，不支持处理"}
        