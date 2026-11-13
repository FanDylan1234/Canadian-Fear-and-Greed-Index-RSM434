import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BOC = 'BD.CDN.10YR.DQ.YLD';
const START = '2010-01-01';

async function download(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(30000)});
  if (!response.ok) throw new Error('HTTP ' + response.status + ' ' + response.statusText);
  return {text: await response.text(), http_status: response.status, url: response.url};
}
function number(value) {
  if (value === null || value === undefined || String(value).trim() === '' || value === '.') return null;
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error('Invalid numeric value: ' + value);
  return n;
}
function csv(text, delimiter, expected) {
  if (/<html|<!doctype/i.test(text)) throw new Error('Received HTML instead of CSV');
  const lines = text.replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  const header = lines.shift().split(delimiter);
  for (const field of expected) if (!header.includes(field)) throw new Error('Missing CSV field: ' + field);
  return lines.map(line => Object.fromEntries(header.map((key, i) => [key, line.split(delimiter)[i]])));
}
function stats(rows, intraday = false) {
  if (!rows.length) throw new Error('Empty series');
  const valid = rows.filter(r => r.value !== null);
  if (!valid.length) throw new Error('No numeric observations');
  const dates = rows.map(r => r.date);
  if (dates.some(d => !/^\d{4}-\d{2}-\d{2}/.test(d) || !Number.isFinite(Date.parse(d)))) throw new Error('Invalid date');
  const sorted = [...valid].sort((a,b) => a.date.localeCompare(b.date));
  return {
    rows: rows.length, numeric_rows: valid.length, missing_rows: rows.length-valid.length,
    duplicate_dates: dates.length-new Set(dates).size,
    first_date: sorted[0].date, last_date: sorted.at(-1).date,
    frequency: intraday ? 'intraday snapshot' : 'daily',
    begins_near_requested_start: !intraday && sorted[0].date <= '2010-01-08',
    // This is a rough freshness flag, not an exchange holiday calendar.
    calendar_days_since_last: Math.floor((Date.now()-Date.parse(sorted.at(-1).date))/86400000)
  };
}
async function portProbe() {
  return new Promise(resolve => {
    const socket = net.createConnection({host:'127.0.0.1',port:8194});
    const finish = value => {socket.destroy();resolve(value);};
    socket.setTimeout(3000);
    socket.once('connect',()=>finish('TCP port open; Bloomberg identity and entitlements NOT verified'));
    socket.once('error',e=>finish(e.code || e.message));
    socket.once('timeout',()=>finish('TCP timeout'));
  });
}
export async function run(output = path.join(ROOT,'data-access-results')) {
  await fs.mkdir(path.join(output,'raw'),{recursive:true});
  const report = {tested_at_utc:new Date().toISOString(), requested_start:START,
    scope:'Data retrieval only. No scoring, index, backtest, or evaluation.', results:[]};
  const sources = [
    {id:'fred_vix',url:'https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS&cosd='+START,ext:'csv',
      parse:t=>csv(t,',',['observation_date','VIXCLS']).map(r=>({date:r.observation_date,value:number(r.VIXCLS)})),
      note:'US VIX benchmark / explicitly labelled possible fallback, not Canadian volatility.'},
    {id:'boc_canada_10y',url:'https://www.bankofcanada.ca/valet/observations/'+BOC+'/json?start_date='+START,ext:'json',
      parse:t=>{const j=JSON.parse(t);if(!j.seriesDetail?.[BOC] || !Array.isArray(j.observations)) throw new Error('Unexpected Valet schema');return j.observations.map(r=>({date:r.d,value:number(r[BOC]?.v)}));},
      note:'Government of Canada benchmark yield; a yield series is NOT a bond total-return series.'},
    {id:'mx_equity_put_call',url:'https://www.m-x.ca/files/ratio-equity.csv',ext:'csv',
      parse:t=>csv(t,';',['Date','Call','Put','Total','Ratio']).map(r=>({date:r.Date,value:number(r.Ratio)})),
      note:'Equity options only. Source begins in 2011; no 2010 observations are invented.'},
    {id:'mx_vixi_snapshot',url:'https://www.m-x.ca/files/json/vixi.json',ext:'json',intraday:true,
      parse:t=>{const j=JSON.parse(t);if(!Array.isArray(j)) throw new Error('Unexpected VIXI schema');return j.map(r=>{if(!Array.isArray(r)||typeof r[0]!=='number')throw new Error('Invalid VIXI point');return {date:new Date(r[0]).toISOString(),value:number(r[1])};});},
      note:'Public chart feed only. Does not establish historical daily VIXI/VIXC access or fill the 2020-21 gap.'}
  ];
  for (const source of sources) {
    try {
      const result = await download(source.url);
      const rows = source.parse(result.text);
      const summary = stats(rows,source.intraday);
      await fs.writeFile(path.join(output,'raw',source.id+'.'+source.ext),result.text);
      report.results.push({id:source.id,status:source.intraday?'PARTIAL':'PASS',url:source.url,
        http_status:result.http_status,...summary,note:source.note});
    } catch(error) {
      report.results.push({id:source.id,status:'FAIL',url:source.url,error:error.message,note:source.note});
    }
  }
  report.bloomberg_tcp_probe = await portProbe();
  for (const id of ['tsx_price','tsx_total_return','tsx_advancing_declining','tsx_52week_highs_lows','canada_vixc_vixi_history','canada_ig_credit_spreads','canada_bond_total_return']) {
    report.results.push({id:'bloomberg_'+id,status:'NOT_TESTED',note:'Requires verified security/field mapping and an entitled Bloomberg Desktop API session. Run pull_bloomberg.py on the lab terminal. A TCP probe is not a successful data pull.'});
  }
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');
  const lines = ['# Data access check','', 'Tested: '+report.tested_at_utc,'',
    '| Dataset | Status | Numeric rows | First observation | Last observation |',
    '|---|---|---:|---|---|',
    ...report.results.map(r=>'| '+[r.id,r.status,r.numeric_rows??'',r.first_date??'',r.last_date??''].join(' | ')+' |'),
    '',...report.results.map(r=>'- **'+r.id+'**: '+(r.error?r.error+'; ':'')+r.note),
    '', 'Bloomberg TCP probe: '+report.bloomberg_tcp_probe,
    '', 'PASS means a non-empty numeric payload was downloaded and parsed. It does not certify completeness, licensing, accuracy, or trading-calendar coverage.',
    'Missing observations are preserved. No forward fill, returns, indicator selection, or index construction is performed.'];
  await fs.writeFile(path.join(output,'report.md'),lines.join('\n')+'\n');
  console.log(JSON.stringify(report,null,2));
  return report;
}
if (typeof process !== 'undefined' && process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const report=await run(process.argv[2] ? path.resolve(process.argv[2]) : undefined);
  if(report.results.some(r=>r.status==='FAIL')) process.exitCode=1;
}
