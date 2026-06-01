#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补画面素材搜索策略测试。"""

import unittest

from backend.services.broll_service import BrollService


class TestBrollCandidateSearchPolicy(unittest.TestCase):
    """验证候选数量、替换搜索和安全过滤策略。"""

    def setUp(self):
        self.service = BrollService(None)

    def test_default_candidate_count_is_three(self):
        self.assertEqual(self.service.DEFAULT_CONFIG['max_candidates_per_shot'], 3)

    def test_resolve_search_targets_accepts_multiple_shot_ids(self):
        shots = [
            {'shot_id': 's001'},
            {'shot_id': 's002'},
            {'shot_id': 's003'},
        ]

        targets = self.service._resolve_search_targets({'shot_ids': ['s001', 's003', 'missing']}, shots)

        self.assertEqual(targets, ['s001', 's003'])

    def test_news_military_query_gets_safe_news_hint(self):
        shot = {
            'subtitle_text': '国防部门举行发布会介绍军事演习安排',
            'keywords': ['国防', '军事', '发布会'],
            'search_queries': ['cinematic background']
        }

        queries = self.service._build_candidate_queries(shot)

        self.assertTrue(any('military' in query or 'defense' in query for query in queries[:3]))
        self.assertIn('news footage', queries)

    def test_violent_candidate_is_filtered(self):
        unsafe = {
            'title': 'bloody gun violence scene',
            'source_id': 'bad-video',
            'query': 'news footage'
        }
        safe = {
            'title': 'military parade press conference',
            'source_id': 'safe-video',
            'query': 'news footage military'
        }

        self.assertFalse(self.service._is_safe_candidate(unsafe))
        self.assertTrue(self.service._is_safe_candidate(safe))

    def test_search_candidates_returns_at_most_three_safe_items(self):
        class FakeProvider:
            provider_id = 'fake'

            def search(self, query, orientation='landscape', per_page=3):
                candidates = [
                    {'candidate_id': 'bad', 'provider': 'fake', 'source_id': 'bad', 'title': 'blood scene', 'download_url': 'x'}
                ]
                candidates.extend({
                    'candidate_id': f'good-{index}',
                    'provider': 'fake',
                    'source_id': f'good-{index}',
                    'title': 'press conference',
                    'download_url': 'x',
                    'width': 1920,
                    'height': 1080,
                    'duration': 10
                } for index in range(4))
                return candidates

        shot = {
            'duration': 5,
            'subtitle_text': '国防部门举行新闻发布会',
            'keywords': ['国防', '新闻'],
            'search_queries': ['news footage']
        }

        candidates = self.service._search_candidates_for_shot(shot, [FakeProvider()], 'landscape', 3)

        self.assertEqual(len(candidates), 3)
        self.assertTrue(all(candidate['candidate_id'] != 'bad' for candidate in candidates))

    def test_search_candidates_are_filtered_and_capped(self):
        class FakeProvider:
            provider_id = 'fake'

            def search(self, query, orientation='landscape', per_page=3):
                return [
                    {'candidate_id': 'unsafe', 'provider': 'fake', 'source_id': 'unsafe', 'title': 'blood violence', 'download_url': 'x'},
                    {'candidate_id': 'safe1', 'provider': 'fake', 'source_id': 'safe1', 'title': 'press conference', 'download_url': 'x', 'width': 1920, 'height': 1080, 'duration': 10, 'query': query},
                    {'candidate_id': 'safe2', 'provider': 'fake', 'source_id': 'safe2', 'title': 'military parade', 'download_url': 'x', 'width': 1280, 'height': 720, 'duration': 8, 'query': query},
                    {'candidate_id': 'safe3', 'provider': 'fake', 'source_id': 'safe3', 'title': 'government meeting', 'download_url': 'x', 'width': 1280, 'height': 720, 'duration': 8, 'query': query},
                    {'candidate_id': 'safe4', 'provider': 'fake', 'source_id': 'safe4', 'title': 'news footage', 'download_url': 'x', 'width': 1280, 'height': 720, 'duration': 8, 'query': query},
                ]

        shot = {
            'duration': 5,
            'subtitle_text': '国防部门举行发布会',
            'keywords': ['国防', '发布会'],
            'search_queries': []
        }

        candidates = self.service._search_candidates_for_shot(shot, [FakeProvider()], 'landscape', 3)

        self.assertLessEqual(len(candidates), 3)
        self.assertTrue(all('unsafe' not in item['candidate_id'] for item in candidates))

    def test_resolve_search_targets_supports_multiple_shots(self):
        shots = [
            {'shot_id': 's001'},
            {'shot_id': 's002'},
            {'shot_id': 's003'},
        ]

        target_ids = self.service._resolve_search_targets(
            {'shot_ids': ['s001', 's003', 'missing', '']},
            shots
        )

        self.assertEqual(target_ids, ['s001', 's003'])

    def test_compose_prepares_missing_selected_local_asset(self):
        class FakeDb:
            def __init__(self):
                self.created = []

            def get_project(self, project_id):
                return {'id': project_id, 'materials': []}

            def create_material(self, **kwargs):
                self.created.append(kwargs)

        service = BrollService(FakeDb())
        service._download_candidate = lambda candidate: 'temp/broll/fake.mp4'
        shot = {
            'shot_id': 's001',
            'selected_candidate_id': 'c001',
            'candidates': [
                {
                    'candidate_id': 'c001',
                    'provider': 'fake',
                    'source_id': 'source001',
                    'download_url': 'https://example.com/source001.mp4'
                }
            ]
        }

        result = service._ensure_compose_assets('project123', [shot])

        self.assertEqual(result['downloaded'], 1)
        self.assertEqual(result['usable'], 1)
        self.assertEqual(shot['candidates'][0]['local_path'], 'temp/broll/fake.mp4')

    def test_compose_tries_next_candidate_when_selected_download_fails(self):
        class FakeDb:
            def __init__(self):
                self.created = []

            def get_project(self, project_id):
                return {'id': project_id, 'materials': []}

            def create_material(self, **kwargs):
                self.created.append(kwargs)

        service = BrollService(FakeDb())

        def fake_download(candidate):
            if candidate['candidate_id'] == 'bad':
                raise TimeoutError('下载超时')
            return 'temp/broll/good.mp4'

        service._download_candidate = fake_download
        shot = {
            'shot_id': 's001',
            'selected_candidate_id': 'bad',
            'candidates': [
                {'candidate_id': 'bad', 'provider': 'fake', 'source_id': 'bad', 'download_url': 'https://example.com/bad.mp4'},
                {'candidate_id': 'good', 'provider': 'fake', 'source_id': 'good', 'download_url': 'https://example.com/good.mp4'},
            ]
        }

        with self.assertLogs('backend.services.broll_service', level='WARNING'):
            result = service._ensure_compose_assets('project123', [shot])

        self.assertEqual(result['downloaded'], 1)
        self.assertEqual(result['usable'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(shot['selected_candidate_id'], 'good')
        self.assertEqual(shot['candidates'][1]['local_path'], 'temp/broll/good.mp4')
        self.assertEqual(shot['candidates'][0]['download_error'], '下载超时')


if __name__ == '__main__':
    unittest.main()
