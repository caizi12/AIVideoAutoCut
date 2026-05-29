#!/bin/bash
# 分段配置持久化测试运行脚本

echo "========================================================================"
echo "分段配置持久化测试套件"
echo "========================================================================"
echo ""

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

# 检查是否在项目根目录
if [ ! -f "backend/services/broll_service.py" ]; then
    echo "❌ 错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 创建tests目录（如果不存在）
mkdir -p tests

echo "========================================================================"
echo "1. 运行单元测试"
echo "========================================================================"
echo ""

python3 tests/test_broll_config_persistence.py

UNIT_TEST_EXIT_CODE=$?

echo ""
echo "========================================================================"
echo "2. 运行 E2E 测试 (Playwright)"
echo "========================================================================"
echo ""
echo "⚠️  注意: E2E测试需要："
echo "   1. 后端服务运行在 http://localhost:5000"
echo "   2. 已安装 playwright: pip install playwright"
echo "   3. 已安装浏览器: playwright install chromium"
echo ""
read -p "是否运行E2E测试? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # 检查playwright
    if ! python3 -c "import playwright" 2>/dev/null; then
        echo "⚠️  未安装 playwright，正在安装..."
        pip install playwright
        playwright install chromium
    fi

    python3 tests/test_broll_config_e2e.py
    E2E_TEST_EXIT_CODE=$?
else
    echo "⏭️  跳过 E2E 测试"
    E2E_TEST_EXIT_CODE=0
fi

echo ""
echo "========================================================================"
echo "测试总结"
echo "========================================================================"
echo ""

if [ $UNIT_TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ 单元测试: 通过"
else
    echo "❌ 单元测试: 失败"
fi

if [ $E2E_TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ E2E测试: 通过"
else
    echo "❌ E2E测试: 失败"
fi

echo ""

if [ $UNIT_TEST_EXIT_CODE -eq 0 ] && [ $E2E_TEST_EXIT_CODE -eq 0 ]; then
    echo "🎉 所有测试通过！"
    exit 0
else
    echo "⚠️  部分测试失败，请检查日志"
    exit 1
fi
