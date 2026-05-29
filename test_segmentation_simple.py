#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的分段逻辑测试

直接测试分段算法，不依赖完整服务
"""

def test_nlp_segment(subtitles, min_duration, max_duration, prefer_sentence_boundary):
    """简化版的NLP分段算法"""

    segments = []
    current_segment = None
    subtitle_indices = []

    # 句子结束标点
    sentence_endings = {'。', '！', '？', '.', '!', '?', ';', '；'}

    for i, subtitle in enumerate(subtitles):
        text = subtitle.get('text', '').strip()
        if not text:
            continue

        start = subtitle.get('start', 0.0)
        end = subtitle.get('end', 0.0)

        # 初始化第一个分段
        if current_segment is None:
            current_segment = {
                'start': start,
                'end': end,
                'text': text,
                'subtitle_indices': [i]
            }
            continue

        # 计算当前分段时长
        current_duration = end - current_segment['start']

        # 检查是否句子结束
        is_sentence_end = any(text.endswith(p) for p in sentence_endings)

        # 分段条件
        should_segment = False

        # 1. 超过最大时长 → 强制分段
        if current_duration > max_duration:
            should_segment = True

        # 2. 句子结束 + 达到最小时长
        elif is_sentence_end and current_duration >= min_duration:
            if prefer_sentence_boundary:
                should_segment = True

        # 3. 达到最小时长（非句子边界优先模式）
        elif not prefer_sentence_boundary and current_duration >= min_duration:
            should_segment = True

        if should_segment:
            # 保存当前分段
            current_segment['duration'] = current_segment['end'] - current_segment['start']
            segments.append(current_segment)

            # 开始新分段
            current_segment = {
                'start': start,
                'end': end,
                'text': text,
                'subtitle_indices': [i]
            }
        else:
            # 继续累积
            current_segment['end'] = end
            current_segment['text'] += ' ' + text
            current_segment['subtitle_indices'].append(i)

    # 保存最后一个分段
    if current_segment:
        current_segment['duration'] = current_segment['end'] - current_segment['start']
        segments.append(current_segment)

    return segments


# 测试数据
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

print("=" * 70)
print("测试1: 默认配置 (min=3.0s, max=10.0s, prefer_sentence=True)")
print("=" * 70)

segments1 = test_nlp_segment(subtitles, 3.0, 10.0, True)
print(f"生成 {len(segments1)} 个镜头:\n")
for i, seg in enumerate(segments1, 1):
    print(f"镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s)")
    print(f"  字幕索引: {seg['subtitle_indices']}")
    print(f"  内容: {seg['text']}")
    print()

print("=" * 70)
print("测试2: 快节奏配置 (min=2.0s, max=5.0s, prefer_sentence=False)")
print("=" * 70)

segments2 = test_nlp_segment(subtitles, 2.0, 5.0, False)
print(f"生成 {len(segments2)} 个镜头:\n")
for i, seg in enumerate(segments2, 1):
    print(f"镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s)")
    print(f"  字幕索引: {seg['subtitle_indices']}")
    print(f"  内容: {seg['text']}")
    print()

print("=" * 70)
print("测试3: 慢节奏配置 (min=5.0s, max=15.0s, prefer_sentence=True)")
print("=" * 70)

segments3 = test_nlp_segment(subtitles, 5.0, 15.0, True)
print(f"生成 {len(segments3)} 个镜头:\n")
for i, seg in enumerate(segments3, 1):
    print(f"镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s)")
    print(f"  字幕索引: {seg['subtitle_indices']}")
    print(f"  内容: {seg['text']}")
    print()

print("=" * 70)
print("测试结果对比")
print("=" * 70)
print(f"默认配置 (3-10秒, 优先句子):  {len(segments1)} 个镜头")
print(f"快节奏 (2-5秒, 不优先句子):   {len(segments2)} 个镜头")
print(f"慢节奏 (5-15秒, 优先句子):    {len(segments3)} 个镜头")
print()

if len(segments1) == len(segments2) == len(segments3):
    print("⚠️  警告: 所有配置生成的镜头数量相同，配置可能未生效！")
else:
    print("✅ 配置正常工作，不同配置生成不同数量的镜头")
