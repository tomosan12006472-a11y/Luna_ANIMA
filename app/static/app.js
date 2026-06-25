import("/static/js/main.js?v=v1.46-tuning-quick-controls-20260625").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
