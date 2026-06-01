#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕工作区持久化测试

覆盖自动字幕页的核心恢复约束：后续空快照不能覆盖已生成字幕。
"""

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from backend.api.subtitle_api import register_subtitle_routes
from backend.database.db_manager import DatabaseManager


class TestSubtitleSessionPersistence(unittest.TestCase):
    """测试字幕会话保存和恢复。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'subtitle_session.db'
        self.db_manager = DatabaseManager(str(self.db_path))
        self.app = Flask(__name__)
        register_subtitle_routes(self.app, self.db_manager)
        self.client = self.app.test_client()

        project = self.db_manager.create_project(
            name='自动字幕测试项目',
            project_type='subtitle',
            description='测试空快照不会覆盖字幕',
            template='subtitle_tool'
        )
        self.project_id = project['id']
        self.subtitles = [
            {'start': 0.0, 'end': 1.5, 'text': '第一句字幕'},
            {'start': 1.5, 'end': 3.0, 'text': '第二句字幕'}
        ]
        self.db_manager.create_task(
            'task-subtitle-completed',
            'subtitle_generate',
            self.project_id,
            input_data={'task_name': '自动字幕生成'}
        )
        self.db_manager.update_task_status(
            'task-subtitle-completed',
            'completed',
            output_data={
                'message': '字幕生成完成',
                'subtitles': self.subtitles,
                'language': 'zh'
            }
        )
        self.db_manager.update_task_progress('task-subtitle-completed', 100)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_snapshot_does_not_erase_completed_subtitles(self):
        """后续空快照保存后，恢复接口仍返回已生成字幕。"""
        save_resp = self.client.post(
            f'/api/subtitle/session/{self.project_id}',
            json={
                'server_video_path': 'uploads/subtitle_videos/demo.mp4',
                'video_name': 'demo.mp4',
                'subtitles': [],
                'style': {'fontSize': 32},
                'language': 'zh-CN'
            }
        )
        self.assertEqual(save_resp.status_code, 200)
        self.assertEqual(save_resp.get_json()['code'], 0)

        restore_resp = self.client.get(f'/api/subtitle/session/{self.project_id}')
        self.assertEqual(restore_resp.status_code, 200)
        payload = restore_resp.get_json()['data']

        self.assertEqual(payload['subtitle_count'], 2)
        self.assertEqual(payload['subtitles'], self.subtitles)
        self.assertEqual(payload['video_name'], 'demo.mp4')

    def test_render_task_requires_project_id(self):
        """创建字幕视频导出任务必须传项目ID。"""
        resp = self.client.post('/api/subtitle/render-video-task', json={})
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        self.assertEqual(body['code'], 1)
        self.assertIn('项目ID', body['msg'])


if __name__ == '__main__':
    unittest.main()
