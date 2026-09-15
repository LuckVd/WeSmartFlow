import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
const source = readFileSync(new URL('../src/api/auth.js', import.meta.url), 'utf8')
  .replace(/import .*?;\n/, '').replace('export const authApi =', 'globalThis.authApi =');
function setup() {
  const values = new Map();
  const calls = [];
  const c = { BASE_URL: '', localStorage: { getItem: () => 'user-token' },
    sessionStorage: { getItem: k => values.get(k), setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) },
    fetch: async (url, options) => { calls.push({url,options}); return { ok: true, json: async () => ({state:'nonce',authorize_url:'https://github.com/oauth'}) }; },
  };
  vm.runInNewContext(source, c);
  return {c,values,calls};
}
test('reward authorization authenticates current user and stores browser state', async () => {
  const {c,values,calls}=setup();
  await c.authApi.getGitHubAuthorizeUrl(true);
  assert.equal(calls[0].url,'/api/auth/github/reward/authorize');
  assert.equal(calls[0].options.headers.Authorization,'Bearer user-token');
  assert.equal(values.get('github-oauth-state'),'nonce');
});
test('mismatched callback state blocks token exchange', async () => {
  const {c,values,calls}=setup(); values.set('github-oauth-state','expected');
  await assert.rejects(c.authApi.githubCallback('code','other'),/授权校验失败/);
  assert.equal(calls.length,0);
});
test('valid callback sends state and cannot replay in browser', async () => {
  const {c,values,calls}=setup(); values.set('github-oauth-state','expected');
  await c.authApi.githubCallback('code','expected');
  assert.deepEqual(JSON.parse(calls[0].options.body),{code:'code',state:'expected'});
  await assert.rejects(c.authApi.githubCallback('code','expected'));
});
test('OAuth query to hash redirect preserves state', () => {
  const main=readFileSync(new URL('../src/main.js',import.meta.url),'utf8');
  const block=main.slice(main.indexOf('(function handleGitHubOAuthRedirect()'),main.indexOf('})();',main.indexOf('(function handleGitHubOAuthRedirect()'))+5);
  let redirect='';
  vm.runInNewContext(block,{URLSearchParams, window:{location:{search:'?code=abc&state=nonce',hash:'',pathname:'/',replace:url=>{redirect=url;}}}});
  assert.equal(redirect,'/#/auth/github/callback?code=abc&state=nonce');
});
