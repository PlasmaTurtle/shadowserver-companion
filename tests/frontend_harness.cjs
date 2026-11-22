/** Load production ES modules intact into an isolated browser-like VM.
 * Tests receive explicit application state/actions; compatibility aliases below
 * keep established regression fixtures readable without source slicing.
 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function loadApplication(context, { theme = false, attach = true } = {}) {
  if (!vm.SourceTextModule) {
    throw new Error('Run DOM tests with node --experimental-vm-modules.');
  }
  const root = path.resolve(__dirname, '../modules/ui/static');
  if (theme) vm.runInContext(fs.readFileSync(path.join(root, 'theme.js'), 'utf8'), context);
  const modules = new Map();
  function load(filename) {
    if (modules.has(filename)) return modules.get(filename);
    const mod = new vm.SourceTextModule(fs.readFileSync(filename, 'utf8'), {
      context,
      identifier: filename,
    });
    modules.set(filename, mod);
    return mod;
  }
  const module = load(path.join(root, 'app.js'));
  // Node links the graph once, including shared dependencies reached by several owners.
  await module.link((specifier, referencing) =>
    load(path.resolve(path.dirname(referencing.identifier), specifier)),
  );
  await module.evaluate();
  const application = module.namespace.createApplication();
  for (const container of [
    application.actions,
    application.constants,
    ...Object.values(application.state),
  ]) {
    for (const key of Object.keys(container)) {
      Object.defineProperty(context, key, {
        configurable: true,
        get: () => container[key],
        set: (value) => {
          container[key] = value;
        },
      });
    }
  }
  if (attach) application.attach();
  return { application, createApplication: module.namespace.createApplication };
}
module.exports = { loadApplication };
