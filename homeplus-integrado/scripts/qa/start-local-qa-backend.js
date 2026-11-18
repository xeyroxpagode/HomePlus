#!/usr/bin/env node
'use strict';

// Local-only runner for runtime QA. It keeps the administrative credential in
// the process environment and never exposes it to the mobile bundle or logs.
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const dotenv = require(require.resolve('dotenv', { paths: [path.join(root, 'backend', 'node_modules')] }));
dotenv.config({ path: path.join(root, 'backend', '.env') });
dotenv.config({ path: path.join(root, '.env.qa'), override: false });

const adminKey = process.env.QA_SUPABASE_SECRET_KEY || process.env.QA_SUPABASE_SERVICE_ROLE_KEY;
if (!adminKey) throw new Error('QA administrative credential is required for the local runtime backend.');

process.env.SUPABASE_SERVICE_ROLE_KEY = adminKey;
process.env.PORT = process.env.PORT || '3001';
require(path.join(root, 'backend', 'index.js'));
