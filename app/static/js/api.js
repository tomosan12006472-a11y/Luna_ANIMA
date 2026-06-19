export function errorMessage(error) {
  return error?.data?.message || error?.data?.detail || error?.message || String(error);
}

export function isUnauthorized(error) {
  return Number(error?.status || error?.data?.status || 0) === 401;
}

export function authExpiredMessage() {
  return "ログインが切れました。PINで入り直してください。";
}

export function createApiClient({ onUnauthorized } = {}) {
  function handleUnauthorized() {
    const message = authExpiredMessage();
    if (onUnauthorized) onUnauthorized(message);
    return message;
  }

  async function fetchWithAuthHandling(path, options = {}) {
    const response = await fetch(path, {
      credentials: "same-origin",
      ...options,
    });
    if (response.status === 401) {
      const message = handleUnauthorized();
      const error = new Error(message);
      error.status = response.status;
      error.data = { ok: false, status: response.status, message };
      throw error;
    }
    if (!response.ok) {
      const body = await response.text().catch(() => "");
      const error = new Error(response.statusText || "Request failed");
      error.status = response.status;
      error.data = { ok: false, status: response.status, body: body.slice(0, 300) };
      throw error;
    }
    return response;
  }

  async function api(path, options = {}) {
    const fetchOptions = { ...options };
    const headers = new Headers(fetchOptions.headers || {});
    delete fetchOptions.headers;
    if (fetchOptions.body !== undefined && !(fetchOptions.body instanceof FormData) && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      headers,
    });
    const raw = await response.text();
    const contentType = response.headers.get("content-type") || "";
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = {
        ok: false,
        message: "Response was not JSON",
        status: response.status,
        content_type: contentType,
        body: raw.slice(0, 300),
      };
    }
    if (response.status === 401) {
      handleUnauthorized();
    }
    if (!response.ok || data?.ok === false) {
      const error = new Error(data?.message || data?.detail || response.statusText || "Request failed");
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  return { api, fetchWithAuthHandling };
}
