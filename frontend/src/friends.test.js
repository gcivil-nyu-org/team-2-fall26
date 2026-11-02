import assert from 'node:assert/strict'
import test from 'node:test'

import { displayName, initial } from './friends.js'

test('display name prefers first and last name, falling back to email', () => {
  assert.equal(displayName({ first_name: 'Sam', last_name: 'Lee', email: 'sam@nyu.edu' }), 'Sam Lee')
  assert.equal(displayName({ first_name: 'Sam', last_name: '', email: 'sam@nyu.edu' }), 'Sam')
  assert.equal(displayName({ first_name: '', last_name: 'Lee', email: 'sam@nyu.edu' }), 'Lee')
  assert.equal(displayName({ first_name: '', last_name: '', email: 'sam@nyu.edu' }), 'sam@nyu.edu')
  assert.equal(displayName(null), '')
  assert.equal(displayName(undefined), '')
})

test('avatar initial prefers the first name, falling back to the email, then a placeholder', () => {
  assert.equal(initial({ first_name: 'Sam', email: 'sam@nyu.edu' }), 'S')
  assert.equal(initial({ first_name: '', email: 'sam@nyu.edu' }), 'S')
  assert.equal(initial({ first_name: '', email: '' }), '?')
  assert.equal(initial(undefined), '?')
})
