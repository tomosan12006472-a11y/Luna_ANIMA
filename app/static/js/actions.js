const actionRegistry = new Map();

export function registerAction(name, handler) {
  const action = String(name || "").trim();
  if (!action || typeof handler !== "function") return;
  actionRegistry.set(action, handler);
}

export function registerActions(entries = {}) {
  const items = Array.isArray(entries) ? entries : Object.entries(entries);
  for (const [name, handler] of items) {
    registerAction(name, handler);
  }
}

export async function dispatchAction(action, target, context = {}) {
  const handler = actionRegistry.get(String(action || "").trim());
  if (!handler) return false;
  await handler(target, context);
  return true;
}
