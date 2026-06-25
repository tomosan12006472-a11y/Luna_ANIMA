import("/static/js/main.js?v=v1.47-mobile-ops-public-save-20260625").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
