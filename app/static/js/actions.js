export async function dispatchAction(handler, action, target) {
  return handler(action, target);
}
