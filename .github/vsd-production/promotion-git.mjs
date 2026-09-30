#!/usr/bin/env node
/** Candidate media-only Git bridge. Fixed repo, bounded data, no force/rebase,
 * no provider credential, editorial release or automatic retry. The workflow
 * grants a Git token only to explicit commit/guard steps. */
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { appendFile, lstat, mkdir, open, realpath, writeFile } from 'node:fs/promises';
import { dirname, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';

const exec = promisify(execFile), REPO = 'MathCSN/voyagesansdetour';
const API = `https://api.github.com/repos/${REPO}`;
const END = Date.parse('2027-09-14T23:59:59+02:00');
const SHA = /^[0-9a-f]{40}$/, HASH = /^[0-9a-f]{64}$/;
const ID = /^[a-z0-9][a-z0-9-]{0,95}$/, BATCH = /^[a-z0-9][a-z0-9._-]{0,99}$/;
const PREFIX = '.github/vsd-production', NAMES = ['reel.mp4', 'poster.jpg', 'credits.txt', 'dmsans-OFL.txt', 'playfairdisplay-OFL.txt'];
const sha = value => createHash('sha256').update(value).digest('hex');
const encode = value => Buffer.from(JSON.stringify(value, null, 2) + '\n');
class Refused extends Error { constructor(code) { super(code); this.code = code; } }
const check = (value, code) => { if (!value) throw new Refused(code); };
const safeId = (value, pattern) => typeof value === 'string' && pattern.test(value);
function active(now = Date.now) { const clock = now(); check(Number.isSafeInteger(clock) && clock <= END, 'authorised_period_ended'); }
async function git(root, args, maxBuffer = 4 * 1024 * 1024) {
  const result = await exec('git', ['-C', root, ...args], { maxBuffer, timeout: 30000 }); return result.stdout.trimEnd();
}
async function file(root, relative, maximum = 512 * 1024) {
  check(typeof relative === 'string' && /^[A-Za-z0-9._/-]+$/.test(relative) &&
    relative.split('/').every(part => part && part !== '.' && part !== '..'), 'unsafe_path');
  const base = resolve(root), target = resolve(base, relative); let cursor = base;
  check(await realpath(base) === base && target.startsWith(base + sep), 'unsafe_root');
  for (const part of relative.split('/')) { cursor = resolve(cursor, part); check(!(await lstat(cursor)).isSymbolicLink(), 'symlink_refused'); }
  const handle = await open(target, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const before = await handle.stat(); check(before.isFile() && before.size <= maximum, 'file_limit');
    const bytes = await handle.readFile(), after = await handle.stat();
    check(bytes.length === before.size && after.size === before.size && after.mtimeMs === before.mtimeMs, 'file_changed'); return bytes;
  } finally { await handle.close(); }
}

export function validatePromotionReport(report, mode) {
  check(['stage', 'finalize'].includes(mode) && report && typeof report === 'object' && !Array.isArray(report), 'report_invalid');
  const statuses = mode === 'stage' ? ['stage_ready', 'finalization_ready', 'already_finalized', 'idle'] : ['finalized', 'already_finalized'];
  check(statuses.includes(report.status) && Array.isArray(report.changedPaths) && report.changedPaths.length <= 12 &&
    new Set(report.changedPaths).size === report.changedPaths.length, 'report_invalid');
  const idle = mode === 'stage' && ['idle', 'already_finalized'].includes(report.status);
  if (idle) { check(report.changedPaths.length === 0, 'idle_changed_files'); return { status: report.status, changedPaths: [], idle: true, requiresDeployment: false }; }
  const { contentId, batchId } = report;
  check(safeId(contentId, ID) && safeId(batchId, BATCH), 'report_identity');
  const root = `${PREFIX}/promotion`, allowed = mode === 'stage'
    ? new Set(['site-src/public-media.json', ...NAMES.map(name => `site-src/social-media/production/${contentId}/${name}`),
      ...['control', 'candidates', 'staged'].map(folder => `${root}/${folder}/${batchId}.json`)])
    : new Set([...['control', 'proofs', 'reviewed'].map(folder => `${root}/${folder}/${batchId}.json`),
      `${PREFIX}/reviewed-social/${batchId}.json`, `${PREFIX}/reviewed-social/index.json`]);
  check(report.changedPaths.every(path => typeof path === 'string' && allowed.has(path)), 'write_outside_allowlist');
  if (mode === 'stage') check(report.requiresDeployment === (report.status === 'stage_ready'), 'deployment_decision_invalid');
  return { status: report.status, contentId, batchId, guideUrl: report.guideUrl,
    changedPaths: [...report.changedPaths], idle: false, requiresDeployment: mode === 'stage' && report.requiresDeployment };
}

function client({ request = globalThis.fetch, token = process.env.GH_TOKEN, now = Date.now } = {}) {
  check(typeof request === 'function' && typeof token === 'string' && token.length >= 10 && !/\s/.test(token), 'git_token_missing');
  async function call(path, { method = 'GET', body } = {}) {
    active(now); check(/^\/(?:git\/(?:ref\/heads\/main|refs\/heads\/main|commits(?:\/[0-9a-f]{40})?|trees(?:\/[0-9a-f]{40})?|blobs))$/.test(path), 'github_path_refused');
    const response = await request(API + path, { method, redirect: 'error', signal: AbortSignal.timeout(15000),
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json' }, ...(body ? { body: JSON.stringify(body) } : {}) });
    check(response?.status >= 200 && response.status < 300 && !response.redirected, 'github_request_unconfirmed');
    const reader = response.body?.getReader(); check(reader, 'github_response_invalid');
    const chunks = []; let size = 0;
    try {
      while (true) { const part = await reader.read(); if (part.done) break; size += part.value.length;
        check(size <= 1024 * 1024, 'github_response_limit'); chunks.push(part.value); }
      return JSON.parse(Buffer.concat(chunks, size).toString('utf8'));
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  }
  async function head() { const result = await call('/git/ref/heads/main'); check(safeId(result?.object?.sha, SHA), 'head_invalid'); return result.object.sha; }
  async function tree(commitSha) {
    check(safeId(commitSha, SHA), 'commit_invalid'); const commit = await call('/git/commits/' + commitSha);
    check(safeId(commit?.tree?.sha, SHA), 'tree_invalid'); const root = await call('/git/trees/' + commit.tree.sha);
    check(root.truncated !== true && Array.isArray(root.tree), 'tree_invalid');
    const source = root.tree.filter(item => item.path === 'site-src');
    check(source.length === 1 && source[0].type === 'tree' && safeId(source[0].sha, SHA), 'public_tree_missing');
    return { rootTree: commit.tree.sha, siteTree: source[0].sha };
  }
  return { call, head, tree };
}

/** Main may advance through metadata commits; public source must remain exact. */
export async function guardPublicTree(expectedTree, options = {}) {
  check(safeId(expectedTree, SHA), 'expected_tree_invalid');
  const api = client(options), head = await api.head(), found = await api.tree(head);
  check(found.siteTree === expectedTree, 'public_source_changed'); return { head, siteTree: found.siteTree };
}

export async function commitPromotion({ repositoryRoot, mode, report }, options = {}) {
  active(options.now); const plan = validatePromotionReport(report, mode), root = resolve(repositoryRoot);
  const base = await git(root, ['rev-parse', 'HEAD']); check(safeId(base, SHA), 'local_head_invalid');
  const siteTree = await git(root, ['rev-parse', 'HEAD:site-src']); check(safeId(siteTree, SHA), 'local_tree_invalid');
  const api = client(options), head = await api.head(); check(head === base, 'head_changed_before_commit');
  const baseTree = await api.tree(base); check(baseTree.siteTree === siteTree, 'checkout_tree_mismatch');
  const tracked = (await git(root, ['diff', '--name-only', '-z', 'HEAD'])).split('\0').filter(Boolean);
  const untracked = (await git(root, ['ls-files', '--others', '--exclude-standard', '-z'])).split('\0').filter(Boolean)
    .filter(path => !path.startsWith('site-src/public/') && !path.startsWith('site-src/__pycache__/'));
  const changed = [...new Set([...tracked, ...untracked])].sort();
  check(JSON.stringify(changed) === JSON.stringify([...plan.changedPaths].sort()), 'unexpected_checkout_changes');
  if (changed.length === 0) return { status: 'unchanged', sourceSha: base, siteTree, ...plan };
  const mutable = new Set(mode === 'stage' ? ['site-src/public-media.json'] : [`${PREFIX}/reviewed-social/index.json`]);
  const tree = []; let total = 0;
  for (const path of changed) {
    const data = await file(root, path, path.endsWith('/reel.mp4') ? 50_000_000 : 2_000_000); total += data.length;
    check(total <= 60_000_000, 'commit_size_limit');
    let exists = true;
    try { await git(root, ['cat-file', '-e', `${base}:${path}`]); } catch { exists = false; }
    check(!exists || mutable.has(path), 'immutable_file_rewrite');
    const blob = await api.call('/git/blobs', { method: 'POST', body: { content: data.toString('base64'), encoding: 'base64' } });
    check(safeId(blob.sha, SHA), 'blob_invalid'); tree.push({ path, mode: '100644', type: 'blob', sha: blob.sha });
  }
  const nextTree = await api.call('/git/trees', { method: 'POST', body: { base_tree: baseTree.rootTree, tree } });
  check(safeId(nextTree.sha, SHA), 'new_tree_invalid');
  const next = await api.call('/git/commits', { method: 'POST', body: {
    message: `${mode === 'stage' ? 'Stage reviewed public media' : 'Record verified immutable social stock'}: ${plan.contentId}`,
    tree: nextTree.sha, parents: [base], author: { name: 'Voyage Sans Détour', email: 'contact@voyagesansdetour.fr' } } });
  check(safeId(next.sha, SHA), 'new_commit_invalid');
  check(await api.head() === base, 'head_changed_before_update');
  // This is a non-force fast-forward, not an atomic HTTP compare-and-swap.
  // The single parent plus the explicit read makes ordinary concurrent sibling
  // commits fail closed. Never replay a ref update after a lost response.
  try {
    const updated = await api.call('/git/refs/heads/main', { method: 'PATCH', body: { sha: next.sha, force: false } });
    check(updated?.object?.sha === next.sha, 'ref_update_unconfirmed');
  } catch {
    check(await api.head() === next.sha, 'ref_update_outcome_uncertain');
  }
  const verified = await api.tree(next.sha);
  if (mode === 'finalize') check(verified.siteTree === siteTree, 'finalization_changed_public_tree');
  return { ...plan, status: 'committed', promotionStatus: plan.status, sourceSha: next.sha, siteTree: verified.siteTree };
}

function guidePath(guideUrl) {
  check(typeof guideUrl === 'string' && /^https:\/\/voyagesansdetour\.fr\/portugal\/[a-z0-9][a-z0-9-]*\/$/.test(guideUrl), 'guide_invalid');
  return 'site-src/public' + new URL(guideUrl).pathname + 'index.html';
}
export async function writeBuildContext({ repositoryRoot, contentId, batchId, guideUrl, outputFile }) {
  active(); check(safeId(contentId, ID) && safeId(batchId, BATCH), 'build_identity_invalid');
  const root = resolve(repositoryRoot), sourceSha = await git(root, ['rev-parse', 'HEAD']), siteTree = await git(root, ['rev-parse', 'HEAD:site-src']);
  check(safeId(sourceSha, SHA) && safeId(siteTree, SHA), 'build_commit_invalid');
  const guide = await file(root, guidePath(guideUrl), 1024 * 1024);
  const context = { schemaVersion: 1, sourceSha, siteTree, contentId, batchId, guideUrl, guideSha256: sha(guide) };
  const bytes = encode(context); await mkdir(dirname(outputFile), { recursive: true }); await writeFile(outputFile, bytes, { flag: 'wx', mode: 0o600 });
  return { ...context, contextSha256: sha(bytes) };
}
export async function verifyBuildContext({ repositoryRoot, contextFile, expectedContextSha256 }) {
  active(); check(safeId(expectedContextSha256, HASH), 'context_hash_invalid');
  const bytes = await file(dirname(resolve(contextFile)), resolve(contextFile).split(sep).at(-1), 8192);
  check(sha(bytes) === expectedContextSha256, 'context_hash_mismatch'); const value = JSON.parse(bytes);
  check(value?.schemaVersion === 1 && Object.keys(value).sort().join(',') === 'batchId,contentId,guideSha256,guideUrl,schemaVersion,siteTree,sourceSha' &&
    safeId(value.sourceSha, SHA) && safeId(value.siteTree, SHA) && safeId(value.contentId, ID) && safeId(value.batchId, BATCH) && safeId(value.guideSha256, HASH), 'context_invalid');
  check(await git(resolve(repositoryRoot), ['rev-parse', 'HEAD:site-src']) === value.siteTree, 'context_public_tree_changed');
  check(sha(await file(resolve(repositoryRoot), guidePath(value.guideUrl), 1024 * 1024)) === value.guideSha256, 'rebuilt_guide_changed'); return value;
}

async function output(values) {
  if (!process.env.GITHUB_OUTPUT) return;
  const lines = [];
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null) continue;
    check(/^[a-z_]+$/.test(key) && !/[\r\n]/.test(String(value)) && String(value).length <= 500, 'output_invalid'); lines.push(`${key}=${value}\n`);
  }
  await appendFile(process.env.GITHUB_OUTPUT, lines.join(''));
}
async function main(args) {
  const mode = args.shift(), values = {};
  check(args.length % 2 === 0, 'arguments_invalid');
  while (args.length) { const key = args.shift(); check(/^--[a-z-]+$/.test(key) && !Object.hasOwn(values, key), 'arguments_invalid'); values[key] = args.shift(); }
  const root = values['--repository-root'] ?? process.cwd();
  if (mode === 'commit') {
    const reportPath = resolve(values['--report']);
    const report = JSON.parse(await file(dirname(reportPath), reportPath.split(sep).at(-1), 32768));
    const result = await commitPromotion({ repositoryRoot: root, mode: values['--mode'], report });
    await output({ source_sha: result.sourceSha, site_tree: result.siteTree, promotion_status: result.promotionStatus ?? result.status,
      content_id: result.contentId, batch_id: result.batchId, guide_url: result.guideUrl, requires_deployment: result.requiresDeployment, idle: result.idle });
  } else if (mode === 'guard') {
    const found = await guardPublicTree(values['--site-tree']); await output({ observed_head: found.head });
  } else if (mode === 'build-context') {
    const result = await writeBuildContext({ repositoryRoot: root, contentId: values['--content-id'], batchId: values['--batch-id'], guideUrl: values['--guide-url'], outputFile: values['--output'] });
    await output({ context_sha256: result.contextSha256, source_sha: result.sourceSha, site_tree: result.siteTree, guide_sha256: result.guideSha256 });
  } else if (mode === 'verify-context') {
    await verifyBuildContext({ repositoryRoot: root, contextFile: values['--context'], expectedContextSha256: values['--sha256'] });
  } else throw new Refused('command_invalid');
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main(process.argv.slice(2)).catch(error => {
    console.error('Media promotion stopped: ' + (error instanceof Refused ? error.code : 'operation_unconfirmed'));
    process.exitCode = 1;
  });
}
