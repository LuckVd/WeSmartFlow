import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { parse as parseVue } from '@vue/compiler-sfc';
import { parse } from '@babel/parser';

const source = readFileSync(new URL('../src/views/DocumentsView.vue', import.meta.url), 'utf8');
const descriptor = parseVue(source).descriptor;
const script = descriptor.scriptSetup.content;

const names = new Set(['getApiErrorMessage', 'unwrapApiResponse', 'loadStudyGuide', 'generateStudyGuide']);
const functions = parse(script, { sourceType: 'module' }).program.body
  .filter(node => node.type === 'FunctionDeclaration' && names.has(node.id.name))
  .map(node => script.slice(node.start, node.end))
  .join('\n');

function ref(value) {
  return { value };
}

function computed(getter) {
  return { get value() { return getter(); } };
}

function setup(apiImpl) {
  const context = {
    console: { warn() {} },
    api: apiImpl,
    studyGuide: ref(null),
    sgLoading: ref(false),
    sgFailed: ref(false),
    sgErrorMessage: ref(''),
    selectedDoc: ref({ id: 'doc-1', status: 'processed' }),
    computed,
  };
  context.sgLoadable = computed(() => ['processed', 'ready'].includes(context.selectedDoc.value?.status));
  vm.createContext(context);
  vm.runInContext(functions, context);
  return context;
}

test('study guide generation success displays the returned guide', async () => {
  const guide = {
    basics: '适合有基础几何概念的学生',
    order: '先看图形关系，再整理定理，最后做题验证',
    difficulties: '注意圆周角与旋转变换的对应关系',
    estimated: '约 20 分钟',
  };
  const c = setup({
    async post(url) {
      assert.equal(url, '/api/documents/doc-1/study-guide');
      return { generated: true, guide };
    },
  });

  await c.generateStudyGuide();

  assert.deepEqual(c.studyGuide.value, guide);
  assert.equal(c.sgFailed.value, false);
  assert.equal(c.sgErrorMessage.value, '');
  assert.equal(c.sgLoading.value, false);
});

test('study guide generation failure keeps a visible retry state with reason', async () => {
  const c = setup({
    async post() {
      const error = new Error('Request failed');
      error.response = { data: { detail: '学习建议生成失败：模型未返回有效内容' } };
      throw error;
    },
  });

  await c.generateStudyGuide();

  assert.equal(c.studyGuide.value, null);
  assert.equal(c.sgFailed.value, true);
  assert.equal(c.sgErrorMessage.value, '学习建议生成失败：模型未返回有效内容');
  assert.equal(c.sgLoading.value, false);
});

test('empty generated response is treated as failure instead of hiding the button silently', async () => {
  const c = setup({
    async post() {
      return { data: { generated: false } };
    },
  });

  await c.generateStudyGuide();

  assert.equal(c.studyGuide.value, null);
  assert.equal(c.sgFailed.value, true);
  assert.equal(c.sgErrorMessage.value, '服务端没有返回学习建议内容');
  assert.equal(c.sgLoading.value, false);
});

test('existing study guide loads into the visible guide state', async () => {
  const guide = {
    basics: '适合入门学习',
    order: '先读摘要，再看例子',
    difficulties: '概念较多',
  };
  const c = setup({
    async get(url) {
      assert.equal(url, '/api/documents/doc-1/study-guide');
      return { generated: true, guide };
    },
  });

  await c.loadStudyGuide('doc-1');

  assert.deepEqual(c.studyGuide.value, guide);
  assert.equal(c.sgFailed.value, false);
  assert.equal(c.sgErrorMessage.value, '');
});
