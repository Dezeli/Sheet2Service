// Two entries share one bundle: a service route loads the app's own styles and screens; the landing loads the
// design kit from /kit and nothing of the app's CSS, so the kit's page rules never reach a service screen.
const path = window.location.pathname.replace(/\/+$/, '');
const serviceMatch = path.match(/^\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/([A-Za-z_]+)$/);

if (serviceMatch) import('./serviceEntry.jsx').then(({ mount }) => mount(serviceMatch[1], serviceMatch[2]));
else import('./landing/landingEntry.jsx').then(({ mount }) => mount());
