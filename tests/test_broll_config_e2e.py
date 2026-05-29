#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分段配置持久化 E2E 测试 (Playwright)

测试前端配置保存和恢复功能
"""

import asyncio
import os
import sys
from playwright.async_api import async_playwright, expect

# 测试配置
BASE_URL = "http://localhost:5000"
TEST_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "test_video.mp4")


async def test_config_persistence():
    """测试配置持久化"""

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("\n" + "="*70)
            print("Playwright E2E 测试: 分段配置持久化")
            print("="*70)

            # 1. 打开页面
            print("\n步骤1: 打开页面")
            await page.goto(BASE_URL)
            await page.wait_for_load_state("networkidle")
            print("✅ 页面加载完成")

            # 2. 上传视频（如果有测试视频）
            if os.path.exists(TEST_VIDEO_PATH):
                print("\n步骤2: 上传测试视频")
                await page.set_input_files('input[type="file"]', TEST_VIDEO_PATH)
                await page.wait_for_timeout(2000)
                print("✅ 视频上传完成")
            else:
                print("\n步骤2: 跳过（无测试视频）")
                print("⚠️  请手动上传视频并生成字幕后继续测试")
                await page.wait_for_timeout(5000)

            # 3. 展开配置面板
            print("\n步骤3: 展开配置面板")
            config_toggle = page.locator('#brollConfigToggle')
            if await config_toggle.is_visible():
                await config_toggle.click()
                await page.wait_for_timeout(500)
                print("✅ 配置面板已展开")
            else:
                print("⚠️  配置面板按钮不可见")

            # 4. 检查默认配置
            print("\n步骤4: 检查默认配置")
            min_duration = page.locator('#brollMinDuration')
            max_duration = page.locator('#brollMaxDuration')
            prefer_sentence = page.locator('#brollPreferSentence')

            min_value = await min_duration.input_value()
            max_value = await max_duration.input_value()
            prefer_checked = await prefer_sentence.is_checked()

            print(f"  最小时长: {min_value}")
            print(f"  最大时长: {max_value}")
            print(f"  优先句子边界: {prefer_checked}")
            print("✅ 默认配置读取成功")

            # 5. 点击快节奏模板
            print("\n步骤5: 点击快节奏模板")
            fast_btn = page.locator('button[data-template="fast"]')
            await fast_btn.click()
            await page.wait_for_timeout(500)

            # 验证配置已更新
            min_value = await min_duration.input_value()
            max_value = await max_duration.input_value()
            prefer_checked = await prefer_sentence.is_checked()

            print(f"  最小时长: {min_value}")
            print(f"  最大时长: {max_value}")
            print(f"  优先句子边界: {prefer_checked}")

            assert min_value == "2", f"最小时长应该是2，实际是{min_value}"
            assert max_value == "5", f"最大时长应该是5，实际是{max_value}"
            assert prefer_checked == False, f"优先句子边界应该是False，实际是{prefer_checked}"
            print("✅ 快节奏配置应用成功")

            # 6. 等待自动保存
            print("\n步骤6: 等待自动保存")
            await page.wait_for_timeout(1000)
            print("✅ 配置已自动保存")

            # 7. 刷新页面
            print("\n步骤7: 刷新页面")
            await page.reload()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)
            print("✅ 页面已刷新")

            # 8. 展开配置面板
            print("\n步骤8: 重新展开配置面板")
            config_toggle = page.locator('#brollConfigToggle')
            if await config_toggle.is_visible():
                await config_toggle.click()
                await page.wait_for_timeout(500)
                print("✅ 配置面板已展开")

            # 9. 验证配置是否保持
            print("\n步骤9: 验证配置是否保持")
            min_duration = page.locator('#brollMinDuration')
            max_duration = page.locator('#brollMaxDuration')
            prefer_sentence = page.locator('#brollPreferSentence')

            min_value = await min_duration.input_value()
            max_value = await max_duration.input_value()
            prefer_checked = await prefer_sentence.is_checked()

            print(f"  最小时长: {min_value}")
            print(f"  最大时长: {max_value}")
            print(f"  优先句子边界: {prefer_checked}")

            # 验证配置保持
            if min_value == "2" and max_value == "5" and prefer_checked == False:
                print("✅ 配置持久化成功！")
                print("\n" + "="*70)
                print("测试结果: ✅ 通过")
                print("="*70)
                return True
            else:
                print("❌ 配置未保持！")
                print(f"   期望: min=2, max=5, prefer=False")
                print(f"   实际: min={min_value}, max={max_value}, prefer={prefer_checked}")
                print("\n" + "="*70)
                print("测试结果: ❌ 失败")
                print("="*70)
                return False

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # 截图
            screenshot_path = os.path.join(os.path.dirname(__file__), "test_result.png")
            await page.screenshot(path=screenshot_path)
            print(f"\n📸 截图已保存: {screenshot_path}")

            # 关闭浏览器
            await browser.close()


async def test_multiple_templates():
    """测试多个模板切换"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("\n" + "="*70)
            print("Playwright E2E 测试: 多模板切换")
            print("="*70)

            # 打开页面
            print("\n步骤1: 打开页面")
            await page.goto(BASE_URL)
            await page.wait_for_load_state("networkidle")
            print("✅ 页面加载完成")

            # 展开配置面板
            print("\n步骤2: 展开配置面板")
            config_toggle = page.locator('#brollConfigToggle')
            if await config_toggle.is_visible():
                await config_toggle.click()
                await page.wait_for_timeout(500)

            min_duration = page.locator('#brollMinDuration')
            max_duration = page.locator('#brollMaxDuration')

            # 测试不同模板
            templates = [
                {'name': '快节奏', 'template': 'fast', 'min': '2', 'max': '5'},
                {'name': '默认', 'template': 'default', 'min': '3', 'max': '8'},
                {'name': '慢节奏', 'template': 'slow', 'min': '5', 'max': '12'},
            ]

            for tmpl in templates:
                print(f"\n测试模板: {tmpl['name']}")

                # 点击模板按钮
                btn = page.locator(f'button[data-template="{tmpl["template"]}"]')
                await btn.click()
                await page.wait_for_timeout(500)

                # 验证配置
                min_value = await min_duration.input_value()
                max_value = await max_duration.input_value()

                print(f"  期望: min={tmpl['min']}, max={tmpl['max']}")
                print(f"  实际: min={min_value}, max={max_value}")

                if min_value == tmpl['min'] and max_value == tmpl['max']:
                    print(f"  ✅ {tmpl['name']}配置正确")
                else:
                    print(f"  ❌ {tmpl['name']}配置错误")
                    return False

            print("\n" + "="*70)
            print("测试结果: ✅ 所有模板切换正常")
            print("="*70)
            return True

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            await browser.close()


async def test_manual_config_change():
    """测试手动修改配置"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=500)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("\n" + "="*70)
            print("Playwright E2E 测试: 手动修改配置")
            print("="*70)

            # 打开页面
            print("\n步骤1: 打开页面")
            await page.goto(BASE_URL)
            await page.wait_for_load_state("networkidle")

            # 展开配置面板
            print("\n步骤2: 展开配置面板")
            config_toggle = page.locator('#brollConfigToggle')
            if await config_toggle.is_visible():
                await config_toggle.click()
                await page.wait_for_timeout(500)

            # 手动修改配置
            print("\n步骤3: 手动修改配置")
            min_duration = page.locator('#brollMinDuration')
            max_duration = page.locator('#brollMaxDuration')

            await min_duration.fill('3.5')
            await max_duration.fill('7.0')
            await page.wait_for_timeout(1000)  # 等待自动保存

            print("  设置: min=3.5, max=7.0")
            print("✅ 配置已修改")

            # 刷新页面
            print("\n步骤4: 刷新页面")
            await page.reload()
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(1000)

            # 展开配置面板
            config_toggle = page.locator('#brollConfigToggle')
            if await config_toggle.is_visible():
                await config_toggle.click()
                await page.wait_for_timeout(500)

            # 验证配置
            print("\n步骤5: 验证配置")
            min_duration = page.locator('#brollMinDuration')
            max_duration = page.locator('#brollMaxDuration')

            min_value = await min_duration.input_value()
            max_value = await max_duration.input_value()

            print(f"  期望: min=3.5, max=7")
            print(f"  实际: min={min_value}, max={max_value}")

            if min_value == "3.5" and max_value == "7":
                print("\n✅ 手动配置持久化成功")
                return True
            else:
                print("\n❌ 手动配置未保持")
                return False

        except Exception as e:
            print(f"\n❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            await browser.close()


async def main():
    """运行所有E2E测试"""
    print("\n" + "="*70)
    print("分段配置持久化 E2E 测试套件")
    print("="*70)
    print("\n⚠️  注意: 请确保后端服务已启动 (http://localhost:5000)")
    print("⚠️  注意: 测试将自动打开浏览器窗口")
    print("\n按 Enter 继续...")
    input()

    results = []

    # 测试1: 配置持久化
    print("\n" + "="*70)
    print("测试1: 配置持久化")
    print("="*70)
    result1 = await test_config_persistence()
    results.append(("配置持久化", result1))

    # 测试2: 多模板切换
    print("\n" + "="*70)
    print("测试2: 多模板切换")
    print("="*70)
    result2 = await test_multiple_templates()
    results.append(("多模板切换", result2))

    # 测试3: 手动修改配置
    print("\n" + "="*70)
    print("测试3: 手动修改配置")
    print("="*70)
    result3 = await test_manual_config_change()
    results.append(("手动修改配置", result3))

    # 输出总结
    print("\n" + "="*70)
    print("E2E 测试总结")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n✅ 所有E2E测试通过！")
        return 0
    else:
        print("\n❌ 部分E2E测试失败")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
