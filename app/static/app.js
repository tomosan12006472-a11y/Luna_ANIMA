import("/static/js/main.js?v=v1.66-upperbody-outfit-wildcards-20260701").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
