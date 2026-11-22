import { createApplication } from './app.js';
import { establishSession } from './session.js';
export const application = createApplication();
try {
  await establishSession();
  await application.start();
} catch (error) {
  document.getElementById('main').textContent = error.message;
}
