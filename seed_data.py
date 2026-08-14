from app import create_app, db
from app.models import Environment, Module, Project, TestCase, Variable


app = create_app()


def seed():
    with app.app_context():
        if Project.query.first():
            print("示例数据已存在，跳过初始化。")
            return

        project = Project(
            name="示例接口测试平台",
            description="用于演示接口自动化测试平台完整流程",
            status="active",
        )
        db.session.add(project)
        db.session.flush()

        login_module = Module(
            project_id=project.id,
            name="登录模块",
            description="登录和认证相关接口",
        )
        user_module = Module(
            project_id=project.id,
            name="用户模块",
            description="用户信息查询相关接口",
        )
        db.session.add_all([login_module, user_module])
        db.session.flush()

        env = Environment(
            project_id=project.id,
            name="本地测试环境",
            base_url="http://127.0.0.1:5001",
            description="本地联调用测试环境",
            is_active=True,
        )
        env.headers = {
            "Content-Type": "application/json"
        }
        env.variables_data = {
            "tenant_code": "test"
        }
        db.session.add(env)
        db.session.flush()

        variables = [
            Variable(
                project_id=project.id,
                environment_id=None,
                name="username",
                value="admin",
                scope="project",
                description="登录用户名",
            ),
            Variable(
                project_id=project.id,
                environment_id=None,
                name="password",
                value="123456",
                scope="project",
                description="登录密码",
            ),
            Variable(
                project_id=project.id,
                environment_id=env.id,
                name="user_id",
                value="1001",
                scope="environment",
                description="测试用户ID",
            ),
        ]
        db.session.add_all(variables)

        login_case = TestCase(
            project_id=project.id,
            module_id=login_module.id,
            name="登录成功",
            description="登录接口成功场景",
            source="manual",
            is_active=True,
            case_data="{}",
        )
        login_case.data = {
            "name": "登录成功",
            "method": "POST",
            "url": "/api/login",
            "headers": {},
            "params": {},
            "body": {
                "username": "${username}",
                "password": "${password}"
            },
            "extract": {
                "token": "data.token"
            },
            "assertions": [
                {
                    "type": "status_code",
                    "expected": 200
                },
                {
                    "type": "json_path",
                    "path": "code",
                    "expected": 0
                },
                {
                    "type": "contains",
                    "expected": "success"
                }
            ]
        }

        user_case = TestCase(
            project_id=project.id,
            module_id=user_module.id,
            name="查询用户信息",
            description="依赖 token 查询用户信息",
            source="manual",
            is_active=True,
            case_data="{}",
        )
        user_case.data = {
            "name": "查询用户信息",
            "method": "GET",
            "url": "/api/user/${user_id}",
            "headers": {
                "Authorization": "Bearer ${token}"
            },
            "params": {},
            "body": {},
            "extract": {},
            "assertions": [
                {
                    "type": "status_code",
                    "expected": 200
                },
                {
                    "type": "response_time",
                    "expected": 3000
                }
            ]
        }

        db.session.add_all([login_case, user_case])
        db.session.commit()
        print("示例数据初始化完成。")


if __name__ == "__main__":
    seed()
