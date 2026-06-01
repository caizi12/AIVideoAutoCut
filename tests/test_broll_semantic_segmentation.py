#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补画面语义分段测试。"""

import unittest

from backend.services.broll_service import BrollService


class TestBrollSemanticSegmentation(unittest.TestCase):
    """验证字幕会按完整语义合并为补画面镜头。"""

    def setUp(self):
        self.service = BrollService(None)

    def test_sentence_boundary_keeps_ending_subtitle_in_same_segment(self):
        subtitles = [
            {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
            {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史。'},
            {'start': 4.0, 'end': 6.0, 'text': '接下来看看实际应用。'},
        ]

        segments = self.service._nlp_segment_subtitles(subtitles, {
            'min_shot_duration': 3.0,
            'max_shot_duration': 10.0,
            'prefer_sentence_boundary': True
        })

        self.assertGreaterEqual(len(segments), 1)
        self.assertEqual(segments[0]['subtitle_indices'], [0, 1])
        self.assertIn('人工智能的发展历史。', segments[0]['text'])

    def test_duration_config_changes_segment_density_without_punctuation(self):
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

        fast = self.service._nlp_segment_subtitles(subtitles, {
            'min_shot_duration': 2.0,
            'max_shot_duration': 5.0,
            'prefer_sentence_boundary': False
        })
        slow = self.service._nlp_segment_subtitles(subtitles, {
            'min_shot_duration': 5.0,
            'max_shot_duration': 15.0,
            'prefer_sentence_boundary': True
        })

        self.assertGreater(len(fast), len(slow))

    def test_build_shots_uses_readable_search_keywords(self):
        subtitles = [
            {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
            {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史。'},
        ]

        shots = self.service._build_shots(subtitles, {
            'min_shot_duration': 3.0,
            'max_shot_duration': 10.0,
            'prefer_sentence_boundary': True
        })

        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]['subtitle_indices'], [0, 1])
        self.assertNotIn('天我们来', shots[0]['keywords'])
        self.assertTrue(shots[0]['search_queries'])


if __name__ == '__main__':
    unittest.main()
