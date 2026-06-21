import("/static/js/main.js?v=v1.40-lora-catalog-refresh-20260621").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
