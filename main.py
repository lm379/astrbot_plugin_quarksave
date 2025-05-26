import re
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .quark_save_api import QuarkSaveApi
from astrbot.core.star.filter.permission import PermissionType

# 用于匹配夸克网盘分享链接的正则表达式
Quark_ShareLink_Pattern = r"(https:\/\/pan\.quark\.cn\/s\/[a-f0-9]{12})(?:.*?(?:pwd|提取码|密码)\s*[=：:]?\s*([a-zA-Z0-9]{4}))?"


@register(
    "astrbot_plugin_quarksave",
    "lm379",
    "调用quark-auto-save转存资源到自己的夸克网盘",
    "1.0.4",
)
class QuarkSave(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        try:
            self.quark_save = QuarkSaveApi(config)  # 传递 QuarkSave 实例
        except Exception as e:
            logger.error(f"初始化QuarkSaveApi失败: {e}")
            raise

    async def initialize(self):
        await self.quark_save.initialize()

    @filter.command_group("quark")
    @filter.permission_type(PermissionType.ADMIN)
    def quark(self):
        pass

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("help", alias=["帮助", "helpme"])
    async def help(self, event: AstrMessageEvent):
        """帮助信息"""
        yield event.plain_result(
            """
        Hello, 这是一个调用夸克自动转存项目的插件
        你可以向我发送一条夸克网盘的分享链接，可以包含提取码
        我在识别后将调用quark-auto-save这个项目来添加转存任务
        请确保你已经提前部署好了该项目并配置好了 API token 和 URL
        如果准备工作已经就绪，那么，开始吧~

        指令格式:
        添加任务：直接发送分享链接（若有提取码请同时发送提取码）
        获取帮助：    /quark help
        获取任务列表：/quark list
        获取任务详情：/quark detail 任务id
        运行指定任务：/quark run 任务id
        运行所有任务：/quark runall
        删除指定任务：/quark del 任务id
        重命名任务：  /quark rename 任务id 新任务名
        修改任务目录：/quark update_dir 任务id 目录
        修改任务链接：/quark update_link 任务id 新链接
        更新任务子目录正则表达式：/quark update_subdir taskid 子目录正则表达式
        """
        )

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("run", alias=["执行", "运行"])
    async def run_task(self, event: AstrMessageEvent, id: int):
        """执行单个任务"""
        if id is None:
            yield event.plain_result("请输入任务ID")
            return
        resp = await self.quark_save.run_task(id)
        if resp["success"] == False:
            yield event.plain_result(resp["message"])
        else:
            yield event.plain_result(f'{resp["message"]}')

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("runall", alias=["执行所有", "运行所有"])
    async def run_all_task(self, event: AstrMessageEvent):
        """执行所有任务"""
        resp = await self.quark_save.run_task(None)
        yield event.plain_result(
            f"执行所有任务时耗时较久，消息会在1~3分钟内返回（取决于任务数量）"
        )
        yield event.plain_result(resp["message"])

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("list", alias=["列表", "任务列表"])
    async def get_list(self, event: AstrMessageEvent):
        """获取任务列表"""
        resp = await self.quark_save.get_task_list()
        if resp["success"] == False:
            yield event.plain_result(f"{resp['message']}")
        else:
            tasklist = ""
            for index, task in enumerate(resp["data"]):
                tasklist += f"ID: {index}  任务名: {task['taskname']}"
                if task.get("shareurl_ban"):
                    tasklist += f"  当前状态：{task['shareurl_ban']}"
                if index < len(resp["data"]) - 1:
                    tasklist += f"\n"
            yield event.plain_result(f"{tasklist}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("del", alias=["删除", "删除任务", "del"])
    async def del_task(self, event: AstrMessageEvent, id: int):
        """删除任务"""
        resp = await self.quark_save.del_task(id)
        yield event.plain_result(f"任务{id} {resp['message']}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("rename", alias=["重命名", "修改任务"])
    async def rename(self, event: AstrMessageEvent, id: int, name: str):
        """重命名任务"""
        resp = await self.quark_save.rename_task(
            id, name, dir=None, link=None, subdir=None
        )
        yield event.plain_result(f"任务{id} {resp['message']}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("update_link", alias=["修改链接", "更新链接"])
    async def update_link(self, event: AstrMessageEvent, id: int, link: str):
        """更新任务链接"""
        match = re.search(Quark_ShareLink_Pattern, link)
        if not match:
            yield event.plain_result("请提供有效的分享链接")
            return
        # 提取分享链接和提取码
        share_link = match.group(1)
        share_pwd = match.group(2) or None
        # 检查链接是否存在
        if self.quark_save.task_exists(share_link):
            yield event.plain_result("该链接已经存在")
        else:
            share_link = self.quark_save.build_share_url(share_link, share_pwd)
            resp = await self.quark_save.rename_task(
                id, link=share_link, dir=None, subdir=None, name=None
            )
            yield event.plain_result(f"任务{id} {resp['message']}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("update_dir", alias=["修改目录", "更新目录"])
    async def update_dir(self, event: AstrMessageEvent, id: int, dir: str):
        """更新任务目录"""
        if dir is None:
            yield event.plain_result("请输入目录")
            return
        # 检查目录是否以/开头
        if dir[0] != "/":
            dir = "/" + dir
        resp = await self.quark_save.rename_task(
            id, dir=dir, subdir=None, link=None, name=None
        )
        yield event.plain_result(f"任务{id} {resp['message']}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("update_subdir", alias=["修改子目录", "更新子目录"])
    async def update_subdir(self, event: AstrMessageEvent, id: int, subdir: str):
        """更新任务子目录正则表达式"""
        if subdir is None:
            yield event.plain_result("请输入子目录正则")
            return
        resp = await self.quark_save.rename_task(
            id, subdir=subdir, dir=None, link=None, name=None
        )
        yield event.plain_result(f"任务{id} {resp['message']}")

    @filter.permission_type(PermissionType.ADMIN)
    @quark.command("detail", alias=["详情", "任务详情"])
    async def get_detail(self, event: AstrMessageEvent, id: int):
        """获取任务详情"""
        resp = await self.quark_save.get_task_detail(id)
        if resp["success"] == False:
            yield event.plain_result(f"{resp['message']}")
        else:
            task = resp["data"]
            task_detail = f"ID: {id}\n任务名: {task['taskname']}\n链接: {task['shareurl']}\n保存目录: {task['savepath']}\n匹配表达式: {task['pattern']}\n替换表达式: {task['replace']}"
            if task.get("shareurl_ban"):
                task_detail += f"\n当前状态: {task['shareurl_ban']}"
            if task.get("update_subdir"):
                task_detail += f"\n子目录正则表达式: {task['update_subdir']}"
            yield event.plain_result(f"{task_detail}")

    # 监听所有消息，且只允许单聊
    @filter.permission_type(PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @filter.regex(
        r"^(?![\s\S]*\/quark)[\s\S]*?(https:\/\/pan\.quark\.cn\/s\/[a-f0-9]{12})(?:[^\n\r]*?(?:pwd|提取码|密码)\s*[=：:]?\s*([a-zA-Z0-9]{4}))?"
    )
    async def quark_share_link(self, event: AstrMessageEvent):
        """自动识别聊天记录中的分享链接"""
        message_str = event.message_str or ""

        if "/quark" in message_str:
            # 如果消息中包含/quark指令，则不处理
            return

        # 通过正则表达式匹配分享链接
        match = re.search(Quark_ShareLink_Pattern, message_str)
        if match:
            share_link = match.group(1)
            share_pwd = match.group(2) or None

            # 调用quark-auto-save
            if self.quark_save.task_exists(share_link):
                yield event.plain_result("该链接已经存在")
            else:
                share_detail = await self.quark_save.get_share_detail(
                    share_link, share_pwd
                )
                if share_detail["success"] == False:
                    yield event.plain_result(share_detail["message"])
                else:
                    # 去除标题中的.和空格
                    title = (
                        share_detail["data"]["share"]["title"]
                        .replace(".", "")
                        .replace(" ", "")
                    )
                    resp = await self.quark_save.add_share_task(
                        share_link, share_pwd, title
                    )
                    yield event.plain_result(f'任务 {title} {resp["message"]}')
