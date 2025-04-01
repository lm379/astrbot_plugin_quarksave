import re
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .quark_save_api import QuarkSaveApi
from astrbot.core.star.filter.permission import PermissionType

# 用于匹配夸克网盘分享链接的正则表达式
Quark_ShareLink_Pattern = r"(https:\/\/pan\.quark\.cn\/s\/[a-f0-9]{12})(?:.*?(?:pwd|提取码|密码)\s*[=：:]?\s*([a-zA-Z0-9]{4}))?"

@register("astrbot_plugin_quarksave", "lm379", "调用quark-auto-save转存资源到自己的夸克网盘", "1.0.0")
class QuarkSave(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)   
        self.config = config
        self.cookie = {
            "QUARK_AUTO_SAVE_SESSION": config.get("quark_auto_save_cookie")
        }
        self.save_path = config.get("quark_save_path")
        self.base_url = config.get("quark_auto_save_url")
        # 如果保存路径不是以/开头，则添加/
        if self.save_path and self.save_path[0] != "/":
            self.save_path = "/" + self.save_path
        if self.save_path and self.save_path[-1] != "/":
            self.save_path += "/"
        # 如果URL不是以/结尾，则添加/
        if self.base_url and self.base_url[-1] != "/":
            self.base_url += "/"
        try:
            self.quark_save = QuarkSaveApi(config)  # 传递 QuarkSave 实例
        except Exception as e:
            logger.error(f"初始化QuarkSaveApi失败: {e}")
            raise

    async def initialize(self):
        # 未填写cookie
        quark_session = self.cookie.get("QUARK_AUTO_SAVE_SESSION")
        if not quark_session or quark_session == "your cookie" or quark_session.strip() == "":
            logger.error("请填写cookie")
            return
        if not await self.quark_save.check_url():
            logger.error("quark-auto-save地址无效，请检查配置")
            return
        await self.quark_save.initialize()
    
    @filter.command_group("quark")
    def quark(self):
        pass

    @quark.command("help", alias=['帮助', 'helpme'])
    async def help(self, event: AstrMessageEvent):
        '''帮助信息'''
        yield event.plain_result(f"Hello, 这是一个调用夸克自动转存项目的插件\n你可以向我发送一条夸克网盘的分享链接，可以包含提取码\n我在识别后将调用quark-auto-save这个项目来添加转存任务\n请确保你已经提前部署好了该项目并配置好了cookie\n如果准备工作已经就绪，那么，开始吧~\n指令格式:\n获取帮助：/quark help\n获取任务列表：/quark list\n运行指定任务：/quark run 任务id\n运行所有任务：/quark runall\n删除指定任务：/quark del 任务id")

    @quark.command("run", alias=['执行', '运行'])
    async def run_task(self, event: AstrMessageEvent, id: int):
        '''执行单个任务'''
        if id is None:
            yield event.plain_result("请输入任务ID")
            return
        resp = await self.quark_save.run_task(id)
        if resp["code"] == 1:
            yield event.plain_result(resp["message"])
        else:
            yield event.plain_result(f'任务 {id} 运行成功\n{resp["message"]}')
    
    @quark.command("runall", alias=['执行所有', '运行所有'])
    async def run_all_task(self, event: AstrMessageEvent):
        '''执行所有任务'''
        resp = await self.quark_save.run_task(None)
        yield event.plain_result(f"执行所有任务时耗时较久，消息会在1~3分钟内返回（取决于任务数量）")
        yield event.plain_result(resp["message"])

    @quark.command("list", alias=['列表', '任务列表'])
    async def get_list(self, event: AstrMessageEvent):
        '''获取任务列表'''
        resp = await self.quark_save.get_task_list()
        if resp["code"] == 1:
            yield event.plain_result(f"{resp['message']}")
        else:
            tasklist = ""
            for index, task in enumerate(resp['data']):
                tasklist += f"ID: {index}  任务名: {task['taskname']}"
                if task.get("shareurl_ban"):
                    tasklist += f"  当前状态：{task['shareurl_ban']}"
                if index < len(resp["data"]) - 1:
                    tasklist += f"\n\n"
            yield event.plain_result(f"{tasklist}")

    @quark.command("del", alias=['删除', '删除任务', 'del'])
    async def del_task(self, event: AstrMessageEvent, id: int):
        '''删除任务'''
        resp = await self.quark_save.del_task(id)
        yield event.plain_result(f"任务{id} {resp['message']}")
    
    # 监听所有消息，且只允许单聊
    @filter.permission_type(PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def quark_share_link(self, event: AstrMessageEvent):
        '''自动识别聊天记录中的分享链接'''
        message_str = event.message_str or ""
        # 通过正则表达式匹配分享链接
        match = re.search(Quark_ShareLink_Pattern, message_str)
        if match:
            share_link = match.group(1)
            share_pwd = match.group(2) or None

            # 调用quark-auto-save
            if self.quark_save.check_link_exist(share_link):
                yield event.plain_result("该链接已经存在")
                self.quark_save.quark_config = await self.quark_save.fetch_config()  # 刷新配置
            else:
                share_detail = await self.quark_save.get_share_detail(share_link, share_pwd)
                if share_detail["code"] == 1:
                    yield event.plain_result(share_detail["message"])
                else:
                    # 去除标题中的.和空格
                    title = share_detail["data"]["share"]["title"].replace(".", "").replace(" ", "")
                    save_path = self.save_path + title
                    resp = await self.quark_save.add_share_task(share_link, share_pwd, save_path, title)
                    yield event.plain_result(f'任务 {title} {resp["message"]}')