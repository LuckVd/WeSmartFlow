import js from "@eslint/js";
import vue from "eslint-plugin-vue";
import globals from "globals";
import vueParser from "vue-eslint-parser";
import prettier from "eslint-config-prettier";

export default [
  { ignores: ["dist/**", "node_modules/**", "coverage/**"] },

  js.configs.recommended,
  ...vue.configs["flat/recommended"],

  {
    files: ["**/*.{js,jsx,vue}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
  },

  // .vue 用 vue-eslint-parser（内部 script 用默认 espree，本项目无 TS）
  {
    files: ["**/*.vue"],
    rules: { "vue/no-v-html": "off" },
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        extraFileExtensions: [".vue"],
      },
    },
  },
  prettier,
];
