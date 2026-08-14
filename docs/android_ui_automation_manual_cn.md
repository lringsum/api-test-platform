# Android UI 自动化联调手册

这份文档面向平台使用者、测试同学和后续维护开发者，覆盖 Android UI 自动化能力的本地联调、Worker 启动方式、前置依赖和验收口径。

## 实时执行详情

- 任务入队后即按流程快照预创建完整步骤，初始状态为“待执行”。
- Worker 执行每一步前更新为“执行中”，完成后更新为“通过”或“失败”，详情抽屉在活动状态下每秒刷新并显示完成数与总步骤数。
- 执行失败时，当前执行步骤标记为“失败”，未执行步骤标记为“已跳过”；手动停止时，当前步骤标记为“已停止”，未执行步骤标记为“已跳过”。
- 任务进入终态、详情抽屉关闭或页面切到后台后停止轮询。

## 1. 当前能力范围

当前已落地的能力：

- Android UI 自动化任务管理
- 单任务手动入队
- 失败记录重新执行
- 执行记录列表、实时步骤进度、详情与截图预览
- 独立 Android Worker 轮询消费队列
- APK 下载、`aapt` 解析、`adb install`、`am start`、截图、日志回写
- Worker 心跳、单实例锁、僵尸任务恢复
- Worker 在线状态、设备状态与手动停止
- 异常记录批量重试

当前未落地的增强项：

- 批量导入 APK 任务
- 批量运行
- 真机 / 模拟器设备池调度策略

## 2. 关键文件

- 路由：`app/routes/api_v1.py`
- 服务：`app/services/android_ui_automation_service.py`
- Worker：`app/services/android_ui_automation_worker.py`
- Worker 启动脚本：`scripts/run_android_ui_automation_worker.py`
- 页面：`frontend/src/views/AndroidAutomationPage.vue`
- 数据模型：`app/models.py`
- 迁移：`migrations/versions/e370cba83ac6_add_android_ui_automation_models.py`

## 3. 启动前置

### 3.1 Python 依赖

建议使用项目自带虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.2 数据库迁移

Android UI 自动化依赖下面两张表：

- `android_ui_test_tasks`
- `android_ui_test_runs`

如果没有先执行迁移，Worker 会直接提示：

```text
Android UI 自动化数据表尚未创建，请先执行数据库迁移。
```

执行迁移：

```powershell
.\.venv\Scripts\python.exe -m flask db upgrade
```

如果当前环境没有配置 `FLASK_APP`，先执行：

```powershell
$env:FLASK_APP="run.py"
.\.venv\Scripts\python.exe -m flask db upgrade
```

### 3.3 ADB / AAPT

平台现在默认按 MuMu 环境联调：

- `ANDROID_UI_ADB_PATH=C:\Program Files\Netease\MuMu\nx_main\adb.exe`
- `ANDROID_UI_AAPT_PATH` 未设置时，程序优先使用项目内 `tools/android/aapt.exe`；随后查找 Android SDK `build-tools` 目录里的 `aapt.exe`
- `ANDROID_UI_AUTO_START_DEVICE=true`（默认）：任务发现本机 MuMu 设备离线时自动拉起实例
- `ANDROID_UI_DEVICE_START_WAIT_SECONDS=90`：自动拉起后等待 ADB 上线的最长秒数

如果本机 `aapt.exe` 不在标准 Android SDK 目录，可以通过环境变量手工覆盖：

```powershell
$env:ANDROID_UI_ADB_PATH="C:\Program Files\Netease\MuMu\nx_main\adb.exe"
$env:ANDROID_UI_AAPT_PATH="C:\Users\Administrator\AppData\Local\Android\Sdk\build-tools\35.0.0\aapt.exe"
```

项目内工具用于统一本地开发环境；如果需要升级或替换它，请使用可信 Android SDK Build-Tools 中的 `aapt.exe`，并核对 `tools/android/README.md` 记录的版本和校验值。

### 3.4 设备前置

先确认设备能被 adb 识别：

```powershell
C:\Program Files\Netease\MuMu\nx_main\adb.exe devices -l
```

如果默认设备当前不在线，任务 Worker 会在执行前自动尝试通过 MuMu CLI 拉起实例并重新 `adb connect`。该行为只适用于 `127.0.0.1:<端口>` 或 `localhost:<端口>` 形式的本机 MuMu 目标，避免误启动 USB 或远程设备；可设置 `ANDROID_UI_AUTO_START_DEVICE=false` 关闭。也可以在 `设备管理` 页面点击 `拉起默认设备` 手动预热设备。

当前 Worker 的设备选择规则：

1. 任务里填写了 `device_serial`，就严格使用该设备。
2. 任务里没填时，如果只连了 1 台设备，则自动使用这 1 台。
3. 目标设备不在线且是可识别的本机 MuMu 地址时，Worker 会在选设备失败后自动拉起并重新检测一次。
4. 如果连了多台设备但任务没指定设备，则执行失败并提示补充 `device_serial`。

## 4. 页面使用流程

### 4.1 创建任务

从左侧 `UI 自动化 > Android 自动化` 进入 Android 工作区，再通过页面标题下方的 `测试任务` 入口进入任务列表。

填写：

- 所属项目
- 任务名称
- 包标识
- 包名称
- APK 下载链接
- 设备序列号（可选）
- 安装超时
- 启动等待时长

### 4.2 发起执行

在任务列表点击 `立即执行`，系统会：

- 新建一条执行记录
- 生成执行编号
- 状态置为 `pending`
- 阶段置为 `queued`

### 4.3 查看结果

进入 `Android 执行记录` 页面后，可以看到：

- 排队中
- 执行中
- 通过
- 失败

详情页可查看：

- 执行编号
- 设备信息
- 每个阶段的字段状态
- APK 路径 / 日志路径 / 截图路径
- 当前焦点窗口
- 异常信息

### 4.4 仙遇悬浮入口的受控打开

`open_xianyu_user_center` 是用于仙遇 SDK 悬浮入口的专用流程步骤。它不会把一次 `adb input tap` 当作页面已打开，而是按以下顺序执行：

1. 用悬浮入口图片定位后点击；
2. 立即等待用户中心标题模板出现；
3. 若未出现，再次点击入口并再次确认标题；
4. 整轮仍未成功时，按“重试次数”重做整轮；`retry_times=2` 表示最多 3 轮；
5. 每次首击、二击、确认成功或失败都会保存 `attempt_screenshot` 产物。

当前仙遇全功能流程已使用该步骤替代原先的固定坐标双击和 2 秒 `sleep`。重试产生的新执行记录会快照当前流程；旧执行记录仍保留其创建时的原始步骤。

## 5. Worker 启动方式

如果你日常是通过项目根目录的 `start_project.bat` 启动后台，现在它会自动尝试拉起：

- `scripts/run_ui_automation_worker.py`
- `scripts/run_android_ui_automation_worker.py`

也就是说，正常本地使用时，不一定需要再额外手动开 Android Worker。

### 5.1 常驻模式

```powershell
.\.venv\Scripts\python.exe scripts/run_android_ui_automation_worker.py
```

用途：

- 持续轮询队列
- 有新任务就自动消费

### 5.2 单次执行模式

```powershell
.\.venv\Scripts\python.exe scripts/run_android_ui_automation_worker.py --once
```

用途：

- 只处理 1 条排队记录
- 没有排队记录则直接退出

### 5.3 指定 run_id 执行

```powershell
.\.venv\Scripts\python.exe scripts/run_android_ui_automation_worker.py --run-id 12
```

用途：

- 本地定点联调某一条执行记录

## 6. Worker 运行目录

运行时目录：

- 心跳状态：`instance/android_ui_automation/worker/status.json`
- 单实例锁：`instance/android_ui_automation/worker/worker.lock`
- 标准输出日志：`instance/android_ui_automation/worker/worker.out.log`
- 标准错误日志：`instance/android_ui_automation/worker/worker.err.log`
- 每次执行产物：`instance/android_ui_automation/runs/<run_id>/`

通过 `start_project.bat` 启动时，脚本会在启动后短暂确认 Worker 进程是否仍在运行；如果启动失败，会直接中止起服并提示查看错误日志。Worker 因未处理异常退出时，`status.json` 会保留 `state: error` 和 `last_error`，用于页面展示和排查。

每次执行目录中通常会有：

- 下载下来的 APK
- `execution.log`
- `launch.png`

## 7. 执行阶段说明

当前约定的阶段流转：

1. `queued`
2. `download`
3. `apk_parse`
4. `install`
5. `launch`
6. `screenshot`
7. `finished`

当前约定的状态：

- `pending`
- `running`
- `passed`
- `failed`

## 8. 成功判定口径

一条执行记录会被判定为 `passed`，需要同时满足：

- APK 下载成功
- `aapt dump badging` 解析成功
- `adb install -r` 成功
- `am start -W -n` 返回成功
- 启动等待后，检测到前台焦点或有效 PID
- 截图成功

如果启动后既没有前台焦点，也没有检测到进程 PID，会按“疑似闪退”处理并标记失败。

## 9. 常见失败类型

### 9.1 缺表

现象：

- Worker 启动后立即提示 Android UI 自动化表未创建

处理：

- 先执行数据库迁移

### 9.2 找不到 adb

现象：

- 提示未找到 adb

处理：

- 检查 `ANDROID_UI_ADB_PATH`
- 确认 `adb.exe` 真实存在

### 9.3 找不到 aapt

现象：

- 提示未找到 aapt

处理：

- 检查 `ANDROID_UI_AAPT_PATH`
- 或改为 Android SDK `build-tools` 里的 `aapt.exe`
- 该依赖校验会在任务执行前完成；缺失时仅当前执行记录失败，常驻 Worker 会保持在线，修复环境后可重新执行该记录

### 9.4 多设备未指定

现象：

- 任务未填 `device_serial`，但当前连了多台设备

处理：

- 给任务补充目标设备序列号

### 9.5 自动拉起 MuMu 失败

现象：

- 执行日志提示“目标设备离线，自动拉起 MuMu 失败”

处理：

- 检查 `ANDROID_UI_AUTO_START_DEVICE` 是否被关闭
- 检查 MuMu CLI 是否与 `ANDROID_UI_ADB_PATH` 位于同一安装目录，或确认默认 MuMu 安装目录存在
- 在 `设备管理` 页面手动拉起默认设备，并以 `adb devices -l` 确认目标显示为 `device`
- 如果启动较慢，增大 `ANDROID_UI_DEVICE_START_WAIT_SECONDS` 后重启 Android Worker

### 9.5 安装失败

常见原因：

- 设备存储不足
- 签名冲突
- 旧包未卸载干净
- APK 本身损坏

排查：

- 看执行详情里的 `install_status`
- 看 `execution.log`
- 手动执行同一条 `adb install -r`

### 9.6 启动失败或疑似闪退

常见原因：

- 入口 Activity 解析不正确
- 游戏启动后立即崩溃
- 首屏拉起时间超出 `launch_wait_sec`

排查：

- 看 `current_focus`
- 看 `pid`
- 手动在设备上打开同一个 APK 复核

## 10. 推荐联调顺序

建议按下面顺序联调：

1. 执行数据库迁移
2. `adb devices -l` 确认设备在线
3. 在页面创建 1 条测试任务
4. 点击 `立即执行`
5. 启动 Worker `scripts/run_android_ui_automation_worker.py --once`
6. 回到执行详情页查看状态、日志路径、截图路径
7. 到 `instance/android_ui_automation/runs/<run_id>/` 复核产物

## 11. 验收清单

### 11.1 功能验收

- 能创建 Android UI 测试任务
- 能编辑、删除任务
- 能手动发起单任务执行
- 能生成执行记录
- 能对失败记录重新执行
- 能在执行记录页看到状态变化
- 能在详情页看到日志路径、截图路径、设备信息

### 11.2 Worker 验收

- Worker 常驻模式可启动
- Worker 单次模式可启动
- Worker 只有一个实例能持锁运行
- Worker 会写入 `status.json`
- Worker 能恢复异常中断遗留的 `running` 记录
- 单条任务因 ADB/AAPT 等依赖缺失失败时，Worker 不会因此退出

### 11.3 设备链路验收

- APK 能下载到本地执行目录
- `aapt` 能解析包名和启动 Activity
- `adb install -r` 成功
- `adb shell am start -W -n` 成功
- 能抓到当前焦点或 PID
- 能产出截图文件

### 11.4 结果验收

- 成功记录标记为 `passed`
- 失败记录标记为 `failed`
- 失败信息能在详情页看到
- `execution.log` 内容完整
- 页面中文文案无乱码

## 12. 后续建议

下一阶段最值得继续补的方向：

1. 在执行记录页展示 Worker 在线状态和当前消费中的 run_id。
2. 详情页直接预览截图，而不是只看路径。
3. 补批量导入和批量执行。
4. 增加 `adb logcat` 截取，提升闪退定位效率。
5. 增加真机 / 模拟器设备池和设备占用保护。
