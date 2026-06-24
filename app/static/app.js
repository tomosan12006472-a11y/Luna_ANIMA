import("/static/js/main.js?v=v1.42-lora-ux-controls-20260624").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
