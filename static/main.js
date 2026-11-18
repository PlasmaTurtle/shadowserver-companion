import { createApplication } from './app.js';
import { establishSession } from './modules/session.js';
export const application = createApplication();
try {
  await establishSession();
  await application.start();
} catch (error) {
  document.getElementById('main').textContent = error.message;
}
