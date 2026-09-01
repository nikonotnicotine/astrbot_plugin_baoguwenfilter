"""
astrbot_plugin_baoguwenfilter — 八股文过滤器
对 LLM 返回的文字进行正则过滤/替换，消除常见套话，
并在下次请求前清理对话历史，防止 LLM 重复学习原始内容。
"""

import json
import re

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


@register(
    "baoguwenfilter",
    "user",
    "对 LLM 返回内容进行八股文过滤/替换，并清理历史",
    "1.0.0",
)
class BaoguwenFilterPlugin(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.context = context
        logger.info("📝 八股文过滤器已加载。")

    # ------------------------------------------------------------------
    # 构建当前生效的规则列表
    # ------------------------------------------------------------------

    def _build_rules(self) -> list[tuple[re.Pattern, str]]:
        """返回 (compiled_pattern, replacement) 的有序列表。
        replacement 为空字符串表示删除匹配内容。
        """
        cfg = self.config  # AstrBot Star 基类属性，对应插件配置
        rules: list[tuple[re.Pattern, str]] = []

        def add_delete(key: str, pattern: str) -> None:
            if cfg.get(key, False):
                rules.append((re.compile(pattern), ""))

        def add_replace(key: str, pattern: str, repl: str) -> None:
            if cfg.get(key, False):
                rules.append((re.compile(pattern), repl))

        # 1. 极其、一丝
        add_delete("filter_jiqi_yisi", r"极其|一丝")
        # 2. 老子 → 我
        add_replace("replace_laozi", r"老子", "我")
        # 3. 嫉妒 → 忮忌
        add_replace("replace_jidu", r"嫉妒", "忮忌")
        # 4. 他妈 → 他爹
        add_replace("replace_tama", r"他妈", "他爹")
        # 5. 一种近乎、带着一种
        add_delete("filter_jinhuzhe", r"一种近乎|带着一种")
        # 6. 微不可察、不易察觉
        add_delete("filter_weibukeча", r"微不可察|不易察觉")
        # 7. 破折号 → 逗号
        add_replace("replace_dash", r"——", "，")
        # 8. 低吼、幼兽、凶残的、肉刃、四肢百骸
        add_delete("filter_violent", r"低吼|幼兽|凶残的|肉刃|四肢百骸")
        # 9. 不容置疑的、不容置喙的
        add_delete("filter_burongzhiyi", r"不容置疑的|不容置喙的")
        # 10. 我的小
        add_delete("filter_wodexiao", r"我的小")
        # 11. 胸腔震动、胸腔振动
        add_delete("filter_xiongqiang", r"胸腔震动|胸腔振动")

        # 12. 自定义过滤（纯文本，每条一个词/短语）
        custom_filters: list[str] = cfg.get("custom_filters", [])
        for raw in custom_filters:
            term = raw.strip()
            if term:
                rules.append((re.compile(re.escape(term)), ""))

        # 13. 自定义替换（格式：原文||替换文）
        custom_replacements: list[str] = cfg.get("custom_replacements", [])
        for raw in custom_replacements:
            raw = raw.strip()
            if "||" in raw:
                src, dst = raw.split("||", 1)
                src = src.strip()
                dst = dst.strip()
                if src:
                    rules.append((re.compile(re.escape(src)), dst))

        return rules

    # ------------------------------------------------------------------
    # 对单段文本应用所有规则
    # ------------------------------------------------------------------

    def _apply_rules(self, text: str, rules: list[tuple[re.Pattern, str]]) -> str:
        for pattern, repl in rules:
            text = pattern.sub(repl, text)
        return text

    # ------------------------------------------------------------------
    # 钩子 1：LLM 返回后，过滤响应文本
    # ------------------------------------------------------------------

    @filter.on_llm_response()
    async def filter_response(
        self, event: AstrMessageEvent, response: LLMResponse
    ) -> None:
        rules = self._build_rules()
        if not rules:
            return

        original = response.completion_text
        filtered = self._apply_rules(original, rules)

        if filtered != original:
            response.completion_text = filtered
            logger.debug(
                f"[八股文过滤] 过滤前: {original!r}\n"
                f"[八股文过滤] 过滤后: {filtered!r}"
            )

    # ------------------------------------------------------------------
    # 钩子 2：下次请求前，清理历史中残留的原始内容
    # ------------------------------------------------------------------

    @filter.on_llm_request()
    async def clean_history(self, event: AstrMessageEvent, req) -> None:
        rules = self._build_rules()
        if not rules:
            return

        await self._clean_db_history(event, rules)
        self._clean_req_memory(req, rules)

    async def _clean_db_history(
        self,
        event: AstrMessageEvent,
        rules: list[tuple[re.Pattern, str]],
    ) -> None:
        """清理数据库中持久化的对话历史。"""
        try:
            umo = event.unified_msg_origin
            conv_mgr = self.context.conversation_manager
            conv_id = await conv_mgr.get_curr_conversation_id(umo)
            if not conv_id:
                return

            conversation = await conv_mgr.get_conversation(umo, conv_id)
            if not conversation or not conversation.history:
                return

            history: list[dict] = json.loads(conversation.history)
            changed = False

            for msg in history:
                # 只处理助手消息；工具调用消息保持原样
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content")
                if not isinstance(content, str):
                    continue
                new_content = self._apply_rules(content, rules)
                if new_content != content:
                    msg["content"] = new_content
                    changed = True

            if changed:
                await conv_mgr.update_conversation(
                    unified_msg_origin=umo,
                    conversation_id=conv_id,
                    history=json.dumps(history, ensure_ascii=False),
                )
                logger.debug("[八股文过滤] 数据库历史已清理。")

        except Exception as e:
            logger.error(f"[八股文过滤] 清理数据库历史失败: {e}")

    def _clean_req_memory(
        self,
        req,
        rules: list[tuple[re.Pattern, str]],
    ) -> None:
        """清理本次请求对象内存中的对话历史。"""
        try:
            for attr_name in dir(req):
                if attr_name.startswith("__"):
                    continue
                attr_val = getattr(req, attr_name, None)
                if not isinstance(attr_val, list) or not attr_val:
                    continue

                new_val = []
                changed = False
                for item in attr_val:
                    if isinstance(item, dict) and item.get("role") == "assistant":
                        content = item.get("content")
                        if isinstance(content, str):
                            new_content = self._apply_rules(content, rules)
                            if new_content != content:
                                item = {**item, "content": new_content}
                                changed = True
                    else:
                        # 对象类型（非 dict）
                        content = getattr(item, "content", None)
                        role = getattr(item, "role", None)
                        if role == "assistant" and isinstance(content, str):
                            new_content = self._apply_rules(content, rules)
                            if new_content != content:
                                try:
                                    item.content = new_content
                                except AttributeError:
                                    pass
                                changed = True
                    new_val.append(item)

                if changed:
                    setattr(req, attr_name, new_val)
                    logger.debug(
                        f"[八股文过滤] 请求内存 '{attr_name}' 已清理。"
                    )
        except Exception as e:
            logger.error(f"[八股文过滤] 清理请求内存失败: {e}")
