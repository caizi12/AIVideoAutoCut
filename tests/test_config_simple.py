#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分段配置持久化简化测试

直接测试配置保存和恢复逻辑，不依赖完整服务
"""

import json
import sqlite3
import os
from datetime import datetime


def test_config_save_and_restore():
    """测试配置保存和恢复"""

    print("\n" + "="*70)
    print("分段配置持久化简化测试")
    print("="*70)

    # 创建临时数据库
    db_path = f"test_config_{datetime.now().timestamp()}.db"

    try:
        # 1. 创建数据库表
        print("\n步骤1: 创建测试数据库")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broll_sessions (
                project_id TEXT PRIMARY KEY,
                session_data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.commit()
        print("✅ 数据库创建成功")

        # 2. 保存配置
        print("\n步骤2: 保存配置到数据库")
        project_id = "test_project_001"

        session_data = {
            'project_id': project_id,
            'version': 1,
            'aspect_ratio': 'original',
            'subtitle_mode': 'burned',
            'providers': ['wikimedia', 'pexels'],
            # 分段配置
            'min_shot_duration': 2.0,
            'max_shot_duration': 5.0,
            'prefer_sentence_boundary': False,
            'shots': []
        }

        cursor.execute('''
            INSERT OR REPLACE INTO broll_sessions (project_id, session_data, updated_at)
            VALUES (?, ?, ?)
        ''', (project_id, json.dumps(session_data), datetime.now().isoformat()))
        conn.commit()

        print(f"✅ 配置已保存:")
        print(f"   min_shot_duration: {session_data['min_shot_duration']}")
        print(f"   max_shot_duration: {session_data['max_shot_duration']}")
        print(f"   prefer_sentence_boundary: {session_data['prefer_sentence_boundary']}")

        # 3. 恢复配置
        print("\n步骤3: 从数据库恢复配置")
        cursor.execute('SELECT session_data FROM broll_sessions WHERE project_id = ?', (project_id,))
        row = cursor.fetchone()

        if row:
            restored_data = json.loads(row[0])
            print(f"✅ 配置已恢复:")
            print(f"   min_shot_duration: {restored_data['min_shot_duration']}")
            print(f"   max_shot_duration: {restored_data['max_shot_duration']}")
            print(f"   prefer_sentence_boundary: {restored_data['prefer_sentence_boundary']}")

            # 4. 验证配置
            print("\n步骤4: 验证配置")
            assert restored_data['min_shot_duration'] == 2.0, "min_shot_duration 不匹配"
            assert restored_data['max_shot_duration'] == 5.0, "max_shot_duration 不匹配"
            assert restored_data['prefer_sentence_boundary'] == False, "prefer_sentence_boundary 不匹配"
            print("✅ 配置验证通过")

            # 5. 测试配置更新
            print("\n步骤5: 更新配置")
            restored_data['min_shot_duration'] = 5.0
            restored_data['max_shot_duration'] = 12.0
            restored_data['prefer_sentence_boundary'] = True

            cursor.execute('''
                UPDATE broll_sessions SET session_data = ?, updated_at = ?
                WHERE project_id = ?
            ''', (json.dumps(restored_data), datetime.now().isoformat(), project_id))
            conn.commit()

            print(f"✅ 配置已更新:")
            print(f"   min_shot_duration: {restored_data['min_shot_duration']}")
            print(f"   max_shot_duration: {restored_data['max_shot_duration']}")
            print(f"   prefer_sentence_boundary: {restored_data['prefer_sentence_boundary']}")

            # 6. 再次恢复验证
            print("\n步骤6: 再次恢复验证")
            cursor.execute('SELECT session_data FROM broll_sessions WHERE project_id = ?', (project_id,))
            row = cursor.fetchone()
            final_data = json.loads(row[0])

            assert final_data['min_shot_duration'] == 5.0, "更新后的 min_shot_duration 不匹配"
            assert final_data['max_shot_duration'] == 12.0, "更新后的 max_shot_duration 不匹配"
            assert final_data['prefer_sentence_boundary'] == True, "更新后的 prefer_sentence_boundary 不匹配"

            print(f"✅ 更新后的配置验证通过:")
            print(f"   min_shot_duration: {final_data['min_shot_duration']}")
            print(f"   max_shot_duration: {final_data['max_shot_duration']}")
            print(f"   prefer_sentence_boundary: {final_data['prefer_sentence_boundary']}")

            print("\n" + "="*70)
            print("测试结果: ✅ 所有测试通过")
            print("="*70)
            return True

        else:
            print("❌ 未找到保存的配置")
            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # 清理
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"\n🧹 已清理测试数据库: {db_path}")


def test_multiple_projects():
    """测试多项目配置独立性"""

    print("\n" + "="*70)
    print("多项目配置独立性测试")
    print("="*70)

    db_path = f"test_multi_{datetime.now().timestamp()}.db"

    try:
        # 创建数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broll_sessions (
                project_id TEXT PRIMARY KEY,
                session_data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.commit()

        # 项目1: 快节奏配置
        print("\n步骤1: 保存项目1配置（快节奏）")
        project1_data = {
            'project_id': 'project_001',
            'min_shot_duration': 2.0,
            'max_shot_duration': 5.0,
            'prefer_sentence_boundary': False
        }

        cursor.execute('''
            INSERT INTO broll_sessions (project_id, session_data, updated_at)
            VALUES (?, ?, ?)
        ''', ('project_001', json.dumps(project1_data), datetime.now().isoformat()))
        conn.commit()
        print(f"✅ 项目1: min={project1_data['min_shot_duration']}, max={project1_data['max_shot_duration']}")

        # 项目2: 慢节奏配置
        print("\n步骤2: 保存项目2配置（慢节奏）")
        project2_data = {
            'project_id': 'project_002',
            'min_shot_duration': 5.0,
            'max_shot_duration': 12.0,
            'prefer_sentence_boundary': True
        }

        cursor.execute('''
            INSERT INTO broll_sessions (project_id, session_data, updated_at)
            VALUES (?, ?, ?)
        ''', ('project_002', json.dumps(project2_data), datetime.now().isoformat()))
        conn.commit()
        print(f"✅ 项目2: min={project2_data['min_shot_duration']}, max={project2_data['max_shot_duration']}")

        # 验证项目1
        print("\n步骤3: 验证项目1配置")
        cursor.execute('SELECT session_data FROM broll_sessions WHERE project_id = ?', ('project_001',))
        row = cursor.fetchone()
        restored1 = json.loads(row[0])

        assert restored1['min_shot_duration'] == 2.0
        assert restored1['max_shot_duration'] == 5.0
        print(f"✅ 项目1配置正确: min={restored1['min_shot_duration']}, max={restored1['max_shot_duration']}")

        # 验证项目2
        print("\n步骤4: 验证项目2配置")
        cursor.execute('SELECT session_data FROM broll_sessions WHERE project_id = ?', ('project_002',))
        row = cursor.fetchone()
        restored2 = json.loads(row[0])

        assert restored2['min_shot_duration'] == 5.0
        assert restored2['max_shot_duration'] == 12.0
        print(f"✅ 项目2配置正确: min={restored2['min_shot_duration']}, max={restored2['max_shot_duration']}")

        print("\n" + "="*70)
        print("测试结果: ✅ 多项目配置独立性验证通过")
        print("="*70)
        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == '__main__':
    print("\n" + "="*70)
    print("分段配置持久化测试套件（简化版）")
    print("="*70)

    results = []

    # 测试1
    result1 = test_config_save_and_restore()
    results.append(("配置保存和恢复", result1))

    # 测试2
    result2 = test_multiple_projects()
    results.append(("多项目配置独立", result2))

    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        exit(0)
    else:
        print("\n⚠️  部分测试失败")
        exit(1)
