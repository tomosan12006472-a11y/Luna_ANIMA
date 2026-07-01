import("/static/js/main.js?v=v1.69-detailer-sampling-20260702").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
