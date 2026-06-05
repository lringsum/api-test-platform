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
