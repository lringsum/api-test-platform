# Python + Playwright UI 自动化模板

这套模板面向 `Python + Playwright` 的脚本中心型 UI 自动化方案，适合直接拷贝到你的自动化仓库里使用。

## 目录

```text
python_playwright_template/
  requirements.txt
  pytest.ini
  conftest.py
  pages/
  tests/
```

## 安装

```bash
pip install -r requirements.txt
playwright install
```

## 运行

```bash
cd python_playwright_template
set APP_BASE_URL=http://127.0.0.1:5000
set APP_USERNAME=admin
set APP_PASSWORD=admin123
pytest -q
```

如果你是在 macOS / Linux，可以把 `set` 换成 `export`。

如果你想启用 Playwright 的 trace / video / screenshot，可以在命令行加上对应参数，或者后续接入你后台里的执行器统一配置。

## 约定

- 脚本以 `pytest` 作为运行入口
- 页面行为封装在 `pages/`
- 登录态和基础配置放在 `conftest.py`
- 测试文件只写业务流程和断言
- locator 优先使用稳定的 `name`、`role` 或 `testid`
