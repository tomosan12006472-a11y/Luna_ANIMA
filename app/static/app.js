import("/static/js/main.js?v=v1.31-reference-i2i-module-20260620").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
