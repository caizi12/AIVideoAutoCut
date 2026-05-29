#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕分段诊断脚本

用于诊断为什么不同配置生成相同数量的镜头
"""

import re
from typing import List, Dict

def extract_keywords(text: str) -> List[str]:
    """简化版关键词提取"""
    # 移除标点
    text = re.sub(r'[，。！？、；：""''（）《》【】\s]+', ' ', text)
    # 分词（简单按空格分）
    words = text.split()
    # 过滤短词
    keywords = [w for w in words if len(w) >= 2]
    return keywords[:6]

def is_sentence_end(text: str) -> bool:
    """检测句子结束"""
    text = text.strip()
    return bool(re.search(r'[。！？\.!?;；]$', text))

def is_topic_change(old_keywords: List[str], new_keywords: List[str]) -> bool:
    """检测主题变化"""
    if not old_keywords or not new_keywords:
        return False

    old_set = set(old_keywords)
    new_set = set(new_keywords)
    overlap = old_set & new_set

    if not old_set:
        return False

    overlap_ratio = len(overlap) / len(old_set)
    return overlap_ratio < 0.3  # 重叠度低于30%认为主题变化

def diagnose_subtitles(subtitles: List[Dict], min_duration: float, max_duration: float, prefer_sentence: bool):
    """诊断字幕分段"""

    print(f"\n{'='*70}")
    print(f"配置: min={min_duration}s, max={max_duration}s, prefer_sentence={prefer_sentence}")
    print(f"{'='*70}\n")

    segments = []
    current_segment = None

    for i, subtitle in enumerate(subtitles):
        text = subtitle.get('text', '').strip()
        if not text:
            continue

        start = float(subtitle.get('start', 0.0))
        end = float(subtitle.get('end', 0.0))

        # 检测句子结束
        is_sent_end = is_sentence_end(text) if prefer_sentence else False

        # 提取关键词
        keywords = extract_keywords(text)

        # 检测主题变化
        is_topic_chg = False
        if current_segment:
            is_topic_chg = is_topic_change(current_segment.get('keywords', []), keywords)

        # 计算时长
        if current_segment:
            duration = end - current_segment['start']
        else:
            duration = 0

        # 决定是否分段
        should_split = False
        split_reason = ""

        if current_segment is None:
            should_split = False
        elif duration >= max_duration:
            should_split = True
            split_reason = f"超过最大时长({duration:.1f}s >= {max_duration}s)"
        elif is_topic_chg and duration >= min_duration:
            should_split = True
            split_reason = f"主题变化且达到最小时长({duration:.1f}s >= {min_duration}s)"
        elif is_sent_end and duration >= min_duration:
            should_split = True
            split_reason = f"句子结束且达到最小时长({duration:.1f}s >= {min_duration}s)"

        # 打印诊断信息
        print(f"字幕{i+1}: {start:.1f}-{end:.1f}s | {text}")
        print(f"  关键词: {keywords}")
        print(f"  句子结束: {is_sent_end}")
        if current_segment:
            print(f"  主题变化: {is_topic_chg}")
            print(f"  当前段落时长: {duration:.1f}s")

        if should_split:
            print(f"  ✂️  分段! 原因: {split_reason}")
            segments.append(current_segment)
            current_segment = {
                'start': start,
                'end': end,
                'text': text,
                'keywords': keywords,
                'subtitle_indices': [i]
            }
        else:
            if current_segment is None:
                print(f"  🆕 开始第一个段落")
                current_segment = {
                    'start': start,
                    'end': end,
                    'text': text,
                    'keywords': keywords,
                    'subtitle_indices': [i]
                }
            else:
                print(f"  ➕ 合并到当前段落")
                current_segment['end'] = end
                current_segment['text'] += ' ' + text
                current_segment['keywords'] = list(set(current_segment['keywords'] + keywords))[:6]
                current_segment['subtitle_indices'].append(i)

        print()

    # 保存最后一个段落
    if current_segment:
        segments.append(current_segment)

    print(f"{'='*70}")
    print(f"最终生成 {len(segments)} 个镜头:")
    print(f"{'='*70}\n")

    for i, seg in enumerate(segments, 1):
        duration = seg['end'] - seg['start']
        print(f"镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({duration:.1f}s)")
        print(f"  字幕索引: {seg['subtitle_indices']}")
        print(f"  内容: {seg['text'][:50]}...")
        print()

    return segments

# 示例：请替换为您的实际字幕数据
subtitles = [
    {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
    {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史。'},
    {'start': 4.0, 'end': 6.0, 'text': '从1950年代开始'},
    {'start': 6.0, 'end': 8.0, 'text': '科学家们就在研究'},
    {'start': 8.0, 'end': 10.0, 'text': '如何让机器模拟人类智能。'},
    {'start': 10.0, 'end': 12.0, 'text': '经过几十年的发展'},
    {'start': 12.0, 'end': 14.0, 'text': 'AI技术已经取得了巨大进步。'},
    {'start': 14.0, 'end': 16.0, 'text': '现在我们来看看具体应用。'},
]

print("\n" + "="*70)
print("字幕分段诊断工具")
print("="*70)
print("\n请将您的实际字幕数据替换到脚本中的 subtitles 变量")
print("然后运行此脚本查看详细的分段过程\n")

# 测试不同配置
configs = [
    {'name': '默认', 'min': 3.0, 'max': 10.0, 'prefer': True},
    {'name': '快节奏', 'min': 2.0, 'max': 5.0, 'prefer': False},
    {'name': '慢节奏', 'min': 5.0, 'max': 15.0, 'prefer': True},
]

results = []
for config in configs:
    segments = diagnose_subtitles(
        subtitles,
        config['min'],
        config['max'],
        config['prefer']
    )
    results.append((config['name'], len(segments)))

print("\n" + "="*70)
print("结果对比")
print("="*70)
for name, count in results:
    print(f"{name}: {count} 个镜头")

if len(set(count for _, count in results)) == 1:
    print("\n⚠️  所有配置生成相同数量的镜头！")
    print("\n可能的原因:")
    print("1. 字幕没有句子结束标点（。！？）")
    print("2. 所有字幕主题相同，关键词重叠度高")
    print("3. 字幕总时长太短")
    print("\n建议:")
    print("- 检查字幕是否有标点符号")
    print("- 尝试禁用'优先句子边界'")
    print("- 调整最大时长，强制分段")
else:
    print("\n✅ 不同配置生成不同数量的镜头，配置正常工作")
