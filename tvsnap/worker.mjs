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
 * API_KEY carries read and write. READ_KEY, when set, carries read only — for
 * consumers that only want the JSON and must never be able to clobber it. Both
 * keys still see calendar titles, so read-only limits damage, not exposure.
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

    const capability = authorized(request, env);
    if (capability === null) {
      // 401 without a WWW-Authenticate header: this is a key check, not a
      // challenge the client can usefully respond to.
      return json({ error: "unauthorized" }, 401);
    }

    if (request.method === "GET") {
      return await handleGet(env);
    }
    if (request.method === "PUT") {
      if (capability !== "rw") {
        // Authenticated but not permitted, so 403 rather than 401: presenting a
        // different key is the fix, retrying this one never is.
        return json({ error: "read-only key" }, 403);
      }
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
 * Returns the capability the presented key carries — "rw" for API_KEY, "ro" for
 * READ_KEY — or null when it matches neither. READ_KEY is optional: with it
 * unset this collapses to the original single-key behaviour.
 */
function authorized(request, env) {
  const presented = request.headers.get("X-API-Key");
  if (!presented) {
    return null;
  }
  if (env.API_KEY && matches(presented, env.API_KEY)) {
    return "rw";
  }
  if (env.READ_KEY && matches(presented, env.READ_KEY)) {
    return "ro";
  }
  return null;
}

/**
 * Compares a presented key against a secret in constant time. A plain === leaks
 * the length of the matching prefix through timing; the keys are long-lived and
 * the endpoint is public, so that is worth avoiding.
 */
function matches(presented, secret) {
  const a = new TextEncoder().encode(presented);
  const b = new TextEncoder().encode(secret);
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
