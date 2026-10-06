// Run with: node tests/js/settings_health.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/settings.js', 'utf8');
const functions = source.slice(source.indexOf('async function saveSettings()'), source.indexOf('const SETTINGS_SECTIONS_STORAGE_KEY'));

async function check(valid, saveOK) {
    const calls = [];
    const context = {
        form: { reportValidity: () => valid },
        t: key => key,
        SETTINGS_API: '/api/settings/',
        DEMUCS_HEALTH_API: '/api/settings/demucs-health',
        setFormState() {}, setStatus() {}, showSaveFeedback() {}, setEngineStatus() {},
        applySettingsToForm() {}, saveCurrentFormSnapshot() {}, applyDemucsHealthToUI() {},
        getFormPayload: () => ({ demucs_api_url: 'http://worker:8001', demucs_api_key: 'new-key' }),
        fetch: async (url, options) => {
            calls.push({ url, options });
            return { ok: options ? saveOK : true, json: async () => ({ healthy: true }) };
        },
    };
    vm.createContext(context);
    vm.runInContext(functions, context);
    await context.checkDemucsHealth();
    return calls;
}

(async () => {
    assert.equal((await check(false, true)).length, 0);
    assert.equal((await check(true, false)).length, 1);
    const calls = await check(true, true);
    assert.equal(calls.length, 2);
    assert.equal(calls[0].url, '/api/settings/');
    assert.equal(calls[0].options.method, 'PATCH');
    assert.equal(JSON.parse(calls[0].options.body).demucs_api_key, 'new-key');
    assert.equal(calls[1].url, '/api/settings/demucs-health');
    assert.equal(calls[1].options, undefined);
    console.log('Settings save-before-health checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
