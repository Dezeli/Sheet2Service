import test from 'node:test';
import assert from 'node:assert/strict';
import { toggleFeature, restoreFeatures, modulesOf, rolesOf, selectedFirst, recommendedSelection } from './features.js';

test('recommended defaults exclude unavailable features and select only the first reception mode', () => {
  const options = [
    { template: 'inquiry', implemented: true },
    { template: 'request_review', implemented: true },
    { template: 'request_auto', implemented: true },
    { template: 'survey', implemented: false },
    { template: 'reservation', implemented: true },
  ];
  assert.deepEqual(recommendedSelection(options).map((item) => item.template), ['inquiry', 'request_review', 'reservation']);
  assert.equal(options.length, 5);
});

test('scheduled reservation coexists with catalog, inquiry and application approval', () => {
  let selected = [];
  for (const template of ['browse_only', 'inquiry', 'request_review', 'reservation']) {
    selected = toggleFeature(selected, { template });
  }
  assert.equal(selected.length, 4);
  selected = toggleFeature(selected, { template: 'request_auto' });
  assert.deepEqual(selected.map((item) => item.template), ['browse_only', 'inquiry', 'reservation', 'request_auto']);
});

test('rental and notice remain independent from reception and reservation', () => {
  let selected = [];
  for (const template of ['inquiry', 'request_review', 'reservation', 'notice', 'rental']) {
    selected = toggleFeature(selected, { template });
  }
  assert.equal(selected.length, 5);
  selected = toggleFeature(selected, { template: 'request_auto' });
  assert.deepEqual(selected.map((item) => item.template), ['inquiry', 'reservation', 'notice', 'rental', 'request_auto']);
});

const feature = (template) => ({ template, reference: { model_call_id: template, scope: 'user', index: 0 } });

test('reception, inquiry and catalog coexist, with one reception mode', () => {
  let selected = [];
  for (const template of ['request_review', 'inquiry', 'browse_only']) selected = toggleFeature(selected, feature(template));
  assert.equal(selected.length, 3);
  selected = toggleFeature(selected, feature('request_auto'));
  assert.deepEqual(selected.map((item) => item.template), ['inquiry', 'browse_only', 'request_auto']);
  selected = toggleFeature(selected, feature('inquiry'));
  assert.deepEqual(selected.map((item) => item.template), ['browse_only', 'request_auto']);
});

test('saved references survive refreshed recommendations and legacy configs restore', () => {
  const stored = { user: { template: 'inquiry', subjectColumn: 2, steps: ['Write', 'Read'] },
    admin: { template: 'reply_inquiries' }, selection: { model_call_id: 'old', index: 0, scope: 'user' } };
  const restored = restoreFeatures({ modules: [stored] }, [feature('inquiry')]);
  assert.deepEqual(restored[0].reference, stored.selection);
  assert.equal(restored[0].user.subjectColumn, 2);
  assert.equal(restoreFeatures({ user: { template: 'request_review' } }, [feature('request_review')]).length, 1);
  assert.deepEqual(modulesOf(null), []);
});

test('each column puts selected items first without changing unselected order', () => {
  const options = ['catalog', 'inquiry', 'review', 'auto'].map(feature);
  assert.deepEqual(selectedFirst(options, (item) => ['auto', 'inquiry'].includes(item.template)).map((item) => item.template),
    ['inquiry', 'auto', 'catalog', 'review']);
  assert.deepEqual(options.map((item) => item.template), ['catalog', 'inquiry', 'review', 'auto']);
});

test('new role selections remain independent and legacy configs get previous defaults', () => {
  const roles = { user: ['inquiry'], admin: ['reply_inquiries'], dashboard: [] };
  assert.deepEqual(rolesOf({ role_selection: roles }), roles);
  const legacy = rolesOf({ user: { template: 'inquiry' }, admin: { template: 'reply_inquiries' } });
  assert.deepEqual(legacy.admin, ['manage_catalog', 'reply_inquiries']);
  assert.deepEqual(legacy.dashboard, ['csv_statistics', 'inquiry_statistics']);
});
