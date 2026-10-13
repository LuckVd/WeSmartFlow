<template>
  <div class="admin-page">
    <div class="admin-page-head">
      <div>
        <h1>用户管理</h1>
        <p>查看账号、积分余额与学习情况，共 {{ number(total) }} 位匹配用户。</p>
      </div>
      <button class="a-button" :disabled="loading" @click="load">
        刷新列表
      </button>
    </div>
    <div v-if="error" class="a-error" role="alert">{{ error }}</div>
    <section class="a-panel" aria-label="用户列表">
      <form class="a-filters" @submit.prevent="apply">
        <label class="a-field wide"
          >搜索用户<input
            v-model="filters.q"
            placeholder="昵称、邮箱、用户 ID 或 GitHub 用户名"
        /></label>
        <label class="a-field"
          >绑定方式<select v-model="filters.binding">
            <option value="">全部</option>
            <option value="email">邮箱</option>
            <option value="github">GitHub</option>
            <option value="wechat">微信</option>
          </select></label
        >
        <label class="a-field"
          >注册起始日期<input v-model="filters.created_from" type="date"
        /></label>
        <label class="a-field"
          >注册截止日期<input v-model="filters.created_to" type="date"
        /></label>
        <label class="a-field"
          >最低积分<input
            v-model="filters.min_balance"
            type="number"
            step="1"
            placeholder="不限"
        /></label>
        <label class="a-field"
          >最高积分<input
            v-model="filters.max_balance"
            type="number"
            step="1"
            placeholder="不限"
        /></label>
        <label class="a-field"
          >排序<select v-model="filters.sort_by">
            <option value="created_at">注册时间</option>
            <option value="balance">积分余额</option>
            <option value="used">本月消耗</option>
          </select></label
        >
        <label class="a-field"
          >顺序<select v-model="filters.sort_order">
            <option value="desc">从高到低 / 从新到旧</option>
            <option value="asc">从低到高 / 从旧到新</option>
          </select></label
        >
        <button class="a-button primary" type="submit">筛选</button
        ><button class="a-button" type="button" @click="reset">重置</button>
      </form>
      <div v-if="loading" class="a-empty" role="status">正在加载用户…</div>
      <div v-else-if="error" class="a-empty">
        <button class="a-button" @click="load">重新加载</button>
      </div>
      <div v-else-if="!items.length" class="a-empty">
        没有匹配的用户，请调整筛选条件。
      </div>
      <div v-else class="a-table-wrap">
        <table class="a-table">
          <thead>
            <tr>
              <th>用户</th>
              <th>邮箱</th>
              <th>绑定方式</th>
              <th>GitHub</th>
              <th>已入账积分</th>
              <th>本月消耗</th>
              <th>注册时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in items" :key="user.id">
              <td>
                <div class="a-user">
                  <span class="a-avatar">{{
                    (user.name || "?").slice(0, 1)
                  }}</span>
                  <div>
                    <router-link class="a-link" :to="detailLink(user.id)">{{
                      user.name
                    }}</router-link>
                    <div class="a-muted">{{ user.id }}</div>
                  </div>
                </div>
              </td>
              <td>{{ user.email || "未提供" }}</td>
              <td>
                <span
                  v-for="binding in user.bindings"
                  :key="binding"
                  class="a-tag"
                  >{{ bindingLabel(binding) }}</span
                ><span v-if="!user.bindings.length" class="a-muted"
                  >未绑定</span
                >
              </td>
              <td>{{ user.github_username || "—" }}</td>
              <td class="numeric">{{ number(user.balance) }}</td>
              <td class="numeric">{{ number(user.used) }}</td>
              <td style="white-space: nowrap">{{ time(user.created_at) }}</td>
              <td>
                <router-link class="a-link" :to="detailLink(user.id)"
                  >查看详情 →</router-link
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="a-pager">
        <span>第 {{ page }} / {{ pages }} 页 · {{ period }} 平台额度消耗</span>
        <div class="a-actions">
          <button
            class="a-button"
            :disabled="page <= 1 || loading"
            @click="go(page - 1)"
          >
            上一页</button
          ><button
            class="a-button"
            :disabled="page >= pages || loading"
            @click="go(page + 1)"
          >
            下一页
          </button>
        </div>
      </div>
    </section>
    <p class="a-muted">
      余额为已入账数值。查看用户不会触发注册或月度积分补发。
    </p>
  </div>
</template>
<script setup>
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { adminApi } from "../api/admin.js";
import {
  number,
  time,
  bindingLabel,
  pageNumber,
} from "../components/Admin/format.js";
const route = useRoute(),
  router = useRouter();
const defaults = {
  q: "",
  binding: "",
  created_from: "",
  created_to: "",
  min_balance: "",
  max_balance: "",
  sort_by: "created_at",
  sort_order: "desc",
};
const filters = reactive({ ...defaults }),
  items = ref([]),
  total = ref(0),
  loading = ref(false),
  error = ref(""),
  period = ref("");
const page = computed(() => pageNumber(route.query.page)),
  pages = computed(() => Math.max(1, Math.ceil(total.value / 25)));
let request = 0;
async function load() {
  const current = ++request;
  loading.value = true;
  error.value = "";
  try {
    const params = Object.fromEntries(
      Object.keys(defaults).map((key) => [
        key,
        route.query[key] ?? defaults[key],
      ]),
    );
    const data = await adminApi.users({
      ...params,
      limit: 25,
      offset: (page.value - 1) * 25,
    });
    if (current !== request) return;
    items.value = data.items;
    total.value = data.total;
    period.value = data.period;
  } catch (e) {
    if (current === request) error.value = e.message;
  } finally {
    if (current === request) loading.value = false;
  }
}
function apply() {
  const query = Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== ""),
  );
  if (JSON.stringify(query) === JSON.stringify(route.query)) load();
  else router.push({ path: "/admin/users", query });
}
function reset() {
  Object.assign(filters, defaults);
  router.push("/admin/users");
}
function go(value) {
  router.push({ query: { ...route.query, page: String(value) } });
}
function detailLink(id) {
  return {
    path: `/admin/users/${encodeURIComponent(id)}`,
    query: { ...route.query, tab: "profile" },
  };
}
watch(
  () => route.query,
  () => {
    Object.assign(
      filters,
      Object.fromEntries(
        Object.keys(defaults).map((key) => [
          key,
          route.query[key] ?? defaults[key],
        ]),
      ),
    );
    load();
  },
  { immediate: true },
);
</script>
