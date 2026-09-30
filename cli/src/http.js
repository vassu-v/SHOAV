import http from 'node:http';
import net from 'node:net';

export function getJson(url, { timeout = 5000 } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { headers: { Accept: 'application/json' } }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const err = new Error(`HTTP ${res.statusCode} from ${url}`);
          err.status = res.statusCode;
          return reject(err);
        }
        try {
          const data = body.trim() ? JSON.parse(body) : {};
          resolve(data && typeof data === 'object' && !Array.isArray(data) ? data : { value: data });
        } catch {
          reject(new Error(`invalid JSON from ${url}`));
        }
      });
    });
    req.setTimeout(timeout, () => req.destroy(new Error(`timed out after ${timeout} ms`)));
    req.on('error', reject);
  });
}

export async function isHealthy(base, timeout = 2000) {
  try {
    const d = await getJson(`${base}/healthz`, { timeout });
    return d.status === 'ok';
  } catch {
    return false;
  }
}

// true when something accepts TCP connections on 127.0.0.1:port.
export function portInUse(port, host = '127.0.0.1', timeout = 1000) {
  return new Promise((resolve) => {
    const sock = net.createConnection({ port, host });
    const done = (v) => { sock.destroy(); resolve(v); };
    sock.setTimeout(timeout, () => done(false));
    sock.once('connect', () => done(true));
    sock.once('error', () => done(false));
  });
}
