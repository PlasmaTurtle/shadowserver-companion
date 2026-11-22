/** Check all owned scripts without executing browser code or third-party bundles. */
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
function scripts(folder) {
  return fs.readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    if (['vendor', 'geo'].includes(entry.name)) return [];
    const file = path.join(folder, entry.name);
    return entry.isDirectory() ? scripts(file) : /\.(c?js)$/.test(entry.name) ? [file] : [];
  });
}
for (const file of [...scripts(path.join(root, 'modules')), ...scripts(__dirname)]) {
  const result = spawnSync(process.execPath, ['--check', file], { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status || 1);
}
console.log('Owned frontend scripts pass syntax checks.');
