/**
 * The service worker that shows §23's pushes (§6.2, §23.4, §24.1).
 *
 * Deliberately minimal, and deliberately NOT the Workbox precaching worker
 * §6.2 also describes. That one caches the shell, the fonts and Tara's
 * portraits and belongs to the PWA workstream; this handles two events. They
 * will merge — a browser allows one worker per scope — and keeping this file
 * small is what will make that merge readable.
 *
 * ── Why the payload carries rendered strings ─────────────────────────────
 *
 * A service worker has no i18n catalog and no way to get one synchronously
 * inside a `push` handler. §2.4 admits no English fallback, so a worker that
 * resolved keys would render the KEY ITSELF on a lock screen the first time a
 * catalog was missing — outside the app, in the wrong language, where none of
 * the in-app guards can see it. The server renders instead
 * (`localisation.SERVER_RENDERED_KEYS` includes every notification string, so
 * a missing translation is a BOOT failure rather than a 07:00 one).
 *
 * ── `tag` is §23.4's collapse, after handover ────────────────────────────
 *
 * The push service collapses by RFC 8030 `Topic` while the message is still in
 * its queue; `tag` collapses in the notification centre once it has arrived.
 * Both are needed — §23.4's rule is that the user sees ONE brief notification,
 * and the two mechanisms cover the message before and after handover.
 *
 * ── The click goes to a ROUTE ────────────────────────────────────────────
 *
 * §24.1: "every push carries its deep link". The payload's `deep_link` is a
 * path and is joined to THIS worker's own origin, never used as a URL. A push
 * that could carry an absolute URL would be a push that could navigate a
 * browser somewhere else, and the payload is attacker-controlled the moment
 * anyone else obtains a VAPID key for this endpoint.
 */

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload;
  try {
    payload = event.data.json();
  } catch {
    // A push we did not send, or one whose shape changed under a stale
    // worker. Showing nothing is right: `userVisibleOnly` means the browser
    // may complain, and a notification reading "[object Object]" is worse
    // than a complaint in a console nobody is watching.
    return;
  }

  const title = payload.title || "";
  if (!title) return;

  event.waitUntil(
    self.registration.showNotification(title, {
      body: payload.body || "",
      // §23.4's collapse, in the notification centre. A regenerated brief
      // REPLACES its predecessor rather than stacking beside it.
      tag: payload.tag || payload.message_id,
      renotify: false,
      // §29.2: no manufactured urgency. `requireInteraction` would keep a
      // notification on screen until dismissed, which is a countdown wearing a
      // different hat.
      requireInteraction: false,
      lang: payload.locale || undefined,
      icon: "/tara/icon-192.png",
      badge: "/tara/badge-72.png",
      data: {
        deep_link: payload.deep_link || "/today",
        message_id: payload.message_id,
        locale: payload.locale,
      },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};

  // A PATH, resolved against our own origin. See the header — never
  // `new URL(payload.deep_link)` on its own.
  const target = new URL(
    typeof data.deep_link === "string" && data.deep_link.startsWith("/")
      ? data.deep_link
      : "/today",
    self.location.origin,
  );

  event.waitUntil(
    (async () => {
      // §23.8's open rate, and §23.2's auto-pause input. `keepalive` because
      // the worker may be terminated the moment the window is focused, and a
      // fetch without it is cancelled — which would make every opened
      // notification look unopened and eventually auto-pause the trigger.
      if (data.message_id) {
        try {
          await fetch(`/api/v1/notifications/${encodeURIComponent(data.message_id)}/opened`, {
            method: "POST",
            credentials: "include",
            keepalive: true,
          });
        } catch {
          // An open we could not record is not a reason to fail to navigate.
        }
      }

      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      // Focus an open tab rather than opening a second one. §24.1's back
      // behaviour is browser-native and never traps; a duplicate tab per push
      // is how a person ends up with six copies of Today by Thursday.
      for (const client of clients) {
        if (new URL(client.url).origin === self.location.origin && "focus" in client) {
          await client.focus();
          if ("navigate" in client) await client.navigate(target.href);
          return;
        }
      }
      await self.clients.openWindow(target.href);
    })(),
  );
});
