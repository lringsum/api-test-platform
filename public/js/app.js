function prettyJson(value) {
    try {
        if (typeof value === "string") {
            value = JSON.parse(value);
        }
        return JSON.stringify(value, null, 2);
    } catch (e) {
        return typeof value === "string" ? value : String(value);
    }
}

function showResultText(elementId, value) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = typeof value === "string" ? value : prettyJson(value);
}

async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(payload || {})
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.message || "请求失败");
    }
    return data;
}

document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        const globalSearch = document.getElementById("globalSearch");
        if (!globalSearch) return;
        event.preventDefault();
        globalSearch.focus();
        globalSearch.select();
    }
});

function initVariableScopeToggles(root = document) {
    const toggleEnvironmentSelect = (scopeEl, envEl) => {
        if (!scopeEl || !envEl) return;
        const isEnvScope = scopeEl.value === "environment";
        envEl.disabled = !isEnvScope;
        if (!isEnvScope) {
            envEl.value = "";
        }
    };

    const createScope = root.querySelector("#createScope");
    const createEnv = root.querySelector("#createEnvironmentId");
    if (createScope && createEnv && !createScope.dataset.softNavBound) {
        createScope.dataset.softNavBound = "true";
        toggleEnvironmentSelect(createScope, createEnv);
        createScope.addEventListener("change", () => toggleEnvironmentSelect(createScope, createEnv));
    }

    root.querySelectorAll(".edit-scope").forEach((scopeEl) => {
        if (scopeEl.dataset.softNavBound) return;
        const targetId = scopeEl.getAttribute("data-target");
        const envEl = targetId ? root.querySelector(`#${CSS.escape(targetId)}`) : null;
        scopeEl.dataset.softNavBound = "true";
        toggleEnvironmentSelect(scopeEl, envEl);
        scopeEl.addEventListener("change", () => toggleEnvironmentSelect(scopeEl, envEl));
    });
}

function initScenarioCreatePreview(root = document) {
    const projectSelect = root.querySelector("#scenarioCreateProject");
    const moduleSelect = root.querySelector("#scenarioCreateModule");
    const nameInput = root.querySelector("#scenarioCreateName");
    const statusSelect = root.querySelector("#scenarioCreateStatus");
    const previewName = root.querySelector("#scenarioCreatePreviewName");
    const previewProject = root.querySelector("#scenarioCreatePreviewProject");
    const previewModule = root.querySelector("#scenarioCreatePreviewModule");
    const previewStatus = root.querySelector("#scenarioCreatePreviewStatus");

    if (!projectSelect || !moduleSelect || !nameInput || !statusSelect || !previewName || !previewProject || !previewModule || !previewStatus) {
        return;
    }

    const syncModuleOptions = () => {
        const projectId = projectSelect.value;
        let firstVisibleOption = null;

        Array.from(moduleSelect.options).forEach((option) => {
            const optionProjectId = option.dataset.projectId || "";
            const isVisible = !option.value || optionProjectId === projectId;
            option.hidden = !isVisible;
            option.disabled = !isVisible;
            if (isVisible && !firstVisibleOption) {
                firstVisibleOption = option;
            }
        });

        if (moduleSelect.selectedOptions[0]?.disabled) {
            moduleSelect.value = firstVisibleOption?.value || "";
        }
    };

    const syncPreview = () => {
        previewName.textContent = nameInput.value.trim() || "新的联动场景";
        previewProject.textContent = projectSelect.selectedOptions[0]?.textContent.trim() || "请选择项目";
        previewModule.textContent = moduleSelect.value
            ? moduleSelect.selectedOptions[0]?.textContent.trim()
            : "暂不归类";

        const isActive = statusSelect.value === "active";
        previewStatus.classList.toggle("status-active", isActive);
        previewStatus.classList.toggle("status-muted", !isActive);
        previewStatus.innerHTML = `<i class="bi bi-dot"></i>${isActive ? "启用" : "停用"}`;
    };

    [projectSelect, moduleSelect, nameInput, statusSelect].forEach((element) => {
        if (element.dataset.softNavBound) return;
        element.dataset.softNavBound = "true";
        const eventName = element === nameInput ? "input" : "change";
        element.addEventListener(eventName, () => {
            if (element === projectSelect) {
                syncModuleOptions();
            }
            syncPreview();
        });
    });

    syncModuleOptions();
    syncPreview();
}

function initTestcaseDirectory(root = document) {
    root.querySelectorAll(".testcase-directory-item[data-module-id]").forEach((item) => {
        if (item.dataset.softNavBound) return;
        item.dataset.softNavBound = "true";
        item.addEventListener("click", function () {
            this.classList.add("active");
        });
    });
}

function initPageInteractions(root = document) {
    initVariableScopeToggles(root);
    initScenarioCreatePreview(root);
    initTestcaseDirectory(root);
}

let softNavigationController = null;

function buildGetUrl(form) {
    const formData = new FormData(form);
    const params = new URLSearchParams();

    for (const [key, value] of formData.entries()) {
        const normalizedValue = String(value).trim();
        if (normalizedValue) {
            params.append(key, normalizedValue);
        }
    }

    const url = new URL(form.getAttribute("action") || window.location.href, window.location.origin);
    url.search = params.toString();
    return url.toString();
}

function syncShell(nextDocument) {
    const currentSidebar = document.querySelector(".sidebar");
    const nextSidebar = nextDocument.querySelector(".sidebar");
    if (currentSidebar && nextSidebar) {
        currentSidebar.outerHTML = nextSidebar.outerHTML;
    }

    const currentTopbar = document.querySelector(".topbar");
    const nextTopbar = nextDocument.querySelector(".topbar");
    if (currentTopbar && nextTopbar) {
        currentTopbar.outerHTML = nextTopbar.outerHTML;
    }

    const currentContent = document.querySelector(".content-area");
    const nextContent = nextDocument.querySelector(".content-area");
    if (currentContent && nextContent) {
        currentContent.innerHTML = nextContent.innerHTML;
    }
}

async function softNavigate(url, options = {}) {
    const currentContent = document.querySelector(".content-area");
    if (!currentContent || !window.fetch || !window.DOMParser) {
        window.location.href = url;
        return;
    }

    if (softNavigationController) {
        softNavigationController.abort();
    }

    softNavigationController = new AbortController();
    document.body.classList.add("is-soft-navigating");

    try {
        const response = await fetch(url, {
            signal: softNavigationController.signal,
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            },
            credentials: "same-origin"
        });

        if (!response.ok) {
            throw new Error(`Soft navigation failed: ${response.status}`);
        }

        const html = await response.text();
        const nextDocument = new DOMParser().parseFromString(html, "text/html");
        if (!nextDocument.querySelector(".content-area")) {
            window.location.href = url;
            return;
        }

        syncShell(nextDocument);
        document.title = nextDocument.title || document.title;

        if (options.updateHistory !== false) {
            window.history.pushState({ softNavigation: true }, "", response.url);
        }

        initPageInteractions(document);
    } catch (error) {
        if (error.name === "AbortError") {
            return;
        }
        window.location.href = url;
    } finally {
        if (softNavigationController?.signal.aborted === false) {
            softNavigationController = null;
        }
        document.body.classList.remove("is-soft-navigating");
    }
}

function initSoftNavigation() {
    document.addEventListener("submit", (event) => {
        const form = event.target.closest(".module-filter-form, .sidebar-project-form");
        if (!form || String(form.method).toLowerCase() !== "get") {
            return;
        }

        event.preventDefault();
        softNavigate(buildGetUrl(form));
    });

    document.addEventListener("click", (event) => {
        const link = event.target.closest(".module-filter-actions a[href]");
        if (!link) return;

        const form = link.closest(".module-filter-form");
        if (!form || String(form.method).toLowerCase() !== "get") {
            return;
        }

        const href = link.getAttribute("href");
        if (!href || href.startsWith("javascript:")) {
            return;
        }

        event.preventDefault();
        softNavigate(new URL(href, window.location.origin).toString());
    });

    document.addEventListener("click", (event) => {
        const link = event.target.closest(".sidebar a[href]");
        if (!link) return;

        const href = link.getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("javascript:")) {
            return;
        }

        const url = new URL(href, window.location.origin);
        if (url.origin !== window.location.origin) {
            return;
        }

        event.preventDefault();
        softNavigate(url.toString());
    });

    window.addEventListener("popstate", () => {
        softNavigate(window.location.href, { updateHistory: false });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initPageInteractions(document);
    initSoftNavigation();
});
