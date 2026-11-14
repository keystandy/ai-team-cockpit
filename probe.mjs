#!/usr/bin/env node
/**
 * 探活脚本 —— 刷新驾驶舱数据
 *
 *   node probe.mjs          只查版本/鉴权，免费、几秒完成（默认）
 *   node probe.mjs --live   真实各发一句话，会产生少量 token 费用
 *
 * 结果写回 data/office.js，刷新网页即可看到。
 * 全部文件都在 E 盘，不往 C 盘写任何东西。
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(HERE, 'data', 'office.js');
const LIVE = process.argv.includes('--live');

/* ---------- 读旧数据（保留配色、座位、能力标签） ---------- */
function loadOld() {
  const code = fs.readFileSync(DATA, 'utf8');
  const fake = { OFFICE: null };
  try {
    new Function('window', code)(fake);
    return fake.OFFICE;
  } catch (e) {
    console.error('读旧数据失败，将用空的骨架：' + e.message);
    return { agents: [], routing: [], log: [], cost: {} };
  }
}
const old = loadOld();
const byId = {};
(old.agents || []).forEach(a => (byId[a.id] = a));

/* ---------- 跑命令的小工具 ---------- */
function run(cmd, args, opts = {}) {
  return new Promise(resolve => {
    const t0 = Date.now();
    let out = '', err = '', done = false;
    let p;
    try {
      p = spawn(cmd, args, {
        cwd: opts.cwd || HERE,
        env: { ...process.env, ...(opts.env || {}) },
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      });
    } catch (e) {
      return resolve({ ok: false, ms: 0, out: '', err: e.message });
    }
    const timer = setTimeout(() => {
      if (!done) { done = true; try { p.kill(); } catch {} resolve({ ok: false, ms: Date.now() - t0, out, err: err + '\n[超时]' }); }
    }, opts.timeout || 60000);
    p.stdout.on('data', d => (out += d));
    p.stderr.on('data', d => (err += d));
    p.on('error', e => { if (!done) { done = true; clearTimeout(timer); resolve({ ok: false, ms: Date.now() - t0, out, err: e.message }); } });
    p.on('close', code => {
      if (done) return;
      done = true; clearTimeout(timer);
      resolve({ ok: code === 0, ms: Date.now() - t0, out, err, code });
    });
  });
}

const DSH_EXE = 'D:\\Program Files\\DSH NEXT\\DSH NEXT.exe';
const DSH_BIN = 'D:\\Program Files\\DSH NEXT\\resources\\app.asar\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js';
const CODEX_EXE = 'D:\\WindowsApps\\OpenAI.Codex_26.1111.2228.0_x64__2p2nqsd0c76g0\\app\\resources\\codex.exe';
const CLAUDE_EXE = 'D:\\Programs\\claude-code\\claude.exe';
const CRED = path.join(HERE, '..', '..', 'doubao-bridge', '.credentials');

function dshEnv() {
  const env = { DSH_HOME: 'E:\\DSHDockData\\dsh-home', ELECTRON_RUN_AS_NODE: '1' };
  try {
    const raw = fs.readFileSync('E:\\DSHDockData\\dsh-home\\.credentials.yaml', 'utf8');
    const m = raw.match(/sk-[A-Za-z0-9_-]{20,}/);
    if (m) env.DEEPSEEK_API_KEY = m[0];
  } catch {}
  return env;
}

function codexEnv() {
  return {
    CODEX_HOME: 'E:\\WorkBuddy工作空间\\codex-bridge\\codex-home',
    TEMP: 'E:\\WorkBuddy工作空间\\codex-bridge\\tmp',
    TMP: 'E:\\WorkBuddy工作空间\\codex-bridge\\tmp',
  };
}

function arkKey() {
  try {
    const raw = fs.readFileSync(CRED, 'utf8');
    const m = raw.match(/^ARK_API_KEY=(.+)$/m);
    return m ? m[1].trim() : null;
  } catch { return null; }
}

/* ---------- 各家探活 ---------- */
async function probeDeepseek() {
  if (LIVE) {
    const r = await run(DSH_EXE, [DSH_BIN, '--profile', 'headless', '只回复两个字：在线'], { env: dshEnv(), timeout: 180000 });
    return { status: r.ok && /在线/.test(r.out) ? 'online' : 'offline', ms: r.ms, note: r.ok ? '实呼成功' : '实呼失败' };
  }
  const r = await run(DSH_EXE, [DSH_BIN, '--version'], { env: dshEnv(), timeout: 60000 });
  const v = (r.out + r.err).trim().split(/\s+/).pop();
  return { status: r.ok ? 'online' : 'offline', ms: r.ms, version: r.ok ? v : null, note: r.ok ? '版本探活' : '版本探活失败' };
}

async function probeCodex() {
  if (LIVE) {
    const r = await run(CODEX_EXE, ['exec', '--skip-git-repo-check', '--sandbox', 'danger-full-access', '-C', HERE, '只回复两个字：在线'],
      { env: codexEnv(), timeout: 180000 });
    const tok = (r.out.match(/tokens used\s*\n?\s*([\d,]+)/) || [])[1];
    return { status: r.ok && /在线/.test(r.out) ? 'online' : 'offline', ms: r.ms, tokens: tok, note: r.ok ? '实呼成功' : '实呼失败' };
  }
  const r = await run(CODEX_EXE, ['--version'], { env: codexEnv(), timeout: 45000 });
  return { status: r.ok ? 'online' : 'offline', ms: r.ms, version: r.ok ? (r.out || r.err).trim() : null, note: r.ok ? '版本探活' : '版本探活失败' };
}

async function probeClaude() {
  if (LIVE) {
    const r = await run(CLAUDE_EXE, ['-p', '只回复两个字：在线'], { timeout: 180000 });
    return { status: r.ok && /在线/.test(r.out) ? 'online' : 'offline', ms: r.ms, note: r.ok ? '实呼成功' : '实呼失败' };
  }
  const r = await run(CLAUDE_EXE, ['--version'], { timeout: 45000 });
  return { status: r.ok ? 'online' : 'offline', ms: r.ms, version: r.ok ? (r.out || r.err).trim() : null, note: r.ok ? '版本探活' : '版本探活失败' };
}

async function probeDoubao() {
  const key = arkKey();
  if (!key) return { status: 'offline', ms: 0, note: '缺 ARK_API_KEY' };
  const base = 'https://ark.cn-beijing.volces.com/api/v3';
  const model = (byId.dou?.version || 'doubao-seed-2-1-pro-260915');
  const t0 = Date.now();
  try {
    if (LIVE) {
      const res = await fetch(base + '/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
        body: JSON.stringify({ model, messages: [{ role: 'user', content: '只回复两个字：在线' }], max_tokens: 12, thinking: { type: 'disabled' } }),
        signal: AbortSignal.timeout(45000),
      });
      const j = await res.json();
      const txt = j.choices?.[0]?.message?.content || '';
      return { status: res.ok && /在线/.test(txt) ? 'online' : 'offline', ms: Date.now() - t0, tokens: j.usage?.total_tokens, note: res.ok ? '实呼成功' : (j.error?.code || '实呼失败') };
    }
    const res = await fetch(base + '/models', { headers: { Authorization: 'Bearer ' + key }, signal: AbortSignal.timeout(20000) });
    return { status: res.ok ? 'online' : 'offline', ms: Date.now() - t0, note: res.ok ? '鉴权通过' : '鉴权失败' };
  } catch (e) {
    return { status: 'offline', ms: Date.now() - t0, note: '网络错误：' + e.message.slice(0, 40) };
  }
}

/* ---------- 主流程 ---------- */
const fmt = ms => (ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's');
const now = new Date();
const hhmm = d => String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
const stamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${hhmm(now)}`;

console.log(`探活开始 ${stamp}　模式=${LIVE ? 'live 实呼' : 'quick 免费'}`);
const [ds, cx, cl, db] = await Promise.all([probeDeepseek(), probeCodex(), probeClaude(), probeDoubao()]);
const res = { shen: ds, ku: cx, ke: cl, dou: db };

let onlineCount = 1;
const logAdd = [];
for (const [id, r] of Object.entries(res)) {
  const a = byId[id];
  if (!a) continue;
  a.status = r.status;
  if (r.status === 'online') onlineCount++;
  const bits = [r.note];
  if (r.tokens) bits.push(r.tokens + ' tok');
  bits.push(fmt(r.ms));
  a.last = `${hhmm(now)} ${bits.join(' / ')}`;
  if (r.version) a.version = r.version;
  console.log(`  ${a.name.padEnd(3)} ${r.status === 'online' ? '在线' : '离线'}  ${bits.join('  ')}`);
  logAdd.push({
    t: hhmm(now), who: a.name,
    msg: `${r.status === 'online' ? '探活通过' : '探活失败'}：${bits.join(' / ')}`,
    ok: r.status === 'online', bad: r.status !== 'online',
  });
}

const out = {
  generatedAt: stamp,
  connectivity: `${onlineCount - 1}/4 员工 + 老板`,
  agents: (old.agents || []).length ? old.agents : [],
  routing: old.routing || [],
  cost: old.cost || {},
  log: [...logAdd, ...(old.log || [])].slice(0, 40),
};

const header = `/* 磨坊办公室 · 数据快照
   由 probe.mjs 自动生成（${stamp}），也可手改。
   注意：这是 JS 而非 JSON —— 为了在 file:// 下也能直接双击打开（无 CORS 限制）。 */

`;
fs.writeFileSync(DATA, header + 'window.OFFICE = ' + JSON.stringify(out, null, 2) + ';\n', 'utf8');
console.log(`\n已写入 ${path.relative(process.cwd(), DATA) || DATA}`);
console.log(`在线 ${onlineCount}/5　刷新网页即可看到`);
