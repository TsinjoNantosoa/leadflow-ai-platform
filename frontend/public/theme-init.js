// Applique le thème avant le premier rendu (évite le flash clair/sombre). Fichier externe : compatible CSP `script-src 'self'`.
try {
  var t = localStorage.getItem('lf-theme')
  var dark = t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  if (dark) document.documentElement.classList.add('dark')
} catch (e) {}
