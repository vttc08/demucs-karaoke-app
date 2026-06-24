(() => {
  const assetMarker = "/assets/";

  const getDocsBasePath = () => {
    const candidates = [
      'link[rel="icon"]',
      'link[href*="/assets/stylesheets/"]',
      'script[src*="/assets/javascripts/"]',
    ];

    for (const selector of candidates) {
      const element = document.querySelector(selector);
      if (!element) continue;

      const rawUrl = element.getAttribute("href") || element.getAttribute("src");
      if (!rawUrl) continue;

      const resolvedPath = new URL(rawUrl, window.location.href).pathname;
      const markerIndex = resolvedPath.indexOf(assetMarker);
      if (markerIndex >= 0) {
        return resolvedPath.slice(0, markerIndex);
      }
    }

    return "";
  };

  const docsBasePath = getDocsBasePath().replace(/\/$/, "");

  const prefixPath = (value) => {
    if (!value || value.startsWith("#") || value.startsWith("//")) {
      return value;
    }

    if (
      value.startsWith("mailto:") ||
      value.startsWith("tel:") ||
      value.startsWith("javascript:")
    ) {
      return value;
    }

    if (value.startsWith("/")) {
      return `${docsBasePath}${value}`;
    }

    return value;
  };

  const rewriteRootRelativeLinks = (root) => {
    root.querySelectorAll('a[href], img[src], source[srcset], link[rel="alternate"][href]').forEach((element) => {
      if (element.tagName === "A" || element.tagName === "LINK") {
        const href = element.getAttribute("href");
        const rewritten = prefixPath(href);
        if (rewritten !== href) {
          element.setAttribute("href", rewritten);
        }
        return;
      }

      if (element.tagName === "IMG") {
        const src = element.getAttribute("src");
        const rewritten = prefixPath(src);
        if (rewritten !== src) {
          element.setAttribute("src", rewritten);
        }
        return;
      }

      if (element.tagName === "SOURCE") {
        const srcset = element.getAttribute("srcset");
        if (!srcset) return;

        const rewritten = srcset
          .split(",")
          .map((part) => {
            const trimmed = part.trim();
            if (!trimmed) return trimmed;

            const [url, descriptor] = trimmed.split(/\s+/, 2);
            const nextUrl = prefixPath(url);
            return descriptor ? `${nextUrl} ${descriptor}` : nextUrl;
          })
          .join(", ");

        if (rewritten !== srcset) {
          element.setAttribute("srcset", rewritten);
        }
      }
    });
  };

  const start = () => {
    rewriteRootRelativeLinks(document);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;
          rewriteRootRelativeLinks(node);
        }
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
