# -*- coding: utf-8 -*-
# @Time    : 12/6/22 12:02 PM
# @FileName: chat.py
# @Software: PyCharm
# @Github    ：sudoskys

import json
import os
import random

import openai_async
from .web import webEnhance

# import loguru
# import jiagu


# 基于 Completion 上层
from ..resouce import Completion
from ..utils.Talk import Talk

from ..utils.data import MsgFlow


# 聊天类


class Chatbot(object):
    def __init__(self, api_key: str = None, conversation_id: int = 1, token_limit: int = 3505,
                 restart_sequ: str = "\nSomeone:",
                 start_sequ: str = "\nReply:",
                 call_func=None):
        """
        chatGPT 的实现由上下文实现，所以我会做一个存储器来获得上下文
        :param api_key:
        :param conversation_id: 独立ID,每个场景需要独一个
        :param call_func: 回调
        """
        if api_key is None:
            api_key = openai_async.api_key
        if isinstance(api_key, list):
            api_key: list
            if not api_key:
                raise RuntimeError("NO KEY")
            api_key = random.choice(api_key)
            api_key: str
        self.__api_key = api_key
        if not api_key:
            raise RuntimeError("NO KEY")
        self.conversation_id = str(conversation_id)
        self._MsgFlow = MsgFlow(uid=self.conversation_id)
        self._start_sequence = start_sequ
        self._restart_sequence = restart_sequ
        # 防止木头
        if not self._start_sequence.strip().endswith(":"):
            self._start_sequence = self._start_sequence + ":"
        if not self._restart_sequence.strip().endswith(":"):
            self._restart_sequence = self._restart_sequence + ":"
        self.__call_func = call_func
        self.__token_limit = token_limit

    def reset_chat(self):
        # Forgets conversation
        return self._MsgFlow.forget()

    def record_ai(self, prompt, response):
        REPLY = []
        Choice = response.get("choices")
        if Choice:
            for item in Choice:
                _text = item.get("text")
                REPLY.append(_text)
        if not REPLY:
            REPLY = [""]
        # 构建一轮对话场所
        _msg = {"weight": 0, "ask": f"{self._restart_sequence}{prompt}", "reply": f"{self._start_sequence}{REPLY[0]}"}
        # 存储成对的对话
        self._MsgFlow.saveMsg(msg=_msg)
        # 拒绝分条存储
        # self._MsgFlow.save(prompt=prompt, role=self._restart_sequence)
        # self._MsgFlow.save(prompt=REPLY[0], role=self._start_sequence)
        return REPLY

    @staticmethod
    def random_string(length):
        """
        生成随机字符串
        :param length:
        :return:
        """
        import string
        import random
        all_chars = string.ascii_letters + string.digits
        result = ''
        for i in range(length):
            result += random.choice(all_chars)
        return result

    # _prompt = random_string(3700)

    def get_hash(self):
        import hashlib
        my_string = str(self.conversation_id)
        # 使用 hashlib 模块中的 sha256 算法创建一个散列对象
        hash_object = hashlib.sha256(my_string.encode())
        return hash_object.hexdigest()

    @staticmethod
    def zip_str(_item):
        # 读取字典
        path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), ".", "vocab.json")
        )
        with open(path, encoding="utf8") as f:
            target = json.loads(f.read())
        # 遍历字典键值对
        for key, value in target.items():
            # 使用 str.replace() 方法替换字符串中的键
            _item = _item.replace(key, value)
        return _item

    def convert_msgflow_to_list(self, msg_list: list) -> list:
        """
        提取以单条 msgflow 组成的列表的回复。
        :param msg_list:
        :return:
        """
        _result = []
        for ir in msg_list:
            ask, reply = self._MsgFlow.get_content(ir, sign=True)
            _result.append(ask)
            _result.append(reply)
        return _result

    def Summer(self,
               prompt: str,
               memory: list,
               attention: int = 4,
               start_token: int = 0,
               extra_token: int = 0
               ) -> list:
        """
        以单条消息为对象处理达标并排序时间轴
        数据清洗采用权重设定，而不操作元素删减
        :param attention: 注意力
        :param prompt: 记忆提示
        :param extra_token: 记忆的限制
        :param memory: 记忆桶
        :return: 新的列表
        """
        # 单条消息的内容 {"ask": self._restart_sequence+prompt, "reply": self._start_sequence+REPLY[0]}
        _create_token = self.__token_limit - extra_token
        # 入口检查
        if len(memory) - attention < 0:
            return self.convert_msgflow_to_list(memory)
        # 组建
        for i in range(len(memory) - attention, len(memory)):
            memory[i]["content"]["weight"] = 1000
        # 筛选标准发言机器
        _index = []
        for i in range(0, len(memory) - attention):
            ask, reply = self._MsgFlow.get_content(memory[i], sign=False)
            if len(ask) < 1 or len(reply) < 1:
                memory[i]["content"]["weight"] = 0
        # 相似度检索
        for i in range(0, len(memory) - attention):
            ask, reply = self._MsgFlow.get_content(memory[i], sign=False)
            _diff1 = Talk.cosion_sismilarity(pre=prompt, aft=ask)
            _diff2 = Talk.cosion_sismilarity(pre=prompt, aft=reply)
            _diff = (_diff1 + _diff2) / 2
            memory[i]["content"]["weight"] = _diff * 100 + 30  # 相比于关键词检索有 2个优先级
        # 主题检索
        _key = Talk.tfidf_keywords(prompt, topK=3)
        for i in range(0, len(memory) - attention):
            ask, reply = self._MsgFlow.get_content(memory[i], sign=False)
            for ir in _key:
                if ir in f"{ask}{reply}":
                    memory[i]["content"]["weight"] = 90
        # 进行筛选，计算限制
        _msg_flow = []
        _msg_return = []
        _now_token = start_token
        memory = sorted(memory, key=lambda x: x['time'], reverse=True)
        for i in range(0, len(memory)):
            if memory[i]["content"]["weight"] > 80:
                ask, reply = self._MsgFlow.get_content(memory[i], sign=True)
                _now_token += Talk.tokenizer(f"{ask}{reply}")
                if _now_token > _create_token:
                    # print(f"{ask}-> {_now_token}")
                    break
                _msg_flow.append(memory[i])
        _msg_flow = sorted(_msg_flow, key=lambda x: x['time'], reverse=False)
        # print(_msg_flow)
        # print(_msg_flow)
        _msg_flow_list = self.convert_msgflow_to_list(_msg_flow)
        _msg_return.extend(_msg_flow_list)
        """
                if _out:
            for i in range(len(_Final)):
                if Talk.tokenizer(_Final[i]) > 240:
                    if Talk.get_language(_Final[i]) == "chinese":
                        _sum = Talk.tfidf_summarization(sentence=_Final[i], ratio=0.3)
                        if len(_sum) > 7:
                            _Final[i] = _sum
        """
        return _msg_flow_list

    async def get_chat_response(self, prompt: str, max_tokens: int = 200, model: str = "text-davinci-003",
                                character: list = None, head: str = None, role: str = "",
                                web_enhance_server: list = None) -> dict:
        """
        异步的，得到对话上下文
        :param web_enhance_server: ["https://www.exp.com/search?q={}"] 格式如此
        :param role:
        :param head: 预设技巧
        :param max_tokens: 限制返回字符数量
        :param model: 模型选择
        :param prompt: 提示词
        :param character: 性格提示词，列表字符串
        :return:
        """
        # 预设
        if head is None:
            head = f"{self._restart_sequence}让我们谈谈吧。\n"
        if character is None:
            character = ["helpful", "creative", "clever", "friendly", "lovely", "talkative"]
        _character = ",".join(character)
        _role = f"我代表 [{self._start_sequence}] following.\nI am a {_character} Ai assistant.\n"
        if role:
            if len(f"{role}") > 4:
                _role = f"I am [{self._start_sequence}] following.\n我认为:{role}.\n"
        _header = f"{_role}{head}"
        # 构建主体
        _prompt_s = [f"{self._restart_sequence}{prompt}."]
        _prompt_memory = self._MsgFlow.read()
        # 占位限制
        _extra_token = int(
            len(_prompt_memory) +
            Talk.tokenizer(self._start_sequence) +
            max_tokens +
            Talk.tokenizer(_header + _prompt_s[0]))
        # Web 支持
        _prompt_list = []
        _appenx = self.Prehance(prompt=prompt, web_enhance_server=web_enhance_server)
        start_token = int(Talk.tokenizer(_appenx))
        _prompt_list.append(_appenx)
        _prompt_apple = self.Summer(prompt=prompt,
                                    start_token=start_token,
                                    memory=_prompt_memory,
                                    extra_token=_extra_token)
        _prompt_list.extend(_prompt_apple)
        _prompt_list.extend(_prompt_s)
        # 拼接提示词汇
        _prompt = '\n'.join(_prompt_list) + f"\n{self._start_sequence}"
        # 重切割
        _limit = self.__token_limit - max_tokens - Talk.tokenizer(_header)
        _mk = _limit if _limit > 0 else 0
        while Talk.tokenizer(_prompt) > _mk:
            _prompt = _prompt[1:]
        _prompt = _header + _prompt
        # 响应
        response = await Completion(api_key=self.__api_key, call_func=self.__call_func).create(
            model=model,
            prompt=_prompt,
            temperature=0.9,
            max_tokens=max_tokens,
            top_p=1,
            n=1,
            frequency_penalty=0,
            presence_penalty=0.5,
            user=str(self.get_hash()),
            stop=[f"{self._start_sequence}:", f"{self._restart_sequence}:"],
        )
        self.record_ai(prompt=prompt, response=response)
        return response

    @staticmethod
    def str_prompt(prompt: str) -> list:
        range_list = prompt.split("\n")

        # 如果当前项不包含 `:`，则将其并入前一项中
        result = [range_list[i] + range_list[i + 1] if ":" not in range_list[i] else range_list[i] for i in
                  range(len(range_list))]
        # 使用列表推导式过滤掉空白项
        filtered_result = [x for x in result if x != ""]
        # 输出处理后的结果
        return filtered_result

    def Prehance(self, prompt, web_enhance_server):
        _appenx = ""
        # 提取内容
        re = []
        if "time" in prompt or "时间" in prompt or "几点了" in prompt:
            from datetime import datetime
            currentDateAndTime = datetime.now()
            re.append(f"Current  time {currentDateAndTime}")
        if web_enhance_server:
            if len(prompt) < 80 and (
                    "知道" in prompt or "谈谈" in prompt or "介绍" in prompt):  # or "?" in prompt or "？" in prompt):
                try:
                    re = webEnhance(server=web_enhance_server).get_content(prompt=prompt)
                except Exception as e:
                    re = []
        _appenx = "".join(re)
        return _appenx
