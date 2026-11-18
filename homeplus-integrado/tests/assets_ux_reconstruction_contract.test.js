const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) =>
  fs.readFileSync(path.join(root, relativePath), 'utf8');

test('Assets mantiene una única entrada primaria y mueve archivo/papelera al menú secundario', () => {
  const source = read('front/mi-front-limpio/screens/assets/AssetsListScreen.tsx');

  assert.match(source, /const showHeaderCreate = isRoot && canCreate && \(assets\.length > 0 \|\| hasActiveFilter\)/);
  assert.match(source, /actionLabel=\{canCreate \? "Agregar un objeto" : undefined\}/);
  assert.match(source, /label: 'Archivados'/);
  assert.match(source, /label: 'Papelera'/);
  assert.match(source, /secondaryActionLabel="Limpiar búsqueda y filtros"/);
  assert.doesNotMatch(source, /styles\.accessRow/);
});

test('La creación usa progressive disclosure sin perder los datos avanzados', () => {
  const source = read('front/mi-front-limpio/components/assets/AssetCreateSheet.tsx');

  assert.match(source, /title="Agregar un objeto"/);
  assert.match(source, /title="Agregar más datos"/);
  assert.match(source, /label="Marca \(opcional\)"/);
  assert.match(source, /label="Modelo \(opcional\)"/);
  assert.match(source, /label="Número de serie \(opcional\)"/);
  assert.match(source, /Categoría \(opcional\)/);
});

test('El detalle conserva rutas y permite Planner cuando queda al menos una acción disponible', () => {
  const source = read('front/mi-front-limpio/screens/assets/AssetDetailScreen.tsx');
  const navigator = read('front/mi-front-limpio/navigation/HomeTabNavigator.tsx');

  assert.match(source, /<AppPageHeader/);
  assert.match(source, /!canCreatePlannerTask && !canCreatePlannerEvent/);
  assert.match(source, /DÓNDE ESTÁ Y QUIÉN LO TIENE/);
  assert.match(source, /navigation\.navigate\('Assets'/);

  for (const route of [
    'Assets',
    'AssetsArchived',
    'AssetsTrash',
    'AssetsDetail',
    'AssetRecords',
    'AssetCare',
  ]) {
    assert.match(navigator, new RegExp(`name="${route}"`));
  }
});

test('Registros y cuidados largos conservan desplazamiento vertical', () => {
  const source = read('front/mi-front-limpio/screens/assets/AssetRecordsScreen.tsx');
  const scrollViews = source.match(/<ScrollView/g) ?? [];
  assert.equal(scrollViews.length, 2);
});
