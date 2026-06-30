import("/static/js/main.js?v=v1.63-history-generation-metrics-20260630").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
