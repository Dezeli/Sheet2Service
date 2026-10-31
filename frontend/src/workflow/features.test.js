import test from 'node:test';
import assert from 'node:assert/strict';
import { modulesOf, rolesOf } from './features.js';

test('role selections are returned as saved and legacy configs get previous defaults', () => {
  const roles = { user: ['inquiry'], admin: ['reply_inquiries'], dashboard: [] };
  assert.deepEqual(rolesOf({ role_selection: roles }), roles);
  const legacy = rolesOf({ user: { template: 'inquiry' }, admin: { template: 'reply_inquiries' } });
  assert.deepEqual(legacy.admin, ['manage_catalog', 'reply_inquiries']);
  assert.deepEqual(legacy.dashboard, ['csv_statistics', 'inquiry_statistics']);
  assert.deepEqual(modulesOf(null), []);
  assert.equal(modulesOf({ modules: [{ user: { template: 'notice' } }] }).length, 1);
});
