#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕标点符号自动添加工具

为ASR生成的无标点字幕自动添加标点符号
"""

import re
from typing import List, Dict


class PunctuationAdder:
    """标点符号自动添加器"""

    def __init__(self):
        """初始化"""
        # 句子结束标志词
        self.sentence_end_words = [
            '吗', '呢', '吧', '啊', '呀', '哇', '哦', '嘛',
            '了', '的', '着', '过', '得',
        ]

        # 疑问词
        self.question_words = [
            '什么', '怎么', '为什么', '哪里', '谁', '哪个', '多少',
            '几', '如何', '是否', '能否', '可以吗', '好吗', '行吗'
        ]

        # 逗号标志词
        self.comma_words = [
            '但是', '然后', '接着', '所以', '因此', '而且', '并且',
            '或者', '还是', '不过', '可是', '虽然', '如果', '假如'
        ]

    def add_punctuation(self, subtitles: List[Dict]) -> List[Dict]:
        """
        为字幕添加标点符号

        Args:
            subtitles: 字幕列表，每项包含 start, end, text

        Returns:
            添加标点后的字幕列表
        """
        if not subtitles:
            return subtitles

        result = []

        for i, subtitle in enumerate(subtitles):
            text = subtitle.get('text', '').strip()

            if not text:
                result.append(subtitle)
                continue

            # 如果已经有标点，跳过
            if self._has_punctuation(text):
                result.append(subtitle)
                continue

            # 添加标点
            punctuated_text = self._add_punctuation_to_text(text, i, subtitles)

            result.append({
                'start': subtitle['start'],
                'end': subtitle['end'],
                'text': punctuated_text
            })

        return result

    def _has_punctuation(self, text: str) -> bool:
        """检查文本是否已有标点"""
        punctuation = '。！？，、；：""''（）《》【】…—'
        return any(p in text for p in punctuation)

    def _add_punctuation_to_text(self, text: str, index: int, all_subtitles: List[Dict]) -> str:
        """
        为单条字幕添加标点

        Args:
            text: 字幕文本
            index: 当前字幕索引
            all_subtitles: 所有字幕列表

        Returns:
            添加标点后的文本
        """
        # 检查是否是疑问句
        if self._is_question(text):
            return text + '？'

        # 检查是否是最后一条字幕
        is_last = (index == len(all_subtitles) - 1)

        # 检查下一条字幕是否以连接词开头
        has_connector_next = False
        if not is_last:
            next_text = all_subtitles[index + 1].get('text', '').strip()
            has_connector_next = any(next_text.startswith(word) for word in self.comma_words)

        # 检查当前字幕是否以句子结束词结尾
        ends_with_sentence_word = any(text.endswith(word) for word in self.sentence_end_words)

        # 决定标点
        if is_last:
            # 最后一条，加句号
            return text + '。'
        elif has_connector_next:
            # 下一条是连接词，加逗号
            return text + '，'
        elif ends_with_sentence_word and len(text) > 5:
            # 以句子结束词结尾且文本较长，加句号
            return text + '。'
        else:
            # 默认加逗号（表示未完成）
            return text + '，'

    def _is_question(self, text: str) -> bool:
        """判断是否是疑问句"""
        # 检查是否包含疑问词
        if any(word in text for word in self.question_words):
            return True

        # 检查是否以疑问语气词结尾
        question_endings = ['吗', '呢', '吧']
        if any(text.endswith(word) for word in question_endings):
            return True

        return False


def add_punctuation_to_subtitles(subtitles: List[Dict]) -> List[Dict]:
    """
    便捷函数：为字幕添加标点

    Args:
        subtitles: 字幕列表

    Returns:
        添加标点后的字幕列表
    """
    adder = PunctuationAdder()
    return adder.add_punctuation(subtitles)


# 测试代码
if __name__ == '__main__':
    # 测试数据
    test_subtitles = [
        {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
        {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史'},
        {'start': 4.0, 'end': 6.0, 'text': '从1950年代开始'},
        {'start': 6.0, 'end': 8.0, 'text': '科学家们就在研究'},
        {'start': 8.0, 'end': 10.0, 'text': '如何让机器模拟人类智能'},
        {'start': 10.0, 'end': 12.0, 'text': '你知道AI是什么吗'},
        {'start': 12.0, 'end': 14.0, 'text': '经过几十年的发展'},
        {'start': 14.0, 'end': 16.0, 'text': 'AI技术已经取得了巨大进步'},
    ]

    print("原始字幕:")
    for sub in test_subtitles:
        print(f"  {sub['text']}")

    print("\n添加标点后:")
    result = add_punctuation_to_subtitles(test_subtitles)
    for sub in result:
        print(f"  {sub['text']}")
