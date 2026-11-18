const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('../front/mi-front-limpio/node_modules/typescript');
const front = path.resolve(__dirname, '../front/mi-front-limpio');
const read = file => fs.readFileSync(path.join(front, file), 'utf8');
function load(file, requireModule) {
  const exports = {};
  vm.runInNewContext(ts.transpileModule(read(file), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, { exports, require: requireModule });
  return exports;
}
const tokens = load('constants/theme.ts', () => ({ Platform: { OS: 'android', select: value => value.android ?? value.default } }));
function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255)
    .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function contrast(a, b) {
  const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (values[0] + 0.05) / (values[1] + 0.05);
}
test('both semantic palettes keep primary and secondary reading text accessible on core surfaces', () => {
  for (const colors of [tokens.colors, tokens.darkColors]) {
    for (const surface of [colors.background.base, colors.surface.card, colors.surface.soft]) {
      for (const text of [colors.text.primary, colors.text.secondary]) {
        assert.ok(contrast(text, surface) >= 4.5, `${text} on ${surface} must reach 4.5:1`);
      }
    }
  }
});
test('theme style consumer updates without remounting when the resolved palette changes', () => {
  let activeTheme = { colors: tokens.colors };
  let previousDependencies, previousStyles;
  const { useThemeStyles } = load('hooks/useThemeStyles.ts', name => name === 'react' ? {
    useMemo(factory, dependencies) {
      if (!previousDependencies || dependencies.some((value, index) => value !== previousDependencies[index])) {
        previousStyles = factory(); previousDependencies = dependencies;
      }
      return previousStyles;
    },
  } : { useAppTheme: () => activeTheme });
  const factory = theme => ({ backgroundColor: theme.colors.surface.card });
  const light = useThemeStyles(factory);
  assert.equal(useThemeStyles(factory), light);
  activeTheme = { colors: tokens.darkColors };
  const dark = useThemeStyles(factory);
  assert.notEqual(dark, light);
  assert.equal(dark.backgroundColor, tokens.darkColors.surface.card);
});
test('approved visible module labels stay centralized while technical identities remain unchanged', () => {
  const { productNames } = load('constants/productLanguage.ts');
  for (const [key, value] of Object.entries({ home: 'Casa', planner: 'Organizador', inventory: 'Inventario',
    shopping: 'Lista de compras', finance: 'Finanzas', family: 'Familia', map: 'Mapa', messages: 'Mensajes',
    files: 'Archivos', memories: 'Recuerdos', assets: 'Objetos', activity: 'Actividad', hplus: 'H+',
    homi: 'Homie', more: 'Más', profile: 'Perfil', settings: 'Ajustes', notifications: 'Notificaciones' })) {
    assert.equal(productNames[key], value);
  }
  assert.match(read('services/assets/client.ts'), /\/api\/assets/);
  assert.match(read('navigation/types.ts'), /PlannerTab/);
});
test('navigation receives the semantic theme without a theme-dependent remount key', () => {
  const app = read('App.tsx');
  assert.match(app, /NavigationContainer linking=\{linking\} theme=\{navigationTheme\}/);
  assert.doesNotMatch(app, /key=\{(?:resolvedScheme|preference|theme)/);
});
