# 分段配置持久化测试文档

本文档说明如何运行分段配置持久化的单元测试和E2E测试。

---

## 📋 测试概览

### 测试类型

1. **单元测试** (`test_broll_config_persistence.py`)
   - 测试后端配置保存和恢复
   - 测试不同配置生成不同镜头
   - 测试多项目配置独立性

2. **E2E测试** (`test_broll_config_e2e.py`)
   - 测试前端UI配置操作
   - 测试配置持久化
   - 测试模板切换
   - 测试手动修改配置

---

## 🚀 快速开始

### 方法1: 使用测试脚本（推荐）

```bash
# 给脚本添加执行权限
chmod +x tests/run_tests.sh

# 运行所有测试
./tests/run_tests.sh
```

---

### 方法2: 手动运行

#### 1. 运行单元测试

```bash
# 在项目根目录执行
python3 tests/test_broll_config_persistence.py
```

**预期输出**:
```
======================================================================
分段配置持久化单元测试
======================================================================

测试1: 保存默认配置
✅ 配置已保存:
   min_shot_duration: 3.0
   max_shot_duration: 8.0
   prefer_sentence_boundary: False

测试2: 恢复配置
✅ 配置已恢复:
   min_shot_duration: 2.0
   max_shot_duration: 5.0
   prefer_sentence_boundary: False

...

======================================================================
测试总结
======================================================================
运行测试: 5
成功: 5
失败: 0
错误: 0

✅ 所有测试通过！
```

---

#### 2. 运行E2E测试

**前提条件**:
1. 后端服务运行在 `http://localhost:5000`
2. 已安装 playwright

**安装playwright**:
```bash
pip install playwright
playwright install chromium
```

**运行测试**:
```bash
python3 tests/test_broll_config_e2e.py
```

**预期行为**:
- 自动打开Chrome浏览器
- 自动操作UI（点击按钮、输入配置等）
- 自动刷新页面验证持久化
- 生成截图 `test_result.png`

---

## 📊 测试详情

### 单元测试

#### 测试1: 保存默认配置
```python
def test_01_save_default_config(self):
    """测试保存默认配置到数据库"""
```

**测试内容**:
- 创建session并保存配置
- 验证配置字段存在
- 验证配置值正确

**验证点**:
- ✅ `min_shot_duration` 保存正确
- ✅ `max_shot_duration` 保存正确
- ✅ `prefer_sentence_boundary` 保存正确

---

#### 测试2: 恢复配置
```python
def test_02_restore_config(self):
    """测试从数据库恢复配置"""
```

**测试内容**:
- 保存配置
- 重新加载session
- 验证配置恢复正确

**验证点**:
- ✅ 配置值完全一致
- ✅ 没有数据丢失

---

#### 测试3: 不同配置生成不同镜头
```python
def test_03_different_configs_different_shots(self):
    """测试不同配置生成不同数量的镜头"""
```

**测试内容**:
- 使用快节奏配置 (min=2.0, max=5.0)
- 使用默认配置 (min=3.0, max=8.0)
- 使用慢节奏配置 (min=5.0, max=12.0)
- 对比镜头数量

**验证点**:
- ✅ 快节奏生成更多镜头
- ✅ 慢节奏生成更少镜头
- ✅ 配置确实影响分段结果

**示例输出**:
```
快节奏 (min=2.0, max=5.0): 6 个镜头
  镜头1: 0.0-4.0s (4.0s)
  镜头2: 4.0-6.0s (2.0s)
  ...

默认 (min=3.0, max=8.0): 4 个镜头
  镜头1: 0.0-8.0s (8.0s)
  ...

慢节奏 (min=5.0, max=12.0): 3 个镜头
  镜头1: 0.0-12.0s (12.0s)
  ...

✅ 测试通过: 不同配置生成不同数量的镜头
```

---

#### 测试4: 配置在多次操作中保持
```python
def test_04_config_persistence_across_sessions(self):
    """测试配置在多次session操作中保持"""
```

**测试内容**:
- 第一次保存快节奏配置
- 恢复并验证
- 第二次修改为慢节奏配置
- 恢复并验证

**验证点**:
- ✅ 配置正确更新
- ✅ 每次恢复都正确

---

#### 测试5: 多项目配置独立
```python
def test_05_multiple_projects_independent_configs(self):
    """测试多个项目的配置相互独立"""
```

**测试内容**:
- 项目1设置快节奏配置
- 项目2设置慢节奏配置
- 分别恢复并验证

**验证点**:
- ✅ 项目1配置不受项目2影响
- ✅ 项目2配置不受项目1影响
- ✅ 配置完全独立

---

### E2E测试

#### 测试1: 配置持久化
```python
async def test_config_persistence():
    """测试前端配置持久化"""
```

**测试步骤**:
1. 打开页面
2. 展开配置面板
3. 点击"快节奏"模板
4. 等待自动保存
5. 刷新页面
6. 验证配置是否保持

**验证点**:
- ✅ 配置值保持不变
- ✅ 模板按钮正确高亮

---

#### 测试2: 多模板切换
```python
async def test_multiple_templates():
    """测试多个模板切换"""
```

**测试步骤**:
1. 点击"快节奏"模板
2. 验证配置: min=2, max=5
3. 点击"默认"模板
4. 验证配置: min=3, max=8
5. 点击"慢节奏"模板
6. 验证配置: min=5, max=12

**验证点**:
- ✅ 每个模板配置正确
- ✅ 切换流畅无错误

---

#### 测试3: 手动修改配置
```python
async def test_manual_config_change():
    """测试手动修改配置"""
```

**测试步骤**:
1. 手动输入 min=3.5, max=7.0
2. 等待自动保存
3. 刷新页面
4. 验证配置是否保持

**验证点**:
- ✅ 手动配置正确保存
- ✅ 刷新后配置保持

---

## 🐛 故障排除

### 单元测试失败

#### 问题1: ModuleNotFoundError
```
ModuleNotFoundError: No module named 'backend'
```

**解决**:
```bash
# 确保在项目根目录运行
cd /Users/lfeng/workspace/AIVideoAutoCut
python3 tests/test_broll_config_persistence.py
```

---

#### 问题2: 数据库错误
```
sqlite3.OperationalError: database is locked
```

**解决**:
```bash
# 关闭所有使用数据库的进程
# 或删除测试数据库
rm -f data/test_*.db
```

---

### E2E测试失败

#### 问题1: 连接失败
```
Error: net::ERR_CONNECTION_REFUSED at http://localhost:5000
```

**解决**:
```bash
# 启动后端服务
python3 frontend/app.py
```

---

#### 问题2: Playwright未安装
```
ModuleNotFoundError: No module named 'playwright'
```

**解决**:
```bash
pip install playwright
playwright install chromium
```

---

#### 问题3: 元素未找到
```
TimeoutError: Timeout 30000ms exceeded
```

**解决**:
- 检查HTML元素ID是否正确
- 增加等待时间
- 检查页面是否正确加载

---

## 📊 测试覆盖率

### 后端覆盖

- ✅ 配置保存到session
- ✅ 配置从session恢复
- ✅ 配置影响分段逻辑
- ✅ 多项目配置独立

### 前端覆盖

- ✅ 配置UI显示
- ✅ 模板按钮点击
- ✅ 配置输入修改
- ✅ 自动保存触发
- ✅ 页面刷新恢复
- ✅ 模板按钮高亮

---

## 🎯 测试结果示例

### 成功示例

```
======================================================================
分段配置持久化单元测试
======================================================================

test_01_save_default_config (__main__.TestBrollConfigPersistence) ... ok
test_02_restore_config (__main__.TestBrollConfigPersistence) ... ok
test_03_different_configs_different_shots (__main__.TestBrollConfigPersistence) ... ok
test_04_config_persistence_across_sessions (__main__.TestBrollConfigPersistence) ... ok
test_05_multiple_projects_independent_configs (__main__.TestBrollConfigPersistence) ... ok

----------------------------------------------------------------------
Ran 5 tests in 2.345s

OK

======================================================================
测试总结
======================================================================
运行测试: 5
成功: 5
失败: 0
错误: 0

✅ 所有测试通过！
```

---

### 失败示例

```
======================================================================
FAIL: test_03_different_configs_different_shots
----------------------------------------------------------------------
Traceback (most recent call last):
  ...
AssertionError: 不同配置应该生成不同数量的镜头

----------------------------------------------------------------------
Ran 5 tests in 2.345s

FAILED (failures=1)

======================================================================
测试总结
======================================================================
运行测试: 5
成功: 4
失败: 1
错误: 0

❌ 部分测试失败
```

---

## 📝 添加新测试

### 添加单元测试

```python
def test_06_your_test_name(self):
    """测试描述"""
    print("\n" + "="*70)
    print("测试6: 你的测试名称")
    print("="*70)

    # 测试逻辑
    # ...

    # 断言
    self.assertEqual(expected, actual)

    print("✅ 测试通过")
```

---

### 添加E2E测试

```python
async def test_your_feature():
    """测试你的功能"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        try:
            # 测试步骤
            await page.goto(BASE_URL)
            # ...

            # 验证
            assert condition, "错误消息"

            return True

        finally:
            await browser.close()
```

---

## 🎉 总结

### 测试覆盖

- ✅ 后端配置保存
- ✅ 后端配置恢复
- ✅ 前端UI操作
- ✅ 前端配置持久化
- ✅ 多项目独立性
- ✅ 配置影响分段

### 测试质量

- ✅ 自动化测试
- ✅ 可重复运行
- ✅ 清晰的输出
- ✅ 详细的文档

---

## 📞 需要帮助？

如果测试失败或有问题：

1. 查看测试输出日志
2. 检查故障排除部分
3. 查看截图 `test_result.png`
4. 检查后端日志 `logs/app.log`

---

**文档版本**: v1.0
**最后更新**: 2026-05-28
