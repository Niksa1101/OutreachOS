import js from '@eslint/js';
import boundaries from 'eslint-plugin-boundaries';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'src/core/api/schema.d.ts'] },

  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      boundaries,
    },
    settings: {
      // Only the module system is policed. src/main.tsx sits outside this
      // deliberately — it is the entry point, not a participant.
      'boundaries/include': ['src/core/**/*', 'src/modules/**/*'],
      // Order matters: the first matching pattern wins, so the composition
      // roots must be listed before the `src/core/**/*` glob that also
      // matches them.
      'boundaries/elements': [
        {
          // Q19: adding a module is a folder plus one line. These two files
          // are where that line goes, so they are the only places inside
          // core/ allowed to name a module. Naming them explicitly is what
          // keeps "core may not import a module" true everywhere else —
          // the alternative is exempting all of core/ and losing the rule.
          type: 'composition-root',
          mode: 'file',
          pattern: ['src/core/router/router.tsx', 'src/core/registry/modules.ts'],
        },
        { type: 'core', pattern: 'src/core/**/*' },
        { type: 'module', pattern: 'src/modules/*/**/*', capture: ['moduleName'] },
      ],
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // Tech.md §3.4: cross-module imports are forbidden; shared behaviour
      // moves to core/. A module may import core/ and itself, nothing else.
      // core/ may never import a module — that would invert the dependency.
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          message: '${file.type} may not import ${dependency.type}. Shared code belongs in core/.',
          rules: [
            // The registry and the route tree may reach into modules. Nothing
            // else in core/ may.
            { from: 'composition-root', allow: ['core', 'module', 'composition-root'] },
            { from: 'core', allow: ['core', 'composition-root'] },
            {
              from: 'module',
              allow: ['core', 'composition-root', ['module', { moduleName: '${from.moduleName}' }]],
            },
          ],
        },
      ],
    },
  },

  // shadcn's primitives are generated, not authored here. `npx shadcn add`
  // overwrites them wholesale, so any edit made to satisfy a lint rule is
  // undone by the next component that gets pulled in.
  //
  // Narrow on purpose: only the rule they actually trip. Everything else —
  // type checking, the boundary rules, unused variables — still applies,
  // because a generated file can still be wrong in ways that matter.
  {
    files: ['src/core/components/ui/**/*.{ts,tsx}'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },

  // Prettier last: switches off every stylistic rule that would conflict.
  // Prettier itself runs as a separate command, never as an ESLint rule.
  prettierConfig,
);
