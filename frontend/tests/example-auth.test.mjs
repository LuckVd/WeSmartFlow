import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
const script = readFileSync(new URL('../public/example-auth.js', import.meta.url), 'utf8');
function setup(status = 200) {
  const calls = [], banners = [];
  const context = {
    Request, Headers, URL,
    location: { href: 'https://app.test/living-history/', origin: 'https://app.test' },
    localStorage: { getItem: () => 'test-token' },
    document: {
      getElementById: () => null,
      createElement: () => ({ style: {}, setAttribute() {}, appendChild() {} }),
      body: { appendChild: el => banners.push(el) },
    },
  };
  context.window = { fetch: async (input, options) => { calls.push({ input, options }); return new Response(JSON.stringify({ detail: '额度已用完' }), { status }); } };
  vm.runInNewContext(script, context);
  return { ...context, calls, banners };
}
test('same-origin example API includes JWT and preserves JSON headers', async () => {
  const c = setup();
  await c.window.fetch('/api/court/tts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  assert.equal(c.calls[0].options.headers.get('Authorization'), 'Bearer test-token');
  assert.equal(c.calls[0].options.headers.get('Content-Type'), 'application/json');
});
test('vendor requests and static assets never receive app token', async () => {
  const c = setup();
  await c.window.fetch('https://vendor.test/api/generate');
  await c.window.fetch('/image.png');
  for (const call of c.calls) assert.equal(call.options.headers, undefined);
});
test('quota response is shown without consuming caller response', async () => {
  const c = setup(429);
  const response = await c.window.fetch('/api/demo/live-science/llm');
  assert.equal(c.banners[0].textContent, '额度已用完');
  assert.equal((await response.json()).detail, '额度已用完');
});
test('expired authentication offers login', async () => {
  const c = setup(401);
  await c.window.fetch('/api/court/tts');
  assert.match(c.banners[0].textContent, /登录/);
});
