# API Test Platform AI Development Knowledge Base

## 1. Purpose

This document is the working knowledge base for future AI-driven development on this repository.

Goal:

- let a new AI understand the real system shape quickly
- reduce requirement drift during iteration
- make code changes based on actual runtime behavior, not directory-name guesses

This document describes the code as it exists now in the repository on June 17, 2026.

## 2. Project Snapshot

- Project type: monolithic Flask web application
- Main domains:
  - API test case management and execution
  - scenario orchestration
  - AI-assisted API test case generation
  - UI automation script management and execution
  - RBAC + project membership + audit log
- Backend stack:
  - Flask
  - Flask-SQLAlchemy / SQLAlchemy
  - requests
  - pytest / playwright for UI automation
- Frontend stack:
  - server-rendered Jinja templates
  - Bootstrap 5
  - plain JavaScript
- Default database:
  - local SQLite only
  - file path: `instance/app.db`

Important runtime fact:

- the Flask app serves static assets from `public/`, not from `app/static/`
- `app/static/` currently looks like a stale duplicate and is not the active runtime static directory

## 3. Real Entry Points

### 3.1 App startup

- `run.py`
  - imports `create_app()`
  - runs Flask with `HOST`, `PORT`, `DEBUG`
- `api/index.py`
  - alternate app entry, likely for deployment adapters such as Vercel-style hosting

### 3.2 App factory

- `app/__init__.py`
  - creates Flask app
  - sets `instance_path`
  - sets `static_folder=os.path.join(project_root, "public")`
  - loads config from `config.py`
  - initializes SQLAlchemy
  - auto-runs `db.create_all()`
  - auto-adds missing column `runtime_variables_json` to `ui_automation_environments`
  - auto-seeds default security data via `SecurityService.ensure_default_data()`
  - registers all blueprints
  - installs `before_request` hooks for auth and project context

### 3.3 Config

- `config.py`
  - SQLite database path is always local
  - OpenAI config exists but API parser and UI script generation only partially use it
  - notable settings:
    - `AI_MODE`
    - `DEFAULT_TIMEOUT`
    - `UI_AUTOMATION_RUN_TIMEOUT`
    - `OPENAI_*`

## 4. High-Level Architecture

The app is a classic layered Flask monolith:

1. Routes / blueprints
2. Services
3. Models
4. Utilities
5. Templates + `public/` assets

Operationally, there are four major business subsystems:

1. API test design
2. API execution engine
3. scenario orchestration
4. UI automation center

Cross-cutting subsystems:

1. authentication and authorization
2. active project context
3. audit log
4. AI assistance

## 5. Repository Map

### 5.1 Core directories

- `app/`
  - Flask app package
- `app/routes/`
  - all web routes and JSON endpoints
- `app/services/`
  - business logic layer
- `app/models.py`
  - all database models in one file
- `app/utils/`
  - execution helpers and generic utilities
- `app/templates/`
  - Jinja pages
- `public/`
  - active CSS/JS static assets
- `scripts/`
  - regression gates, worker launcher, migration helpers
- `docs/`
  - design docs and supporting references
- `instance/`
  - runtime data, especially SQLite DB and UI automation run artifacts

### 5.2 Files that matter most for future development

- `app/__init__.py`
- `app/models.py`
- `app/security.py`
- `app/project_context.py`
- `app/services/base_service.py`
- `app/services/execution_service.py`
- `app/services/scenario_execution_service.py`
- `app/services/ui_automation_service.py`
- `app/services/ui_automation_worker.py`
- `app/routes/ui_automation.py`
- `app/routes/execution.py`
- `app/routes/testcase.py`
- `public/js/app.js`
- `public/css/app.css`

## 6. Cross-Cutting Runtime Rules

## 6.1 Authentication

- login state is stored in session key `user_id`
- unauthenticated users are redirected to `/login`
- most routes rely on `before_request` plus route-level permission decorators
- auth helpers live in:
  - `app/security.py`
  - `app/services/security_service.py`

### 6.2 Authorization

The system combines two layers:

1. role permissions
2. project membership access

Role permissions:

- menu/action/admin style codes, such as:
  - `project:view`
  - `testcase:run`
  - `uiauto:script:edit`
  - `audit:view`

Project access:

- stored in `project_members`
- access levels:
  - `viewer`
  - `editor`
  - `executor`
  - `owner`

Important:

- a user can have role permission and still be blocked by project access
- many changes must respect both permission code and project membership scope

### 6.3 Active project context

This is a major behavior anchor.

- current project is stored in session key `active_project_id`
- request `?project_id=...` can switch it
- helper module: `app/project_context.py`
- helpers in `app/security.py` validate whether the current user can access the selected project

Impact:

- many pages and APIs are implicitly scoped by the active project
- changing filters, page links, and form targets without preserving `project_id` can cause subtle behavior drift

### 6.4 Audit log

- security actions and some admin operations write to `audit_logs`
- service entry: `SecurityService.record_audit`

When adding admin/security-sensitive flows, writing audit records is consistent with existing design.

## 7. Data Model Map

All models live in `app/models.py`.

### 7.1 Security and governance

- `User`
- `Role`
- `Permission`
- `ProjectMember`
- `AuditLog`
- join tables:
  - `user_roles`
  - `role_permissions`

### 7.2 API testing domain

- `Project`
- `Module`
- `Environment`
- `Variable`
- `TestCase`
- `PromptTemplate`
- `Execution`
- `ExecutionDetail`
- `Report`
- `Scenario`
- `ScenarioStep`
- `ScenarioExecution`
- `ScenarioExecutionDetail`

### 7.3 UI automation domain

- `UiAutomationScript`
- `UiAutomationScriptVersion`
- `UiAutomationEnvironment`
- `UiAutomationLocator`
- `UiAutomationRun`
- `UiAutomationRunStep`
- `UiAutomationArtifact`
- `UiAutomationAIRecord`

### 7.4 Modeling conventions

- most JSON-ish fields are stored as `TEXT`
- model properties expose parsed data, for example:
  - `Environment.headers`
  - `Environment.variables_data`
  - `TestCase.data`
  - `Execution.summary`
  - `ScenarioStep.request_overrides`
  - `UiAutomationRun.summary`
- there is no migration framework in active use
- schema evolution is partly manual and partly app-startup patching

Implication for AI:

- do not assume Alembic or Flask-Migrate exists
- any schema change must include an explicit migration strategy

## 8. Business Subsystem: API Test Design

### 8.1 Core entities

- Project -> Module -> TestCase
- Project -> Environment
- Project -> Variable
- Project -> Scenario -> ScenarioStep -> TestCase

### 8.2 Test case schema contract

Validation lives in `app/services/base_service.py` via `validate_case_schema`.

Supported structure includes:

- `name`
- `method`
- `url`
- `headers`
- `params`
- `body`
- `extract`
- `assertions`
- optional:
  - `files`
  - `body_type`
  - `pre_script`

Current method support:

- `GET`
- `POST`

Current assertion types:

- `status_code`
- `json_path`
- `contains`
- `response_time`

Current body types:

- `json`
- `form`
- `multipart`

Important:

- future support for PUT/DELETE/PATCH is not present in schema validation today
- adding those methods requires coordinated changes in validation, UI, AI generation, and regression expectations

### 8.3 Variables

Variable resolution is one of the most important runtime behaviors.

Source layers:

1. project-level variables from `variables` table
2. environment JSON variables from `Environment.variables_json`
3. environment-level variables from `variables` table
4. runtime extracted variables from previous execution steps
5. pre-script runtime mutations

Resolution syntax:

- `${var_name}`

Resolver:

- `app/utils/variable_resolver.py`

Behavior:

- unresolved variable raises `ServiceError`
- environment-level table variables override environment JSON variables
- extracted variables can be persisted back into environment scope

### 8.4 Pre-script

API test cases can include `pre_script`.

Execution service:

- `app/services/pre_script_service.py`

What it does:

- executes restricted Python against request headers/params/body/runtime vars
- exposes helper functions such as:
  - `md5`
  - `sha256`
  - `base64_encode`
  - `timestamp`
  - `uuid4`
  - JSON helpers

Restrictions:

- blocks imports, file access, subprocess, requests, os/sys access, eval/exec-like patterns

Important:

- this is a local sandbox by convention, not a hardened security boundary
- if future requirements expand pre-script power, security review is required

## 9. Business Subsystem: API Execution Engine

Main service:

- `app/services/execution_service.py`

### 9.1 Execution flow

Single or batch execution roughly does:

1. validate target object and active environment
2. build runtime variables
3. build request snapshot
4. apply pre-script if enabled
5. call `requests.request(...)`
6. capture response snapshot
7. run assertions
8. extract variables
9. persist execution detail
10. optionally persist extracted values back to environment variables
11. compute execution summary
12. auto-generate report

### 9.2 Request build path

- `app/utils/request_builder.py`
  - resolves headers/params/body/files/path
  - merges environment headers with testcase headers
  - builds full URL using environment `base_url`

### 9.3 Assertion path

- `app/utils/assertion_engine.py`

### 9.4 Extract path

- `app/utils/extractor.py`

### 9.5 Persistence side effects

Execution is not read-only.

Side effects:

- creates `Execution`
- creates `ExecutionDetail`
- may create/update environment-scoped `Variable` records from extracted values
- creates `Report`

Important:

- replaying the same suite can mutate environment-level variables
- this matters when debugging inconsistent downstream results

## 10. Business Subsystem: Scenario Orchestration

Main services:

- `app/services/scenario_service.py`
- `app/services/scenario_execution_service.py`

### 10.1 Scenario model

A scenario is an ordered set of steps pointing to test cases.

Each step can define:

- `setup_variables`
- `request_overrides`
- `extract_overrides`
- `assertion_overrides`
- `continue_on_failure`
- `is_enabled`

### 10.2 Scenario execution behavior

Runtime flow:

1. load active environment
2. build runtime variables
3. apply global runtime injections if any
4. iterate enabled steps in order
5. inject step variables into runtime
6. merge step overrides into testcase schema
7. execute via `ExecutionService.execute_case(...)`
8. write `ScenarioExecutionDetail`
9. optionally persist extracted values
10. stop early unless `continue_on_failure=True`

Final statuses:

- `passed`
- `partial_success`
- `failed`

Important:

- scenario execution reuses the API execution engine rather than duplicating it
- if changing API execution behavior, check scenario behavior too

## 11. Business Subsystem: AI API Parser

Main services:

- `app/services/ai_service.py`
- `app/services/prompt_service.py`
- `app/utils/ai_mock.py`

### 11.1 Current reality

The AI API parser is only fully implemented in mock mode.

Modes:

- `AI_MODE=mock`
  - works
  - builds synthetic case data from document text
- `AI_MODE=real`
  - placeholder only
  - raises not-implemented style service error

### 11.2 Prompt behavior

- prompt templates are stored in DB
- active template is the latest updated `is_active=True` template
- `{{document}}` placeholder is replaced in prompt text

Important:

- do not assume API document parsing is production-grade LLM integration yet
- future real-model work must cover:
  - request calling
  - response parsing
  - schema validation
  - failure handling
  - tests

## 12. Business Subsystem: UI Automation Center

This is a substantial second product area inside the same Flask app.

Main files:

- `app/routes/ui_automation.py`
- `app/services/ui_automation_service.py`
- `app/services/ui_automation_worker.py`
- `app/services/ui_automation_ai_service.py`

### 12.1 Responsibilities

UI automation includes:

- script management
- script versioning
- AI script generation
- AI script repair
- locator repository
- execution planning
- worker execution
- artifacts
- replay/detail pages

### 12.2 Script storage model

- script metadata in `UiAutomationScript`
- actual executable content in `UiAutomationScriptVersion`
- current active version referenced by `current_version_id`
- updates create new versions rather than in-place overwrite

Important:

- every script edit is versioned
- future code changes must preserve this version-history model

### 12.3 Locator repository

Locators are first-class records.

Supported locator types:

- `role`
- `label`
- `placeholder`
- `text`
- `testid`
- `css`
- `xpath`
- `custom`

Special AI-side policy already exists:

- new saved UI locators are expected to prefer unique XPath when generated from AI guidance

### 12.4 UI automation execution model

Execution planning:

- `UiAutomationService.create_run(...)` creates a queued run record

Execution runtime:

- `UiAutomationWorker.execute_run(run_id)` performs actual execution

Worker flow:

1. validate local runtime dependencies
2. create workspace under `instance/ui_automation/runs/<run_id>/`
3. materialize script into `test_script.py`
4. write dynamic `conftest.py`
5. inject runtime recorder helper
6. run pytest + playwright subprocess
7. capture logs, screenshots, trace, video, reports
8. register artifacts in DB
9. synthesize or persist run steps
10. compute failure analysis summary

### 12.5 Run artifact layout

Artifacts live on disk under:

- `instance/ui_automation/runs/<run_id>/...`

Registered in DB as:

- `UiAutomationArtifact`

Artifact types include:

- `log`
- `steps`
- `script`
- `config`
- `trace`
- `screenshot`
- `video`
- `report`

### 12.6 Runtime step recorder

The worker dynamically writes a `ui_step_recorder.py` helper into the run workspace.

It monkey-patches Playwright sync APIs to record:

- step type
- title
- locator
- input value
- expected value
- status
- duration
- error
- step screenshot

Important:

- this instrumentation is generated at runtime, not stored as a committed module
- if changing UI worker behavior, check both step persistence and replay rendering

### 12.7 UI automation AI

Main service:

- `app/services/ui_automation_ai_service.py`

Capabilities:

- generate script from structured context
- repair script from failed run
- record AI prompts/outputs in `UiAutomationAIRecord`

Current modes:

- `mock`
  - generates deterministic local script text
- `real`
  - actually calls OpenAI-compatible `/chat/completions`

This differs from the API parser subsystem:

- UI automation AI real mode is implemented
- API parser real mode is not

That asymmetry is important and easy to miss.

## 13. Route Map

### 13.1 Human-facing pages

- `/login`
- `/`
- `/projects/`
- `/modules/`
- `/environments/`
- `/variables/`
- `/testcases/`
- `/scenarios/`
- `/executions/run`
- `/executions/history`
- `/reports/`
- `/prompts/`
- `/ui-automation/...`
- `/admin/...`

### 13.2 JSON / API-style endpoints

Main examples:

- `/ai/api/parse`
- `/ai/api/validate`
- `/ai/api/save-testcase`
- `/executions/api/run/options`
- `/executions/api/run/testcase/<id>`
- `/executions/api/run/module/<id>`
- `/executions/api/run/selection`
- `/executions/api/run/project/<id>`
- `/executions/api/details/<detail_id>`
- `/testcases/api/validate-json`

### 13.3 Route design style

- server-rendered pages for CRUD and dashboards
- JSON endpoints for AJAX execution and validation actions
- route layer is intentionally thin and usually delegates to services

## 14. Frontend and Asset Reality

### 14.1 Active assets

Active runtime assets are:

- `public/css/app.css`
- `public/js/app.js`

They are loaded through:

- `url_for('static', filename='css/app.css')`
- `url_for('static', filename='js/app.js')`

because Flask `static_folder` points to `public/`.

### 14.2 Soft navigation

`public/js/app.js` implements lightweight client-side soft navigation for:

- sidebar links
- project switch form
- some GET filter forms

Behavior:

- fetches full HTML
- swaps `.sidebar`, `.topbar`, `.content-area`
- updates history with `pushState`

Important:

- page interactions must be re-initialized after soft navigation
- when adding new page JS behavior, integrate with `initPageInteractions(...)`
- do not assume a full browser reload after every link click

### 14.3 Template layout

Main shell:

- `app/templates/base.html`

Notable behavior:

- left sidebar depends on `has_permission(...)`
- topbar includes current user
- project selector is global
- static asset versions are query-string based

## 15. Regression and Support Scripts

### 15.1 Main scripts

- `scripts/run_ui_regression.py`
  - orchestrates route gate + browser gate + API gate
- `scripts/test_ui_routes.py`
  - checks route rendering markers
- `scripts/test_ui_browser.py`
  - browser-level UI smoke/anomaly tests
- `scripts/test_api_gate.py`
  - JSON endpoint gate tests
- `scripts/run_ui_automation_worker.py`
  - worker launcher helper
- `scripts/migrate_sqlite_to_postgres.py`
  - migration utility, but runtime app itself is SQLite-only

### 15.2 Regression registry

- `scripts/ui_regression_registry.py`
  - central registry of page specs and API scenarios

Important:

- if a page title, marker, or route changes, update this registry too
- otherwise regression scripts will drift from the product behavior

## 16. Seed Data and Default State

### 16.1 Security bootstrap

At startup:

- default permissions are created if missing
- default roles are created/updated if missing
- default admin user is created if no users exist

Default admin:

- username: `admin`
- password: `admin123`

### 16.2 Demo seed

- `seed_data.py`
  - inserts sample project/module/environment/variable/prompt/test cases

Important:

- app startup does not run `seed_data.py`
- it only ensures security defaults

## 17. Known Realities and Drift Risks

### 17.1 Static asset trap

`public/` is live.

`app/static/` appears duplicated but inactive for runtime. Future CSS/JS changes should normally target `public/`.

### 17.2 Schema migration trap

There is no formal migration system in active use.

If a model changes:

- DB compatibility must be planned manually
- startup patching may be needed
- existing SQLite databases may otherwise break silently

### 17.3 Execution side-effect trap

API execution can mutate environment variables through extracted values.

This means:

- test reruns are stateful
- scenario chains may depend on previous extracted values

### 17.4 Encoding trap

Some command-line outputs show garbled Chinese text depending on terminal encoding, but repository content is not uniformly broken. Avoid mass "encoding cleanup" unless the user explicitly asks for it and runtime rendering is proven wrong.

### 17.5 Permission + project trap

A UI change may look local but still break because:

- page menu visibility is permission-driven
- project scope is session-driven
- route results depend on accessible project IDs

### 17.6 Dual AI subsystem trap

The repository has two different AI areas:

1. API parser AI
2. UI automation AI

They do not have the same implementation maturity.

- API parser real mode: not implemented
- UI automation real mode: implemented

Do not generalize behavior from one subsystem to the other.

### 17.7 Monolithic model trap

All models live in one file. Large refactors here have broad blast radius across routes, services, and templates.

## 18. Recommended Change Playbook for Future AI

When implementing a new requirement, use this sequence:

1. identify the business subsystem first
2. locate the page route and service entry
3. inspect related models and JSON field contracts
4. check active project context usage
5. check permission codes used by the page/action
6. confirm whether the feature has regression script coverage
7. update backend behavior before template polish
8. if UI is involved, edit `public/` assets, not inactive duplicates
9. verify data side effects, especially extracted variables and artifacts
10. update this document when the architecture truth changes

## 19. Requirement Anti-Drift Rules

Future AI work should follow these rules:

1. Do not infer active static assets from directory names; verify Flask `static_folder`.
2. Do not add new API request methods without updating validation, UI, AI generation, and tests together.
3. Do not change execution behavior without checking both direct execution and scenario execution.
4. Do not change UI automation run behavior without checking replay pages and artifact registration.
5. Do not treat environment variables as read-only configuration; they may be mutated by execution.
6. Do not assume one AI subsystem reflects the implementation state of the other.
7. Do not introduce schema changes without a database transition plan.
8. Do not bypass project membership checks when adding new project-scoped routes.
9. Do not add page-level JS that only works on hard reload; soft navigation re-init must be handled.
10. Do not "clean up" duplicated directories or encoding artifacts unless runtime behavior proves they are safe to remove.

## 20. Suggested First Files to Read for Any New Task

If a future AI only has time to read a few files, read these first:

1. `app/__init__.py`
2. `app/models.py`
3. `app/security.py`
4. `app/project_context.py`
5. `app/services/base_service.py`
6. the route file for the target feature
7. the paired service file for the target feature
8. `public/js/app.js` if the task touches navigation or UI behavior

## 21. Maintenance Note

This document should be updated whenever any of the following change:

- static asset source directory
- auth/permission model
- active project scoping rules
- test case schema
- execution engine behavior
- UI automation worker architecture
- database migration strategy
- AI subsystem implementation status

