import("/static/js/main.js?v=v1.59-public-image-url-version-20260628").catch((error) => {
  console.error("Failed to load Luna ANIMA app modules", error);
  window.UI?.toast?.("UIモジュールの読み込みに失敗しました", "error");
});
