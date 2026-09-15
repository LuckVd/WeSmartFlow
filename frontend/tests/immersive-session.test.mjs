import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import { parse as parseVue } from '@vue/compiler-sfc';
import { parse } from '@babel/parser';

const source = readFileSync(new URL('../src/views/ImmersiveView.vue', import.meta.url), 'utf8');
const script = parseVue(source).descriptor.scriptSetup.content;
const functions = parse(script, { sourceType: 'module' }).program.body
  .filter(n => n.type === 'FunctionDeclaration' && ['rememberImmersiveSession', 'restoreImmersive'].includes(n.id.name))
  .map(n => script.slice(n.start, n.end)).join('\n');

function harness(query, detail) {
  let starts = 0;
  const context = {
    console: { warn() {} }, Date, String,
    route: { path: '/immersive', query },
    sessionStartTime: null,
    sessionApi: { async getById(id) { assert.equal(id, 'course-1'); if (detail instanceof Error) throw detail; return detail; } },
    router: { async replace(location) { context.route.query = location.query; } },
    imAddLog() {}, applyWorkspacePayload() {},
    nextTick(fn) { return fn?.(); },
    startImmersive() { starts++; },
  };
  for (const name of ['imRestoreError', 'imResumePrompt', 'phase', 'currentTopic', 'currentSessionId', 'imCompleted', 'imGenerating', 'imTab', 'topicInput', 'enableAudio', 'enableExercises', 'imAgentMessages']) {
    context[name] = { value: null };
  }
  context.canvasBlocks = { value: [] };
  context.imChapters = { value: [] };
  vm.createContext(context);
  vm.runInContext(functions, context);
  return { context, starts: () => starts };
}

test('new course URL becomes a restorable session URL before refresh', async () => {
  const { context: c, starts } = harness({ topic: '神经网络', enable_audio: '1' }, { id: 'course-1', stage: 'ready' });
  await c.restoreImmersive();
  assert.equal(starts(), 1);
  c.rememberImmersiveSession('course-1');
  assert.equal(c.route.query.session_id, 'course-1');
  assert.equal(c.route.query.enable_audio, '1');
  c.currentSessionId.value = null; // Refresh loses component memory.
  await c.restoreImmersive();
  assert.equal(starts(), 1);
  assert.equal(c.currentSessionId.value, 'course-1');
  assert.equal(c.imCompleted.value, true);
});

test('failed restore and retry never start a new generation', async () => {
  const { context: c, starts } = harness({ session_id: 'course-1', topic: '神经网络' }, new Error('network failure'));
  await c.restoreImmersive();
  await c.restoreImmersive();
  assert.equal(starts(), 0);
  assert.ok(c.imRestoreError.value);
  assert.equal(c.route.query.session_id, 'course-1');
});

for (const stage of ['ready', 'completed', 'partial_ready']) {
  test(`restore ${stage} distinguishes generated content from unfinished generation`, async () => {
    const { context: c, starts } = harness({ session_id: 'course-1', resume: '1' }, { id: 'course-1', stage });
    await c.restoreImmersive();
    assert.equal(starts(), 0);
    assert.equal(c.imCompleted.value, stage !== 'partial_ready');
    assert.equal(c.imResumePrompt.value, stage === 'partial_ready');
  });
}
