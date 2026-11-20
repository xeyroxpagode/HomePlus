const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

function sourceFiles(directory) {
  const absolute = path.join(root, directory);
  return fs.readdirSync(absolute, { withFileTypes: true }).flatMap((entry) => {
    const relative = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(relative);
    return /\.(ts|tsx)$/.test(entry.name) ? [relative] : [];
  });
}

test('la ruta del harness no está registrada en el stack privado', () => {
  assert.ok(!read('navigation/AppNavigator.tsx').includes('HomeCloudFileIntakeDev'));
  assert.ok(!read('navigation/types.ts').includes('HomeCloudFileIntakeDev'));
});

test('Más no muestra el acceso ni la sección de desarrollo', () => {
  const more = read('screens/MoreScreen.tsx');
  for (const forbidden of [
    'HomeCloudFileIntakeDev',
    'Archivos · Intake',
    'Harness de prueba para HC-2B',
    'DESARROLLO',
  ]) {
    assert.ok(!more.includes(forbidden), `Más todavía contiene: ${forbidden}`);
  }
});

test('ningún archivo de navegación o pantalla enlaza al harness', () => {
  const files = [...sourceFiles('navigation'), ...sourceFiles('screens')].filter(
    (file) => path.basename(file) !== 'HomeCloudFileIntakeDevScreen.tsx',
  );
  assert.ok(files.length > 0);
  for (const file of files) {
    assert.ok(
      !read(file).includes('HomeCloudFileIntakeDev'),
      `${file} todavía referencia el harness`,
    );
  }
});
