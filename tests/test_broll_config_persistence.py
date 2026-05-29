#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分段配置持久化单元测试

测试配置是否正确保存和恢复
"""

import sys
import os
import unittest
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.db_manager import DatabaseManager
from backend.services.broll_service import BrollService


class TestBrollConfigPersistence(unittest.TestCase):
    """测试分段配置持久化"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        cls.db_manager = DatabaseManager()
        cls.broll_service = BrollService(cls.db_manager)

    def setUp(self):
        """每个测试前的准备"""
        # 创建测试项目
        self.project_id = f"test_project_{datetime.now().timestamp()}"
        self.db_manager.create_project(
            project_id=self.project_id,
            video_path="/test/video.mp4",
            video_filename="test_video.mp4"
        )

        # 测试字幕数据
        self.test_subtitles = [
            {'start': 0.0, 'end': 2.0, 'text': '今天我们来介绍'},
            {'start': 2.0, 'end': 4.0, 'text': '人工智能的发展历史'},
            {'start': 4.0, 'end': 6.0, 'text': '从1950年代开始'},
            {'start': 6.0, 'end': 8.0, 'text': '科学家们就在研究'},
            {'start': 8.0, 'end': 10.0, 'text': '如何让机器模拟人类智能'},
            {'start': 10.0, 'end': 12.0, 'text': '经过几十年的发展'},
            {'start': 12.0, 'end': 14.0, 'text': 'AI技术已经取得了巨大进步'},
            {'start': 14.0, 'end': 16.0, 'text': '现在我们来看看具体应用'},
        ]

        # 保存字幕到项目
        self.db_manager.save_subtitles(self.project_id, self.test_subtitles)

    def tearDown(self):
        """每个测试后的清理"""
        # 删除测试项目
        try:
            self.db_manager.delete_project(self.project_id)
        except:
            pass

    def test_01_save_default_config(self):
        """测试1: 保存默认配置"""
        print("\n" + "="*70)
        print("测试1: 保存默认配置")
        print("="*70)

        # 准备数据
        data = {
            'project_id': self.project_id,
            'min_shot_duration': 3.0,
            'max_shot_duration': 8.0,
            'prefer_sentence_boundary': False
        }

        # 生成方案（内部会保存配置）
        project = self.db_manager.get_project(self.project_id)
        subtitles = self.test_subtitles
        session = self.broll_service._empty_session(project)
        session.update({
            'aspect_ratio': 'original',
            'subtitle_mode': 'burned',
            'providers': ['wikimedia'],
            'min_shot_duration': data['min_shot_duration'],
            'max_shot_duration': data['max_shot_duration'],
            'prefer_sentence_boundary': data['prefer_sentence_boundary'],
            'shots': self.broll_service._build_shots(subtitles, data)
        })

        # 保存session
        saved = self.broll_service.save_session(self.project_id, session)

        # 验证配置已保存
        self.assertIn('min_shot_duration', saved)
        self.assertIn('max_shot_duration', saved)
        self.assertIn('prefer_sentence_boundary', saved)

        self.assertEqual(saved['min_shot_duration'], 3.0)
        self.assertEqual(saved['max_shot_duration'], 8.0)
        self.assertEqual(saved['prefer_sentence_boundary'], False)

        print(f"✅ 配置已保存:")
        print(f"   min_shot_duration: {saved['min_shot_duration']}")
        print(f"   max_shot_duration: {saved['max_shot_duration']}")
        print(f"   prefer_sentence_boundary: {saved['prefer_sentence_boundary']}")

    def test_02_restore_config(self):
        """测试2: 恢复配置"""
        print("\n" + "="*70)
        print("测试2: 恢复配置")
        print("="*70)

        # 先保存配置
        data = {
            'project_id': self.project_id,
            'min_shot_duration': 2.0,
            'max_shot_duration': 5.0,
            'prefer_sentence_boundary': False
        }

        project = self.db_manager.get_project(self.project_id)
        subtitles = self.test_subtitles
        session = self.broll_service._empty_session(project)
        session.update({
            'aspect_ratio': 'original',
            'subtitle_mode': 'burned',
            'providers': ['wikimedia'],
            'min_shot_duration': data['min_shot_duration'],
            'max_shot_duration': data['max_shot_duration'],
            'prefer_sentence_boundary': data['prefer_sentence_boundary'],
            'shots': self.broll_service._build_shots(subtitles, data)
        })
        self.broll_service.save_session(self.project_id, session)

        print(f"✅ 已保存配置: min={data['min_shot_duration']}, max={data['max_shot_duration']}")

        # 恢复配置
        restored = self.broll_service.get_session(self.project_id)

        # 验证配置已恢复
        self.assertEqual(restored['min_shot_duration'], 2.0)
        self.assertEqual(restored['max_shot_duration'], 5.0)
        self.assertEqual(restored['prefer_sentence_boundary'], False)

        print(f"✅ 配置已恢复:")
        print(f"   min_shot_duration: {restored['min_shot_duration']}")
        print(f"   max_shot_duration: {restored['max_shot_duration']}")
        print(f"   prefer_sentence_boundary: {restored['prefer_sentence_boundary']}")

    def test_03_different_configs_different_shots(self):
        """测试3: 不同配置生成不同数量的镜头"""
        print("\n" + "="*70)
        print("测试3: 不同配置生成不同数量的镜头")
        print("="*70)

        configs = [
            {'name': '快节奏', 'min': 2.0, 'max': 5.0, 'prefer': False},
            {'name': '默认', 'min': 3.0, 'max': 8.0, 'prefer': False},
            {'name': '慢节奏', 'min': 5.0, 'max': 12.0, 'prefer': False},
        ]

        results = []

        for config in configs:
            data = {
                'project_id': self.project_id,
                'min_shot_duration': config['min'],
                'max_shot_duration': config['max'],
                'prefer_sentence_boundary': config['prefer']
            }

            shots = self.broll_service._build_shots(self.test_subtitles, data)
            shot_count = len(shots)
            results.append((config['name'], shot_count))

            print(f"\n{config['name']} (min={config['min']}, max={config['max']}): {shot_count} 个镜头")
            for i, shot in enumerate(shots, 1):
                print(f"  镜头{i}: {shot['start']:.1f}-{shot['end']:.1f}s ({shot['duration']:.1f}s)")

        # 验证不同配置生成不同数量的镜头
        shot_counts = [count for _, count in results]
        unique_counts = set(shot_counts)

        print(f"\n结果对比:")
        for name, count in results:
            print(f"  {name}: {count} 个镜头")

        if len(unique_counts) > 1:
            print(f"\n✅ 测试通过: 不同配置生成不同数量的镜头")
        else:
            print(f"\n⚠️  警告: 所有配置生成相同数量的镜头")
            self.fail("不同配置应该生成不同数量的镜头")

    def test_04_config_persistence_across_sessions(self):
        """测试4: 配置在多次session操作中保持"""
        print("\n" + "="*70)
        print("测试4: 配置在多次session操作中保持")
        print("="*70)

        # 第一次：保存快节奏配置
        data1 = {
            'project_id': self.project_id,
            'min_shot_duration': 2.0,
            'max_shot_duration': 5.0,
            'prefer_sentence_boundary': False
        }

        project = self.db_manager.get_project(self.project_id)
        session1 = self.broll_service._empty_session(project)
        session1.update({
            'aspect_ratio': 'original',
            'subtitle_mode': 'burned',
            'providers': ['wikimedia'],
            'min_shot_duration': data1['min_shot_duration'],
            'max_shot_duration': data1['max_shot_duration'],
            'prefer_sentence_boundary': data1['prefer_sentence_boundary'],
            'shots': self.broll_service._build_shots(self.test_subtitles, data1)
        })
        self.broll_service.save_session(self.project_id, session1)

        print(f"✅ 第一次保存: min={data1['min_shot_duration']}, max={data1['max_shot_duration']}")

        # 恢复并验证
        restored1 = self.broll_service.get_session(self.project_id)
        self.assertEqual(restored1['min_shot_duration'], 2.0)
        self.assertEqual(restored1['max_shot_duration'], 5.0)
        print(f"✅ 第一次恢复: min={restored1['min_shot_duration']}, max={restored1['max_shot_duration']}")

        # 第二次：修改为慢节奏配置
        data2 = {
            'project_id': self.project_id,
            'min_shot_duration': 5.0,
            'max_shot_duration': 12.0,
            'prefer_sentence_boundary': False
        }

        session2 = self.broll_service.get_session(self.project_id)
        session2.update({
            'min_shot_duration': data2['min_shot_duration'],
            'max_shot_duration': data2['max_shot_duration'],
            'prefer_sentence_boundary': data2['prefer_sentence_boundary'],
            'shots': self.broll_service._build_shots(self.test_subtitles, data2)
        })
        self.broll_service.save_session(self.project_id, session2)

        print(f"✅ 第二次保存: min={data2['min_shot_duration']}, max={data2['max_shot_duration']}")

        # 恢复并验证
        restored2 = self.broll_service.get_session(self.project_id)
        self.assertEqual(restored2['min_shot_duration'], 5.0)
        self.assertEqual(restored2['max_shot_duration'], 12.0)
        print(f"✅ 第二次恢复: min={restored2['min_shot_duration']}, max={restored2['max_shot_duration']}")

        print(f"\n✅ 测试通过: 配置在多次操作中正确保持和更新")

    def test_05_multiple_projects_independent_configs(self):
        """测试5: 多个项目的配置相互独立"""
        print("\n" + "="*70)
        print("测试5: 多个项目的配置相互独立")
        print("="*70)

        # 创建第二个测试项目
        project_id_2 = f"test_project_2_{datetime.now().timestamp()}"
        self.db_manager.create_project(
            project_id=project_id_2,
            video_path="/test/video2.mp4",
            video_filename="test_video2.mp4"
        )
        self.db_manager.save_subtitles(project_id_2, self.test_subtitles)

        try:
            # 项目1：快节奏配置
            data1 = {
                'project_id': self.project_id,
                'min_shot_duration': 2.0,
                'max_shot_duration': 5.0,
                'prefer_sentence_boundary': False
            }

            project1 = self.db_manager.get_project(self.project_id)
            session1 = self.broll_service._empty_session(project1)
            session1.update({
                'aspect_ratio': 'original',
                'subtitle_mode': 'burned',
                'providers': ['wikimedia'],
                'min_shot_duration': data1['min_shot_duration'],
                'max_shot_duration': data1['max_shot_duration'],
                'prefer_sentence_boundary': data1['prefer_sentence_boundary'],
                'shots': self.broll_service._build_shots(self.test_subtitles, data1)
            })
            self.broll_service.save_session(self.project_id, session1)

            print(f"✅ 项目1配置: min={data1['min_shot_duration']}, max={data1['max_shot_duration']}")

            # 项目2：慢节奏配置
            data2 = {
                'project_id': project_id_2,
                'min_shot_duration': 5.0,
                'max_shot_duration': 12.0,
                'prefer_sentence_boundary': True
            }

            project2 = self.db_manager.get_project(project_id_2)
            session2 = self.broll_service._empty_session(project2)
            session2.update({
                'aspect_ratio': '16:9',
                'subtitle_mode': 'separate',
                'providers': ['pexels'],
                'min_shot_duration': data2['min_shot_duration'],
                'max_shot_duration': data2['max_shot_duration'],
                'prefer_sentence_boundary': data2['prefer_sentence_boundary'],
                'shots': self.broll_service._build_shots(self.test_subtitles, data2)
            })
            self.broll_service.save_session(project_id_2, session2)

            print(f"✅ 项目2配置: min={data2['min_shot_duration']}, max={data2['max_shot_duration']}")

            # 验证项目1配置
            restored1 = self.broll_service.get_session(self.project_id)
            self.assertEqual(restored1['min_shot_duration'], 2.0)
            self.assertEqual(restored1['max_shot_duration'], 5.0)
            self.assertEqual(restored1['prefer_sentence_boundary'], False)
            print(f"✅ 项目1恢复: min={restored1['min_shot_duration']}, max={restored1['max_shot_duration']}")

            # 验证项目2配置
            restored2 = self.broll_service.get_session(project_id_2)
            self.assertEqual(restored2['min_shot_duration'], 5.0)
            self.assertEqual(restored2['max_shot_duration'], 12.0)
            self.assertEqual(restored2['prefer_sentence_boundary'], True)
            print(f"✅ 项目2恢复: min={restored2['min_shot_duration']}, max={restored2['max_shot_duration']}")

            print(f"\n✅ 测试通过: 多个项目的配置相互独立")

        finally:
            # 清理第二个项目
            try:
                self.db_manager.delete_project(project_id_2)
            except:
                pass


def run_tests():
    """运行所有测试"""
    print("\n" + "="*70)
    print("分段配置持久化单元测试")
    print("="*70)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestBrollConfigPersistence)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == '__main__':
    exit_code = run_tests()
    sys.exit(exit_code)
