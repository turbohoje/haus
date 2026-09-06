/**
 * haus-tvsnap — serves one small JSON snapshot of the TV display data.
 *
 *   GET  /snapshot   read the current snapshot   (X-API-Key)
 *   PUT  /snapshot   replace it                  (X-API-Key)
 *   GET  /health     liveness, no auth
 *
 * Storage is a single R2 object, last-write-wins. There is no history: the
 * consumer is a watch face that only ever wants "what is true now", and the
 * publisher re-sends every 5 minutes anyway.
 *
 * One shared key does both read and write, so a leaked key is also a write
 * capability. That is the accepted trade here — the key ships inside a
 * sideloaded watch app, where a second key would have been just as exposed.
 */

const OBJECT_KEY = "snapshot.json";
const MAX_BYTES = 32 * 1024;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return json({ status: "ok" });
    }

    if (url.pathname !== "/snapshot") {
      return json({ error: "not found" }, 404);
    }

    if (!authorized(request, env)) {
      // 401 without a WWW-Authenticate header: this is a key check, not a
      // challenge the client can usefully respond to.
      return json({ error: "unauthorized" }, 401);
    }

    if (request.method === "GET") {
      return await handleGet(env);
    }
    if (request.method === "PUT") {
      return await handlePut(request, env);
    }
    return json({ error: "method not allowed" }, 405);
  },
};

async function handleGet(env) {
  const object = await env.SNAP.get(OBJECT_KEY);
  if (object === null) {
    return json({ error: "no snapshot published yet" }, 404);
  }
  // Content-Type is forced rather than echoed from R2: Connect IQ's
  // makeWebRequest only parses a response it is told is JSON.
  return new Response(object.body, {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

async function handlePut(request, env) {
  const body = await request.text();

  if (body.length > MAX_BYTES) {
    return json({ error: `body over ${MAX_BYTES} bytes` }, 413);
  }
  try {
    JSON.parse(body);
  } catch {
    // Reject here rather than at read time — a watch that gets malformed JSON
    // back has no way to recover, so bad input must never reach the bucket.
    return json({ error: "body is not valid JSON" }, 400);
  }

  await env.SNAP.put(OBJECT_KEY, body, {
    httpMetadata: { contentType: "application/json" },
  });

  return json({ ok: true, bytes: body.length });
}

/**
 * Compares against the API_KEY secret in constant time. A plain === leaks the
 * length of the matching prefix through timing; the key is long-lived and the
 * endpoint is public, so that is worth avoiding.
 */
function authorized(request, env) {
  const presented = request.headers.get("X-API-Key");
  if (!presented || !env.API_KEY) {
    return false;
  }

  const a = new TextEncoder().encode(presented);
  const b = new TextEncoder().encode(env.API_KEY);
  if (a.byteLength !== b.byteLength) {
    return false;
  }
  // Workers' timingSafeEqual is synchronous and throws on a length mismatch,
  // which the check above has already ruled out.
  return crypto.subtle.timingSafeEqual(a, b);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
