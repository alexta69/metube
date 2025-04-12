/* RegExp pattern to match URLs in the shared target text (apps often share additional text, not only URLs) */
const URL_PATTERN = /https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)/gi;

self.addEventListener("fetch", (event) => {
  if (event.request.method === "GET") {
    const url = new URL(event.request.url);

    if (url.pathname.endsWith("/share-target")) {
      const urlRegExp = new RegExp(URL_PATTERN);
      const sharedText = url.searchParams.get("text");
      const matches = [...sharedText.matchAll(urlRegExp)].map((m) => m[0]);
      const basePath = url.pathname.split("/").slice(0, -1).join("/");

      event.respondWith(
        (async () => {
          await Promise.all(
            matches.map((url) => {
              return fetch(`${basePath}/add`, {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                },
                body: JSON.stringify({
                  url,
                  quality: "best",
                  format: "any",
                  auto_start: true,
                }),
              });
            })
          );
          return Response.redirect(basePath || "/", 303);
        })()
      );
    }
  }
});

importScripts("./ngsw-worker.js");
