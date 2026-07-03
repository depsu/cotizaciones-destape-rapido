// Web Push para iOS: cifrado aes128gcm (RFC 8291 + RFC 8188) y VAPID (ES256),
// usando SOLO Web Crypto (compatible con Cloudflare Workers).
// Las librerías comunes (PushForge, block65) usan el formato viejo "aesgcm",
// que Apple/iOS rechaza. Esto produce "aes128gcm" + Authorization: vapid.

const ENC = new TextEncoder();

export function b64urlToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const pad = s.length % 4 ? "=".repeat(4 - (s.length % 4)) : "";
  const bin = atob(s + pad);
  const a = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) a[i] = bin.charCodeAt(i);
  return a;
}

export function bytesToB64url(bytes) {
  const a = new Uint8Array(bytes);
  let s = "";
  for (let i = 0; i < a.length; i++) s += String.fromCharCode(a[i]);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function concat(...arrs) {
  let len = 0;
  for (const a of arrs) len += a.length;
  const out = new Uint8Array(len);
  let o = 0;
  for (const a of arrs) {
    out.set(a, o);
    o += a.length;
  }
  return out;
}

async function hkdf(salt, ikm, info, len) {
  const key = await crypto.subtle.importKey("raw", ikm, "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt, info },
    key,
    len * 8
  );
  return new Uint8Array(bits);
}

// JWK ECDH/ECDSA a partir de la clave pública (65 bytes 0x04||x||y) y el escalar privado d (base64url).
function jwkFromKeys(publicB64, dB64, ops) {
  const pub = b64urlToBytes(publicB64); // 65 bytes
  return {
    kty: "EC",
    crv: "P-256",
    x: bytesToB64url(pub.slice(1, 33)),
    y: bytesToB64url(pub.slice(33, 65)),
    ...(dB64 ? { d: dB64 } : {}),
    ext: true,
    key_ops: ops,
  };
}

// Cifra el payload (string) para una suscripción. opts.{salt, asKeyPair} solo para tests.
export async function encryptContent(payloadStr, p256dhB64, authB64, opts = {}) {
  const uaPublic = b64urlToBytes(p256dhB64); // 65
  const authSecret = b64urlToBytes(authB64); // 16

  const asKeyPair =
    opts.asKeyPair ||
    (await crypto.subtle.generateKey({ name: "ECDH", namedCurve: "P-256" }, true, ["deriveBits"]));
  const asPublicRaw = new Uint8Array(await crypto.subtle.exportKey("raw", asKeyPair.publicKey)); // 65

  const uaKey = await crypto.subtle.importKey(
    "raw",
    uaPublic,
    { name: "ECDH", namedCurve: "P-256" },
    false,
    []
  );
  const ecdhSecret = new Uint8Array(
    await crypto.subtle.deriveBits({ name: "ECDH", public: uaKey }, asKeyPair.privateKey, 256)
  ); // 32

  // RFC 8291: IKM = HKDF(auth_secret, ecdh, "WebPush: info\0" || ua_public || as_public)
  const keyInfo = concat(ENC.encode("WebPush: info\0"), uaPublic, asPublicRaw);
  const ikm = await hkdf(authSecret, ecdhSecret, keyInfo, 32);

  // RFC 8188 (aes128gcm)
  const salt = opts.salt || crypto.getRandomValues(new Uint8Array(16));
  const cek = await hkdf(salt, ikm, ENC.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, ENC.encode("Content-Encoding: nonce\0"), 12);

  const plaintext = concat(ENC.encode(payloadStr), new Uint8Array([0x02])); // delimitador último registro
  const aesKey = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["encrypt"]);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce }, aesKey, plaintext)
  );

  // Cabecera: salt(16) || rs(4 BE) || idlen(1) || keyid(as_public 65)
  const rs = 4096;
  const header = new Uint8Array(16 + 4 + 1 + asPublicRaw.length);
  header.set(salt, 0);
  new DataView(header.buffer).setUint32(16, rs);
  header[20] = asPublicRaw.length;
  header.set(asPublicRaw, 21);
  return concat(header, ciphertext);
}

// VAPID JWT (ES256) firmado con la clave privada.
async function buildVapidJwt(endpoint, vapidPublicB64, vapidPrivateB64, subject) {
  const aud = new URL(endpoint).origin;
  const head = bytesToB64url(ENC.encode(JSON.stringify({ typ: "JWT", alg: "ES256" })));
  const exp = Math.floor(Date.now() / 1000) + 12 * 3600;
  const claims = bytesToB64url(ENC.encode(JSON.stringify({ aud, exp, sub: subject })));
  const signingInput = head + "." + claims;

  const jwk = jwkFromKeys(vapidPublicB64, vapidPrivateB64, ["sign"]);
  const key = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "ECDSA", namedCurve: "P-256" },
    false,
    ["sign"]
  );
  // Web Crypto firma ECDSA en formato raw r||s (64 bytes), que es justo lo que JWS necesita.
  const sig = new Uint8Array(
    await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, key, ENC.encode(signingInput))
  );
  return signingInput + "." + bytesToB64url(sig);
}

// Arma la petición HTTP de push lista para fetch().
export async function buildWebPush({
  endpoint,
  p256dh,
  auth,
  payload,
  vapidPublic,
  vapidPrivate,
  subject,
  ttl = 3600,
  urgency = "high",
}) {
  const body = await encryptContent(payload, p256dh, auth);
  const jwt = await buildVapidJwt(endpoint, vapidPublic, vapidPrivate, subject);
  return {
    endpoint,
    method: "POST",
    headers: {
      Authorization: `vapid t=${jwt}, k=${vapidPublic}`,
      "Content-Encoding": "aes128gcm",
      "Content-Type": "application/octet-stream",
      TTL: String(ttl),
      Urgency: urgency,
    },
    body,
  };
}

// Descifra (solo para test de round-trip): RFC 8188 + 8291.
export async function decryptContent(body, p256dhB64, dB64, authB64) {
  body = new Uint8Array(body);
  const salt = body.slice(0, 16);
  const idlen = body[20];
  const asPublic = body.slice(21, 21 + idlen);
  const ciphertext = body.slice(21 + idlen);
  const authSecret = b64urlToBytes(authB64);
  const uaPublic = b64urlToBytes(p256dhB64);

  const uaJwk = jwkFromKeys(p256dhB64, dB64, ["deriveBits"]);
  const uaPriv = await crypto.subtle.importKey(
    "jwk",
    uaJwk,
    { name: "ECDH", namedCurve: "P-256" },
    false,
    ["deriveBits"]
  );
  const asKey = await crypto.subtle.importKey(
    "raw",
    asPublic,
    { name: "ECDH", namedCurve: "P-256" },
    false,
    []
  );
  const ecdhSecret = new Uint8Array(
    await crypto.subtle.deriveBits({ name: "ECDH", public: asKey }, uaPriv, 256)
  );
  const keyInfo = concat(ENC.encode("WebPush: info\0"), uaPublic, asPublic);
  const ikm = await hkdf(authSecret, ecdhSecret, keyInfo, 32);
  const cek = await hkdf(salt, ikm, ENC.encode("Content-Encoding: aes128gcm\0"), 16);
  const nonce = await hkdf(salt, ikm, ENC.encode("Content-Encoding: nonce\0"), 12);
  const aesKey = await crypto.subtle.importKey("raw", cek, "AES-GCM", false, ["decrypt"]);
  const plain = new Uint8Array(
    await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, aesKey, ciphertext)
  );
  // quitar delimitador (0x02 al final, o relleno 0x00... 0x02)
  let end = plain.length;
  while (end > 0 && plain[end - 1] === 0x00) end--;
  if (end > 0 && plain[end - 1] === 0x02) end--;
  return new TextDecoder().decode(plain.slice(0, end));
}
