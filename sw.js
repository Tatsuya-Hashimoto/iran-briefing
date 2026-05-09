const CACHE_NAME = 'iran-briefing-v1';
const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icon.png',
];

// インストール時に静的アセットをキャッシュ
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// 古いキャッシュを削除
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// フェッチ戦略
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Anthropic API・外部APIは常にネットワーク優先（キャッシュしない）
  if (url.hostname === 'api.anthropic.com' || url.hostname.includes('googleapis')) {
    return;
  }

  // 静的アセット: キャッシュファースト、なければネットワーク取得してキャッシュ
  event.respondWith(
    caches.match(event.request).then(cached => {
      if (cached) return cached;

      return fetch(event.request)
        .then(response => {
          if (!response || response.status !== 200 || response.type === 'opaque') {
            return response;
          }
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => {
          // オフライン時はindex.htmlにフォールバック
          if (event.request.destination === 'document') {
            return caches.match('./index.html');
          }
        });
    })
  );
});
