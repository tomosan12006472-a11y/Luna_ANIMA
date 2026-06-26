import("/static/js/main.js?v=v1.54-assist-hub-settings-20260626").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
