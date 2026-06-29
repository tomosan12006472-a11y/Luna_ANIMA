import("/static/js/main.js?v=v1.61-history-pagination-diagnostics-hardfix-20260629").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
