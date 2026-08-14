from datetime import datetime

from flask import request
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import AuditLog, Permission, Project, ProjectMember, Role, User, role_permissions, user_roles
from app.services.base_service import ServiceError, commit_session, ensure_not_blank


PROJECT_ACCESS_LEVELS = ["viewer", "editor", "executor", "owner"]
RETIRED_PERMISSION_CODES = {"ai:use", "prompt:view", "prompt:create", "prompt:edit", "prompt:delete"}

DEFAULT_PERMISSIONS = [
    {"code": "dashboard:view", "name": "仪表盘查看", "category": "menu", "group_name": "总览", "sort_order": 10},
    {"code": "project:view", "name": "项目查看", "category": "menu", "group_name": "资源配置", "sort_order": 20},
    {"code": "project:create", "name": "项目新建", "category": "action", "group_name": "资源配置", "sort_order": 21},
    {"code": "project:edit", "name": "项目编辑", "category": "action", "group_name": "资源配置", "sort_order": 22},
    {"code": "project:delete", "name": "项目删除", "category": "action", "group_name": "资源配置", "sort_order": 23},
    {"code": "module:view", "name": "模块查看", "category": "menu", "group_name": "资源配置", "sort_order": 30},
    {"code": "module:create", "name": "模块新建", "category": "action", "group_name": "资源配置", "sort_order": 31},
    {"code": "module:edit", "name": "模块编辑", "category": "action", "group_name": "资源配置", "sort_order": 32},
    {"code": "module:delete", "name": "模块删除", "category": "action", "group_name": "资源配置", "sort_order": 33},
    {"code": "environment:view", "name": "环境查看", "category": "menu", "group_name": "资源配置", "sort_order": 40},
    {"code": "environment:create", "name": "环境新建", "category": "action", "group_name": "资源配置", "sort_order": 41},
    {"code": "environment:edit", "name": "环境编辑", "category": "action", "group_name": "资源配置", "sort_order": 42},
    {"code": "environment:delete", "name": "环境删除", "category": "action", "group_name": "资源配置", "sort_order": 43},
    {"code": "variable:view", "name": "变量查看", "category": "menu", "group_name": "资源配置", "sort_order": 50},
    {"code": "variable:create", "name": "变量新建", "category": "action", "group_name": "资源配置", "sort_order": 51},
    {"code": "variable:edit", "name": "变量编辑", "category": "action", "group_name": "资源配置", "sort_order": 52},
    {"code": "variable:delete", "name": "变量删除", "category": "action", "group_name": "资源配置", "sort_order": 53},
    {"code": "testcase:view", "name": "用例查看", "category": "menu", "group_name": "测试设计", "sort_order": 60},
    {"code": "testcase:create", "name": "用例新建", "category": "action", "group_name": "测试设计", "sort_order": 61},
    {"code": "testcase:edit", "name": "用例编辑", "category": "action", "group_name": "测试设计", "sort_order": 62},
    {"code": "testcase:delete", "name": "用例删除", "category": "action", "group_name": "测试设计", "sort_order": 63},
    {"code": "testcase:run", "name": "用例执行", "category": "action", "group_name": "测试设计", "sort_order": 64},
    {"code": "scenario:view", "name": "场景查看", "category": "menu", "group_name": "测试设计", "sort_order": 70},
    {"code": "scenario:create", "name": "场景新建", "category": "action", "group_name": "测试设计", "sort_order": 71},
    {"code": "scenario:edit", "name": "场景编辑", "category": "action", "group_name": "测试设计", "sort_order": 72},
    {"code": "scenario:delete", "name": "场景删除", "category": "action", "group_name": "测试设计", "sort_order": 73},
    {"code": "scenario:run", "name": "场景执行", "category": "action", "group_name": "测试设计", "sort_order": 74},
    {"code": "uiauto:view", "name": "UI 自动化查看", "category": "menu", "group_name": "UI 自动化", "sort_order": 95},
    {"code": "uiauto:script:view", "name": "UI 脚本查看", "category": "menu", "group_name": "UI 自动化", "sort_order": 96},
    {"code": "uiauto:script:create", "name": "UI 脚本创建", "category": "action", "group_name": "UI 自动化", "sort_order": 97},
    {"code": "uiauto:script:edit", "name": "UI 脚本编辑", "category": "action", "group_name": "UI 自动化", "sort_order": 98},
    {"code": "uiauto:script:delete", "name": "UI 脚本删除", "category": "action", "group_name": "UI 自动化", "sort_order": 99},
    {"code": "uiauto:script:run", "name": "UI 脚本执行", "category": "action", "group_name": "UI 自动化", "sort_order": 100},
    {"code": "uiauto:locator:view", "name": "定位器查看", "category": "menu", "group_name": "UI 自动化", "sort_order": 101},
    {"code": "uiauto:locator:manage", "name": "定位器管理", "category": "action", "group_name": "UI 自动化", "sort_order": 102},
    {"code": "android_uiauto:view", "name": "Android UI 自动化查看", "category": "menu", "group_name": "UI 自动化", "sort_order": 103},
    {"code": "android_uiauto:task:create", "name": "Android UI 任务创建", "category": "action", "group_name": "UI 自动化", "sort_order": 104},
    {"code": "android_uiauto:task:edit", "name": "Android UI 任务编辑", "category": "action", "group_name": "UI 自动化", "sort_order": 105},
    {"code": "android_uiauto:task:delete", "name": "Android UI 任务删除", "category": "action", "group_name": "UI 自动化", "sort_order": 106},
    {"code": "android_uiauto:task:run", "name": "Android UI 任务执行", "category": "action", "group_name": "UI 自动化", "sort_order": 107},
    {"code": "android_uiauto:execution:view", "name": "Android UI 执行记录查看", "category": "menu", "group_name": "UI 自动化", "sort_order": 108},
    {"code": "execution:view", "name": "执行查看", "category": "menu", "group_name": "执行与报告", "sort_order": 110},
    {"code": "execution:detail_full", "name": "执行明细全内容", "category": "action", "group_name": "执行与报告", "sort_order": 101},
    {"code": "execution:run", "name": "执行发起", "category": "action", "group_name": "执行与报告", "sort_order": 102},
    {"code": "report:view", "name": "报告查看", "category": "menu", "group_name": "执行与报告", "sort_order": 110},
    {"code": "user:manage", "name": "用户管理", "category": "admin", "group_name": "权限管理", "sort_order": 120},
    {"code": "role:manage", "name": "角色管理", "category": "admin", "group_name": "权限管理", "sort_order": 121},
    {"code": "project_member:manage", "name": "项目成员管理", "category": "admin", "group_name": "权限管理", "sort_order": 122},
    {"code": "audit:view", "name": "审计查看", "category": "admin", "group_name": "权限管理", "sort_order": 123},
]

DEFAULT_ROLES = [
    {
        "code": "admin",
        "name": "超级管理员",
        "description": "拥有全部菜单、按钮和数据范围权限",
        "is_system": True,
        "sort_order": 10,
        "permissions": [item["code"] for item in DEFAULT_PERMISSIONS],
    },
    {
        "code": "manager",
        "name": "测试负责人",
        "description": "负责项目配置、用例设计和执行管理",
        "is_system": True,
        "sort_order": 20,
        "permissions": [
            "dashboard:view",
            "project:view",
            "module:view",
            "environment:view",
            "variable:view",
            "testcase:view",
            "testcase:create",
            "testcase:edit",
            "testcase:delete",
            "testcase:run",
            "scenario:view",
            "scenario:create",
            "scenario:edit",
            "scenario:delete",
            "scenario:run",
            "uiauto:view",
            "uiauto:script:view",
            "uiauto:script:create",
            "uiauto:script:edit",
            "uiauto:script:delete",
            "uiauto:script:run",
            "uiauto:locator:view",
            "uiauto:locator:manage",
            "android_uiauto:view",
            "android_uiauto:task:create",
            "android_uiauto:task:edit",
            "android_uiauto:task:delete",
            "android_uiauto:task:run",
            "android_uiauto:execution:view",
            "execution:view",
            "execution:detail_full",
            "execution:run",
            "report:view",
            "project_member:manage",
        ],
    },
    {
        "code": "member",
        "name": "测试人员",
        "description": "可查看项目并进行日常设计、执行与报告查看",
        "is_system": True,
        "sort_order": 30,
        "permissions": [
            "dashboard:view",
            "project:view",
            "module:view",
            "environment:view",
            "variable:view",
            "testcase:view",
            "testcase:create",
            "testcase:edit",
            "testcase:run",
            "scenario:view",
            "scenario:create",
            "scenario:edit",
            "scenario:run",
            "uiauto:view",
            "uiauto:script:view",
            "uiauto:script:create",
            "uiauto:script:edit",
            "uiauto:script:run",
            "uiauto:locator:view",
            "android_uiauto:view",
            "android_uiauto:task:create",
            "android_uiauto:task:edit",
            "android_uiauto:task:run",
            "android_uiauto:execution:view",
            "execution:view",
            "execution:detail_full",
            "execution:run",
            "report:view",
        ],
    },
    {
        "code": "viewer",
        "name": "只读访客",
        "description": "仅查看项目与报告，不能编辑",
        "is_system": True,
        "sort_order": 40,
        "permissions": [
            "dashboard:view",
            "project:view",
            "module:view",
            "environment:view",
            "variable:view",
            "testcase:view",
            "scenario:view",
            "uiauto:view",
            "uiauto:script:view",
            "uiauto:locator:view",
            "android_uiauto:view",
            "android_uiauto:execution:view",
            "execution:view",
            "report:view",
        ],
    },
]


def _normalize_username(username):
    return ensure_not_blank(username, "用户名").lower()


def _normalize_role_codes(role_codes):
    if not role_codes:
        return []
    if isinstance(role_codes, str):
        role_codes = [role_codes]
    return [str(item).strip() for item in role_codes if str(item).strip()]


class SecurityService:
    @staticmethod
    def ensure_default_data():
        created = False

        retired_permissions = Permission.query.filter(
            Permission.code.in_(RETIRED_PERMISSION_CODES)
        ).all()
        for permission in retired_permissions:
            permission.roles = []
            db.session.delete(permission)
            created = True
        if retired_permissions:
            db.session.flush()

        permissions_by_code = {item.code: item for item in Permission.query.all()}
        for item in DEFAULT_PERMISSIONS:
            if item["code"] not in permissions_by_code:
                db.session.add(Permission(**item))
                created = True
        if created:
            db.session.flush()
            permissions_by_code = {item.code: item for item in Permission.query.all()}

        for item in DEFAULT_ROLES:
            role = Role.query.filter_by(code=item["code"]).first()
            if not role:
                role = Role(
                    code=item["code"],
                    name=item["name"],
                    description=item["description"],
                    is_system=item["is_system"],
                    sort_order=item["sort_order"],
                )
                db.session.add(role)
                created = True
            else:
                if role.name != item["name"]:
                    role.name = item["name"]
                    created = True
                if role.description != item["description"]:
                    role.description = item["description"]
                    created = True
                if role.is_system != item["is_system"]:
                    role.is_system = item["is_system"]
                    created = True
                if role.sort_order != item["sort_order"]:
                    role.sort_order = item["sort_order"]
                    created = True

            desired_permissions = [
                permissions_by_code[code]
                for code in item["permissions"]
                if code in permissions_by_code
            ]
            current_codes = [permission.code for permission in role.permissions]
            desired_codes = [permission.code for permission in desired_permissions]
            if current_codes != desired_codes:
                role.permissions = desired_permissions
                created = True

        if User.query.count() == 0:
            admin = User(
                username="admin",
                display_name="管理员",
                email="admin@example.com",
                password_hash=generate_password_hash("admin123"),
                is_active=True,
                is_superuser=True,
                last_login_at=None,
            )
            db.session.add(admin)
            db.session.flush()

            admin_role = Role.query.filter_by(code="admin").first()
            if admin_role:
                admin.roles.append(admin_role)
            created = True

        if created:
            commit_session()

    @staticmethod
    def authenticate(username, password):
        username = _normalize_username(username)
        password = ensure_not_blank(password, "密码")

        user = User.query.filter_by(username=username).first()
        if not user or not user.is_active:
            raise ServiceError("用户名或密码错误。")

        if not check_password_hash(user.password_hash, password):
            raise ServiceError("用户名或密码错误。")

        user.last_login_at = datetime.utcnow()
        commit_session()
        return user

    @staticmethod
    def get_user_by_id(user_id):
        user = db.session.get(User, user_id)
        if not user:
            raise ServiceError("用户不存在。")
        return user

    @staticmethod
    def get_user_by_username(username):
        return User.query.filter_by(username=_normalize_username(username)).first()

    @staticmethod
    def list_users():
        return User.query.order_by(User.created_at.desc()).all()

    @staticmethod
    def list_roles():
        return Role.query.order_by(Role.sort_order.asc(), Role.created_at.asc()).all()

    @staticmethod
    def list_permissions():
        return Permission.query.order_by(Permission.group_name.asc(), Permission.sort_order.asc()).all()

    @staticmethod
    def list_project_members(project_id=None):
        query = ProjectMember.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        return query.order_by(ProjectMember.created_at.desc()).all()

    @staticmethod
    def list_audit_logs(page=1, per_page=20, project_id=None):
        query = AuditLog.query
        if project_id:
            query = query.filter_by(project_id=project_id)
        return query.order_by(AuditLog.created_at.desc()).paginate(
            page=page,
            per_page=per_page,
            error_out=False,
        )

    @staticmethod
    def create_user(username, display_name="", email="", password="", is_active=True, is_superuser=False, role_codes=None):
        username = _normalize_username(username)
        display_name = str(display_name or "").strip()
        email = str(email or "").strip()
        password = ensure_not_blank(password, "密码")
        role_codes = _normalize_role_codes(role_codes)

        if User.query.filter_by(username=username).first():
            raise ServiceError("用户名已存在。")
        if email and User.query.filter_by(email=email).first():
            raise ServiceError("邮箱已存在。")

        user = User(
            username=username,
            display_name=display_name,
            email=email,
            password_hash=generate_password_hash(password),
            is_active=bool(is_active),
            is_superuser=bool(is_superuser),
        )
        if role_codes:
            user.roles = SecurityService._load_roles_by_codes(role_codes)

        db.session.add(user)
        commit_session()
        return user

    @staticmethod
    def update_user(user_id, username, display_name="", email="", password="", is_active=True, is_superuser=False, role_codes=None):
        user = SecurityService.get_user_by_id(user_id)
        username = _normalize_username(username)
        display_name = str(display_name or "").strip()
        email = str(email or "").strip()
        role_codes = _normalize_role_codes(role_codes)

        exists = User.query.filter(User.username == username, User.id != user_id).first()
        if exists:
            raise ServiceError("用户名已存在。")
        if email:
            exists = User.query.filter(User.email == email, User.id != user_id).first()
            if exists:
                raise ServiceError("邮箱已存在。")

        user.username = username
        user.display_name = display_name
        user.email = email
        user.is_active = bool(is_active)
        user.is_superuser = bool(is_superuser)
        if password:
            user.password_hash = generate_password_hash(ensure_not_blank(password, "密码"))
        user.roles = SecurityService._load_roles_by_codes(role_codes)
        commit_session()
        return user

    @staticmethod
    def set_user_roles(user_id, role_codes):
        user = SecurityService.get_user_by_id(user_id)
        user.roles = SecurityService._load_roles_by_codes(_normalize_role_codes(role_codes))
        commit_session()
        return user

    @staticmethod
    def create_role(code, name, description="", is_system=False, sort_order=0, permission_codes=None):
        code = ensure_not_blank(code, "角色编码").lower()
        name = ensure_not_blank(name, "角色名称")
        description = str(description or "").strip()
        permission_codes = _normalize_role_codes(permission_codes)

        if Role.query.filter_by(code=code).first():
            raise ServiceError("角色编码已存在。")

        role = Role(
            code=code,
            name=name,
            description=description,
            is_system=bool(is_system),
            sort_order=int(sort_order or 0),
        )
        role.permissions = SecurityService._load_permissions_by_codes(permission_codes)
        db.session.add(role)
        commit_session()
        return role

    @staticmethod
    def update_role(role_id, code, name, description="", is_system=False, sort_order=0, permission_codes=None):
        role = SecurityService.get_role_by_id(role_id)
        code = ensure_not_blank(code, "角色编码").lower()
        name = ensure_not_blank(name, "角色名称")
        description = str(description or "").strip()
        permission_codes = _normalize_role_codes(permission_codes)

        exists = Role.query.filter(Role.code == code, Role.id != role_id).first()
        if exists:
            raise ServiceError("角色编码已存在。")

        role.code = code
        role.name = name
        role.description = description
        role.is_system = bool(is_system)
        role.sort_order = int(sort_order or 0)
        role.permissions = SecurityService._load_permissions_by_codes(permission_codes)
        commit_session()
        return role

    @staticmethod
    def get_role_by_id(role_id):
        role = db.session.get(Role, role_id)
        if not role:
            raise ServiceError("角色不存在。")
        return role

    @staticmethod
    def get_permission_by_code(code):
        permission = Permission.query.filter_by(code=code).first()
        if not permission:
            raise ServiceError("权限不存在。")
        return permission

    @staticmethod
    def update_project_member(project_id, user_id, access_level="viewer", remark=""):
        access_level = ensure_not_blank(access_level, "访问级别").lower()
        if access_level not in PROJECT_ACCESS_LEVELS:
            raise ServiceError("访问级别非法。")

        project = db.session.get(Project, project_id)
        if not project:
            raise ServiceError("项目不存在。")
        user = db.session.get(User, user_id)
        if not user:
            raise ServiceError("用户不存在。")

        member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
        if not member:
            member = ProjectMember(
                project_id=project_id,
                user_id=user_id,
                access_level=access_level,
                remark=str(remark or "").strip(),
            )
            db.session.add(member)
        else:
            member.access_level = access_level
            member.remark = str(remark or "").strip()

        commit_session()
        return member

    @staticmethod
    def remove_project_member(project_id, user_id):
        member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
        if not member:
            raise ServiceError("项目成员不存在。")
        db.session.delete(member)
        commit_session()
        return True

    @staticmethod
    def record_audit(action, resource_type="", resource_id=None, project_id=None, detail=None, user=None):
        user = user or getattr(request, "current_user", None)
        if user is None:
            from flask import g

            user = getattr(g, "current_user", None)

        audit = AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else "",
            action=ensure_not_blank(action, "审计动作"),
            resource_type=str(resource_type or "").strip(),
            resource_id=resource_id,
            project_id=project_id,
            ip_address=(request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip(),
        )
        audit.detail = detail or {}
        db.session.add(audit)
        commit_session()
        return audit

    @staticmethod
    def _load_permissions_by_codes(permission_codes):
        if not permission_codes:
            return []
        return Permission.query.filter(Permission.code.in_(permission_codes)).all()

    @staticmethod
    def _load_roles_by_codes(role_codes):
        if not role_codes:
            return []
        return Role.query.filter(Role.code.in_(role_codes)).all()
