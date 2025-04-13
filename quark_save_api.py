import re
import os
import aiohttp
from astrbot.api import logger
from typing import Optional, Dict, List

class APIConnectionError(Exception):
    """API连接异常"""
    def __init__(self, message="quark-auto-save API连接失败，可能是API Token错误或服务未启动"):
        super().__init__(message)
        logger.error(message)

class APIResponseError(Exception):
    """API响应异常"""
    def __init__(self, message="quark-auto-save 无响应，可能是URL错误或服务未启动"):
        super().__init__(message)
        logger.error(message)

class HttpClient:
    def __init__(self, base_url: str, API_Token: str = None):
        self.base_url = base_url.rstrip('/') + '/'
        self.Token = API_Token
        self.timeout = aiohttp.ClientTimeout(total=10)

    async def request(self, method: str, endpoint: str, **kwargs) -> Dict:
        if not self.Token:
            logger.warning("API Token未设置，请检查配置")
            return {"success": False, "message": "Token 未设置"}
        if not self.base_url:
            logger.warning("无法发送请求，因为 base_url 未设置或设置错误")
            return {"success": False, "message": "base_url 未设置"}
        params = kwargs.pop('params', {})
        if self.Token:
            params['token'] = self.Token
        url = self.base_url + endpoint.lstrip('/')
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {'Content-Type': 'application/json'}
                async with session.request(method, url, params=params, headers=headers, **kwargs) as response:
                    # 使用 await 等待响应的JSON解析完成
                    response_json = await response.json()
                    if response_json.get('success') == 'false':
                        logger.error(f"API请求失败: {response_json.get('message', '未知错误')}")
                    return response_json
        except aiohttp.ClientConnectorError as e:
            logger.warning(f"无法连接到 API: {e}")
            return {"success": False, "message": "无法连接到 API，请检查 base_url 是否正确"}
        except aiohttp.ClientResponseError as e:
            logger.error(f"API响应错误: {e}")
            return {"success": False, "message": f"API响应错误: {e}"}
        except aiohttp.ClientError as e:
            logger.error(f"API客户端错误: {e}")
            return {"success": False, "message": f"API连接错误: {e}"}
        except Exception as e:
            logger.error(f"API请求未知错误: {e}")
            return {"success": False, "message": f"API请求未知错误: {e}"}

    async def request_text(self, method: str, endpoint: str, **kwargs) -> Dict:
        params = kwargs.pop('params', {})
        if self.Token:
            params['token'] = self.Token
        url = self.base_url + endpoint.lstrip('/')
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {'Content-Type': 'application/json'}
                async with session.request(method, url, params=params, headers=headers, **kwargs) as response:
                    return await response.text()
        except aiohttp.ClientResponseError as e:
            logger.error(f"API响应错误: {e}")
            return None
        
class QuarkConfigManager:
    def __init__(self, http_client: HttpClient):
        self.http = http_client
        self._config: Optional[Dict] = None
    
    async def load(self):
        """加载配置"""
        try:
            response = await self.http.request('GET', 'data')
            if response.get("success") is True:
                self._config = response.get("data", {})
            else:
                logger.error(f"加载配置失败: {response.get('message', '未登录或Token错误')}")
                self._config = None
        except APIResponseError as e:
            logger.error(f"加载配置失败: {e}")
            self._config = None

    async def update(self):
        """更新配置"""
        response = await self.http.request('POST', 'update', json=self._config)
        if response.get("success") is True:
            await self.load()  # 刷新配置
        else:
            logger.error(f"更新配置失败: {response.get('message', '未知登录或Token错误')}")
            self._config = None

    @property
    def config(self) -> Dict:
        """获取配置"""
        if not self._config:
            logger.error("配置未初始化")
            return {}
        return self._config
    
    @property
    def task(self) -> List[Dict]:
        """获取任务列表"""
        return self._config.get("tasklist", [])

class QuarkSaveApi:
    def __init__(self, config: dict):
        self._init_settings(config)
        self.http = HttpClient(
            config["quark_auto_save_url"],
            config["quark_auto_save_token"]
        )
        self.config_manager = QuarkConfigManager(self.http)

    def _init_settings(self, config: dict):
        """初始化设置"""
        self.save_path = config.get("quark_save_path", "")
        if self.save_path and self.save_path[0] != "/":
            self.save_path = "/" + self.save_path

    async def initialize(self):
        """初始化连接"""
        await self._check_connection()
        await self.config_manager.load()

    async def _check_connection(self):
        """检查基础连接"""
        try:
            await self.http.request('GET', 'data')
        except APIConnectionError as e:
            logger.error(f"连接quark-auto-save失败: {e}")
            return False

    def build_share_url(self, base_url: str, pwd: Optional[str]) -> str:
        """构建完整分享链接"""
        return f"{base_url}?pwd={pwd}" if pwd else base_url

    async def get_share_detail(self, quark_share_link, pwd):
        """获取分享链接详情"""
        url = self.build_share_url(quark_share_link, pwd)
        return await self.http.request('GET', 'get_share_detail', params={'shareurl': url})
        
    # 检查链接是否已经存在
    def task_exists(self, share_link: str) -> bool:
        """检查任务是否存在"""
        pattern = r"/s/([a-f0-9]+)(?:[?#]|$)"  # 匹配分享链接的正则表达式
        share_link = re.search(pattern, share_link).group(1)
        for task in self.config_manager.task:
            if re.search(pattern, task["shareurl"]).group(1) == share_link:
                return True
        return False

    # 添加分享任务
    async def add_share_task(self, share_link: str, pwd: Optional[str], title: str):
        share_link = self.build_share_url(share_link, pwd)
        save_path = os.path.join(self.save_path, title)
        payload = {
            "shareurl": share_link,
            "savepath": save_path,
            "taskname": title,
        }
        if self.task_exists(share_link):
            return {"success": False, "message": "分享链接已存在"}
        try:
            response_data = await self.http.request('POST', '/api/add_task', json=payload)
            if response_data.get("success") is True:
                await self.config_manager.load() # 刷新配置
                return {"success": True, "message": "添加任务成功"}
        except APIResponseError as e:
            logger.error(f"添加任务失败: {e}")
            return {"success": False, "message": "添加任务失败"}

    # 运行任务
    async def run_task(self, index: Optional[int] = None):
        """运行指定任务或所有任务"""
        if index is None:
            params = {"task_index": ""}
        else:
            params = {"task_index": index}
            if index < 0 or index >= len(self.config_manager.task):
                return {"success": False, "message": "索引越界，不支持处理"}
        data = await self.http.request_text('GET', 'run_script_now', params=params)
        return {"success": True, "message": data}
    
    # 删除指定任务        
    async def del_task(self, index: int):
        if 0 <= index < len(self.config_manager.task):
            del self.config_manager.config["tasklist"][index]
            await self.config_manager.update()
            return {"success": True, "message": "删除成功"}
        else:
            return {"success": False, "message":"索引越界，不支持处理"}
        
    # 修改指定任务
    async def rename_task(self, index, name, dir, link, subdir):
        if index < 0 or index >= len(self.config_manager.task):
            return {"success": False, "message": "索引越界，不支持处理"}
        # 复制tasklist，避免直接修改原数据
        task = self.config_manager.task[index]
        # 修改任务名称
        if name:
            task["taskname"] = name
            if task["taskname"]:
                base_path = os.path.dirname(task["savepath"])
                # 如果任务名称不为空，则使用任务名称作为子目录
                task["savepath"] = os.path.join(base_path, name)
        if dir:
            # 将目录修改为 /dir/taskname
            task["savepath"] = os.path.join(dir, os.path.basename(task["taskname"]))
        if link:
            task["shareurl"] = link
            del task["shareurl_ban"] # 删除分享链接失效标记
        if subdir:
            task["update_subdir"] = subdir # 子目录正则表达式
        if dir is None and link is None and subdir is None and name is None:
            return {"success": False, "message": "没有需要修改的内容"}
        self.config_manager.config[index] = task
        await self.config_manager.update()
        return {"success": True, "message": "修改成功"}
        
    # 获取任务详情
    async def get_task_detail(self, index):
        if index < 0 or index >= len(self.config_manager.task):
            return {"success": False, "message": "索引越界，不支持处理"}
        task = self.config_manager.task[index]
        return {"success": True, "message": "success", "data": task}
    
    # 获取任务列表
    async def get_task_list(self):
        try:
            tasklist = self.config_manager.task
            if not tasklist:
                return {"success": False, "message": "没有任务"}
            return {"success": True, "message": "success", "data": tasklist}
        except Exception as e:
            logger.error(f"获取任务列表失败: {e}")
            return {"success": False, "message": "获取任务列表失败"}