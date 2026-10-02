import test from 'node:test';
import assert from 'node:assert/strict';
import { resetOverview, resetStatus } from '../src/resetMonitorData.js';
const now = Date.parse('2026-09-17T12:00:00+08:00');
test('expired announcement remains unconfirmed and never becomes upcoming', () => {
 const event = { status: 'announced', schedule: { through: '2026-09-01T12:00:00+08:00' } };
 assert.match(resetStatus(event, now), /尚无确认/);
 assert.equal(resetOverview([event], now).upcoming.length, 0);
 assert.equal(resetOverview([{ status: 'announced', schedule: null }], now).upcoming.length, 0);
});
test('receipt review is distinct; corrections do not turn an older occurrence into the latest reset', () => {
 const older = { id: 'old', type: 'reset_credit', status: 'confirmed', occurredOn: '2026-09-04', updatedAt: '2026-09-17', confirmationBasis: 'receipt_review' };
 const newer = { id: 'new', type: 'reset_credit', status: 'confirmed', createdAt: '2026-09-10' };
 assert.equal(resetOverview([older, newer], now).credit.id, 'new');
 assert.equal(resetStatus(older), '回执核验确认');
});
test('future announced window stays separate from confirmed direct resets and credits', () => {
 const future = { status: 'announced', type: 'direct_reset', schedule: { from: '2026-09-18', through: '2026-09-19' } };
 const result = resetOverview([future], now);
 assert.equal(result.upcoming.length, 1);
 assert.equal(result.direct, undefined);
 assert.equal(result.credit, undefined);
});

import fs from 'node:fs';
import { beijingDay, eventDay, monthDays, shiftDay, shiftMonth, resetForecast, percentage } from '../src/resetMonitorData.js';
const confirmations = JSON.parse(fs.readFileSync(new URL('./fixtures/reset-confirmations.json', import.meta.url), 'utf8'));
test('historical forecast matches source page at same verification time', () => {
 const f = resetForecast(confirmations, '2026-09-17T21:58:00+08:00');
 assert.equal(f.sampleCount, 18);
 assert.deepEqual(f.probabilities.map(p=>percentage(p.probability)), ['2','20','16']);
 assert.equal(percentage(f.laterProbability), '62');
 assert.ok(Math.abs(f.probabilities.reduce((s,p)=>s+p.probability, f.laterProbability)-1)<1e-9);
});
test('forecast excludes cards, unconfirmed, duplicate IDs and future confirmations', () => {
 const asOf = '2026-09-17T21:58:00+08:00';
 const expected = resetForecast(confirmations, asOf);
 const extras = [{...confirmations[0],id:'card',type:'reset_credit'}, {...confirmations[0],id:'pending',status:'announced'}, {...confirmations[0],id:'future',confirmedAt:'2026-12-01'}, confirmations[0]];
 assert.deepEqual(resetForecast([...confirmations,...extras], asOf), expected);
 assert.equal(resetForecast(confirmations.slice(0, 5),asOf), null);
 assert.equal(resetForecast(confirmations,'invalid'), null);
});
test('calendar uses Beijing days, Monday first and handles leap years and year transitions', () => {
 assert.equal(beijingDay('2026-09-11T20:00:00Z'), '2026-09-12');
 assert.equal(monthDays('2026-09')[0], '2026-08-31');
 assert.equal(monthDays('2026-09').at(-1), '2026-10-04');
 assert.ok(monthDays('2024-02').includes('2024-02-29'));
 assert.equal(shiftDay('2026-12-31',1), '2027-01-01');
 assert.equal(shiftMonth('2026-01',-1), '2025-12');
});
test('calendar separates actual occurred date, confirmation time and undated card post', () => {
 assert.equal(eventDay({occurredOn:'2026-09-04',confirmedAt:'2026-09-13T12:00:00+08:00'}),'2026-09-04');
 assert.equal(eventDay({status:'confirmed',confirmedAt:'2026-09-12T16:09:00+08:00',schedule:{from:'2026-09-11'}}),'2026-09-12');
 assert.equal(eventDay({type:'reset_credit',status:'confirmed',createdAt:'2026-09-10T02:23:00+08:00',updatedAt:'2026-09-13'}),'2026-09-10');
});
