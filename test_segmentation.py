#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分段配置测试脚本

用于测试分段配置是否正确工作
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.broll_service import BrollService
from backend.database.db_manager import DatabaseManager

def test_segmentation():
    """测试分段配置"""

    # 模拟字幕数据
    subtitles = [
        {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
        {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史'},
        {'start': 4.0, 'end': 6.0, 'text': '从1950年代开始'},
        {'start': 6.0, 'end': 8.0, 'text': '科学家们就在研究'},
        {'start': 8.0, 'end': 10.0, 'text': '如何让机器模拟人类智能'},
        {'start': 10.0, 'end': 12.0, 'text': '经过几十年的发展'},
        {'start': 12.0, 'end': 14.0, 'text': 'AI技术已经取得了巨大进步'},
        {'start': 14.0, 'end': 16.0, 'text': '现在我们来看看具体应用'},
    ]

    # 初始化服务
    db_manager = DatabaseManager()
    service = BrollService(db_manager)

    print("=" * 60)
    print("测试1: 默认配置 (3-10秒)")
    print("=" * 60)

    data1 = {
        'min_shot_duration': 3.0,
        'max_shot_duration': 10.0,
        'prefer_sentence_boundary': True
    }

    segments1 = service._nlp_segment_subtitles(subtitles, data1)
    print(f"生成 {len(segments1)} 个镜头:")
    for i, seg in enumerate(segments1, 1):
        print(f"  镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s) - {seg['text']}")

    print("\n" + "=" * 60)
    print("测试2: 快节奏配置 (2-5秒)")
    print("=" * 60)

    data2 = {
        'min_shot_duration': 2.0,
        'max_shot_duration': 5.0,
        'prefer_sentence_boundary': False
    }

    segments2 = service._nlp_segment_subtitles(subtitles, data2)
    print(f"生成 {len(segments2)} 个镜头:")
    for i, seg in enumerate(segments2, 1):
        print(f"  镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s) - {seg['text']}")

    print("\n" + "=" * 60)
    print("测试3: 慢节奏配置 (5-15秒)")
    print("=" * 60)

    data3 = {
        'min_shot_duration': 5.0,
        'max_shot_duration': 15.0,
        'prefer_sentence_boundary': True
    }

    segments3 = service._nlp_segment_subtitles(subtitles, data3)
    print(f"生成 {len(segments3)} 个镜头:")
    for i, seg in enumerate(segments3, 1):
        print(f"  镜头{i}: {seg['start']:.1f}-{seg['end']:.1f}s ({seg['duration']:.1f}s) - {seg['text']}")

    print("\n" + "=" * 60)
    print("测试结果对比")
    print("=" * 60)
    print(f"默认配置 (3-10秒): {len(segments1)} 个镜头")
    print(f"快节奏 (2-5秒):   {len(segments2)} 个镜头")
    print(f"慢节奏 (5-15秒):  {len(segments3)} 个镜头")

    if len(segments1) == len(segments2) == len(segments3):
        print("\n⚠️  警告: 所有配置生成的镜头数量相同，配置可能未生效！")
    else:
        print("\n✅ 配置正常工作，不同配置生成不同数量的镜头")

if __name__ == '__main__':
    test_segmentation()
