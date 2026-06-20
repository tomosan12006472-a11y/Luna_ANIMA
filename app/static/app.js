import("/static/js/main.js?v=v1.37-app-shell-checks-20260620").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
