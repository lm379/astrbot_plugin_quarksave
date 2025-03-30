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
            # raise ValueError("QUARK_AUTO_SAVE_SESSION cookie 未设置或无效，请检查配置")
        if not await self.quark_save.check_url():
            logger.error("quark-auto-save地址无效，请检查配置")
            return
        await self.quark_save.initialize()
            # raise ValueError("quark-auto-save地址无效，请检查配置")
    
    @filter.command_group("quark")
    async def quark(self, event: AstrMessageEvent):
        yield event.plain_result(f"Hello, 这是一个调用夸克自动转存项目的插件\n你可以向我发送一条夸克网盘的分享链接\n我在识别后将调用quark-auto-save这个项目来添加转存任务\n请确保你已经提前部署好了该项目并配置好了cookie或账号密码\n如果准备工作已经就绪，那么，开始吧~") # 发送一条纯文本消息
    
    @quark.command("help", alias=['帮助', 'helpme'])
    async def help(self, event: AstrMessageEvent):
        yield event.plain_result(f"Hello, 这是一个调用夸克自动转存项目的插件\n你可以向我发送一条夸克网盘的分享链接\n我在识别后将调用quark-auto-save这个项目来添加转存任务\n请确保你已经提前部署好了该项目并配置好了cookie或账号密码\n如果准备工作已经就绪，那么，开始吧~")

    @quark.command("run")
    def run_task(self, event: AstrMessageEvent, id: int):
        yield event.plain_result(f"开始运行任务 {id}")

    @quark.command("list")
    def get_list(self, event: AstrMessageEvent):
        yield event.plain_result(f"获取任务列表")
    
    # 监听所有消息，且只允许单聊
    @filter.permission_type(PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def quark_share_link(self, event: AstrMessageEvent):
        message_str = event.message_str or ""
        message_chain = event.get_messages()
        # 通过正则表达式匹配分享链接
        match = re.search(Quark_ShareLink_Pattern, message_str)
        if match:
            share_link = match.group(1)
            share_pwd = match.group(2) or None

            # 调用quark-auto-save
            if await self.quark_save.check_cookie() == False:
                yield event.plain_result("未填写Cooike或Cookie失效")
            elif self.quark_save.check_link_exist(share_link):
                yield event.plain_result("该链接已经存在")
            else:
                share_detail = self.quark_save.get_share_detail(share_link, share_pwd)
                if "status" in share_detail and share_detail["status"] == "error":
                    yield event.plain_result(share_detail["message"])
                else:
                    # 去除标题中的.和空格
                    title = share_detail["share"]["title"].replace(".", "").replace(" ", "")
                    save_path = self.save_path + title
                    res = await self.quark_save.add_share_task(share_link, share_pwd, save_path, title)
                    yield event.plain_result(res["message"])
