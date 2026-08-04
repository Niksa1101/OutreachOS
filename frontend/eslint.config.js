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
      // Only the module system is policed. src/main.tsx is the composition root
      // and sits outside this deliberately — it is the one place allowed to
      // reach into both core/ and modules/.
      'boundaries/include': ['src/core/**/*', 'src/modules/**/*'],
      'boundaries/elements': [
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
            { from: 'core', allow: ['core'] },
            {
              from: 'module',
              allow: ['core', ['module', { moduleName: '${from.moduleName}' }]],
            },
          ],
        },
      ],
    },
  },

  // Prettier last: switches off every stylistic rule that would conflict.
  // Prettier itself runs as a separate command, never as an ESLint rule.
  prettierConfig,
);
