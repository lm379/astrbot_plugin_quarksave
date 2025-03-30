import requests
import json
import re
import aiohttp
import asyncio
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .main import QuarkSave

class QuarkSaveApi:
    def __init__(self, quark_save: "QuarkSave"):
        self.quark_save = quark_save  # 保存 QuarkSave 实例的引用
        self.error_message = {
            "status": "error",
            "message": "未填写Cookie或Cookie失效"
        }

    # 检查地址是否有效
    async def check_url(self):
        base_url = self.quark_save.base_url  # 直接从 quark_save 获取 base_url
        if not base_url.endswith("/"):
            base_url += "/"
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url) as response:
                if response.status != 200:
                    return False
                return True

    # 检查Cookie是否有效
    async def check_cookie(self):
        base_url = self.quark_save.base_url
        cookies = self.quark_save.cookie
        if await self.check_url() == False:
            return False
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.get(base_url) as response:
                if response.url == base_url + "login":
                    return False
                return True

    async def get_cookies(self):
        base_url = self.quark_save.base_url
        username = self.quark_save.username
        password = self.quark_save.password
        url = base_url + "login"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"username": username, "password": password}) as response:
                if response.status == 200:
                    cookies = response.cookies.get_dict()
                    return cookies
                else:
                    return None

    # 获取分享链接详情
    def get_share_detail(self, quark_share_link, pwd):
        if not self.check_cookie():
            return self.error_message
        base_url = self.quark_save.base_url
        cookies = self.quark_save.cookie
        url = base_url + "get_share_detail"
        if pwd:
            share_link = quark_share_link + "?pwd=" + pwd
        else:
            share_link = quark_share_link
        querystring = {"shareurl": share_link}
        response = requests.get(url, params=querystring, cookies=cookies)
        response_json = response.json()
        if 'error' in response_json:
            return {
                "status": "error",
                "message": response_json["error"]
            }
        return response_json

    # 获取配置
    def get_config(self):
        if self.check_cookie() == False:
            return self.error_message
        base_url = self.quark_save.base_url
        cookies = self.quark_save.cookie
        url = base_url + "data"
        response = requests.get(url, cookies=cookies)
        return response.json()

    # 检查链接是否已经存在
    def check_link_exist(self, share_link):
        config = self.get_config()
        if config == self.error_message:
            return self.error_message
        pattern = r"/s/([a-f0-9]+)(?:[?#]|$)"  # 匹配分享链接的正则表达式
        share_link = re.search(pattern, share_link).group(1)
        for task in config["tasklist"]:
            if re.search(pattern, task["shareurl"]).group(1) == share_link:
                return True
        return False

    # 添加分享任务
    def add_share_task(self, share_link, pwd, save_path, title):
        if self.check_cookie() == False:
            return self.error_message
        config = self.get_config()
        if config == self.error_message:
            return self.error_message
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
        config["tasklist"].append(task)
        base_url = self.quark_save.base_url
        cookies = self.quark_save.cookie
        url = base_url + "update"
        try:
            response = requests.post(url, json=config, cookies=cookies)
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "status": "error",
                    "code": response.status_code,
                    "message": "添加任务失败"
                }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }
