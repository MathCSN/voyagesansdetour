// exploitation/production-contenus/voice-admission.mjs
import { readFile, writeFile, readdir, lstat as lstat2, rename, unlink } from "node:fs/promises";
import { resolve as resolve2, join as join2 } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";
import { createHash as createHash2 } from "node:crypto";

// exploitation/cloud-publications/stock-selection.mjs
import { constants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join, parse, relative, resolve, sep } from "node:path";

// exploitation/cloud-publications/archival-rejection-contract.mjs
var ARCHIVAL_REJECTION = Object.freeze({
  jobId: "vsd-social-launch-2026-09:facebook:aeroport-porto-centre-ville",
  provider: "windsor_mcp_facebook_organic",
  channelId: "1331092223422242",
  payloadRevision: "0109a97268ea7f6c478e9c7832f6fecb96fd7145a3aa674a7c6869adb1486c20",
  responseSha256: "db0b86fcf4ead4d67989d78104a6ee7ff1329dc744e035dd4f85b742df7cd659",
  originalCallAt: "2026-09-27T10:09:43.257Z",
  originalResponseAt: "2026-09-27T10:09:44.452Z",
  targetUrl: "https://voyagesansdetour.fr/portugal/aeroport-porto-centre-ville/"
});

// exploitation/cloud-publications/scheduler.mjs
var CHANNEL_FORMATS = Object.freeze({
  pinterest: Object.freeze(["pin"]),
  instagram: Object.freeze(["image", "carousel", "reel"]),
  facebook: Object.freeze(["post", "image", "photos", "video", "reel"]),
  tiktok: Object.freeze(["image", "photos", "video"]),
  blog: Object.freeze(["guide", "update"])
});
var CADENCE_CEILINGS = Object.freeze({
  pinterest: { limit: 2, windowHours: 168 },
  instagram: { limit: 2, windowHours: 168 },
  facebook: { limit: 2, windowHours: 168 },
  tiktok: { limit: 2, windowHours: 168 },
  blog: { limit: 1, windowHours: 336 }
});
var DEFAULT_POLICY = Object.freeze({
  enabled: false,
  maxAttempts: 3,
  leaseSeconds: 300,
  retryBaseSeconds: 900,
  retryMaxSeconds: 86400,
  maxDispatchPerTick: 3,
  paidCallsAllowed: false,
  // Explicit opt-in. Only reviewed Buffer social jobs may use this lead time.
  scheduleAheadSeconds: 0,
  cadence: Object.freeze({
    pinterest: Object.freeze({ limit: 2, windowHours: 168 }),
    instagram: Object.freeze({ limit: 1, windowHours: 168 }),
    facebook: Object.freeze({ limit: 0, windowHours: 168 }),
    tiktok: Object.freeze({ limit: 0, windowHours: 168 }),
    blog: Object.freeze({ limit: 1, windowHours: 336 })
  }),
  enabledFormats: Object.freeze({
    pinterest: Object.freeze(["pin"]),
    instagram: Object.freeze(["reel"]),
    facebook: Object.freeze([]),
    tiktok: Object.freeze([]),
    blog: Object.freeze(["guide", "update"])
  })
});
var ACTIVE = /* @__PURE__ */ new Set(["reserved", "submitting", "accepted", "submitted_import_pending", "unknown"]);
var OPERATION_STATES = /* @__PURE__ */ new Set([...ACTIVE, "published", "not_created", "conflicted"]);
var GuardError = class extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = "GuardError";
    this.code = code;
  }
};

// exploitation/cloud-publications/annual-store.mjs
var MiB = 1024 * 1024;
var ANNUAL_STORE_LIMITS = Object.freeze({
  maxStateBytes: 5 * MiB,
  maxChannelBytes: MiB,
  maxJobs: 1024,
  maxJobsPerChannel: 256,
  maxOperations: 3072,
  maxOperationsPerChannel: 768
});
var encoder = new TextEncoder();

// exploitation/cloud-publications/buffer-transport.mjs
var HASH = /^[a-f0-9]{64}$/;
var TYPES = { instagram: ["business"], facebook: ["page"], tiktok: ["profile", "account", "business"] };
var POST_FIELDS = "id channelId status schedulingType dueAt sentAt externalLink";
var CREATE = `mutation BufferPublish($input: CreatePostInput!) { createPost(input: $input) {
  __typename ... on PostActionSuccess { post { ${POST_FIELDS} } } ... on MutationError { message }
} }`;
var POST_QUERY = `query BufferReceipt($input: PostInput!) { post(input: $input) { ${POST_FIELDS} } }`;
var POSTS_QUERY = `query BufferLostReceipt($input: PostsInput!) { posts(first: 20, input: $input) {
  edges { node { ${POST_FIELDS} createdAt text assets { type mimeType source }
    metadata { __typename ... on FacebookPostMetadata { type }
      ... on InstagramPostMetadata { type isAiGenerated shouldShareToFeed } }
  } } pageInfo { hasNextPage }
} }`;
var LOOKUP_WINDOW_MS = 15 * 60 * 1e3;
var encoder2 = new TextEncoder();
function check(value, code) {
  if (!value) throw new GuardError(code);
}
function nonempty(value, max = 1e3) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}
function https(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && !url.port && !url.search && !url.hash ? url : null;
  } catch {
    return null;
  }
}
function exactKeys(value, allowed) {
  return value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).every((key) => allowed.includes(key));
}
async function bufferSha256(value) {
  const bytes2 = typeof value === "string" ? encoder2.encode(value) : value;
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes2))].map((n) => n.toString(16).padStart(2, "0")).join("");
}
function canonicalPayload(value) {
  check(exactKeys(value, ["schemaVersion", "channel", "kind", "text", "aiGenerated", "tiktokTitle", "assets"]) && value.schemaVersion === 1, "buffer_payload_invalid");
  check(Object.hasOwn(TYPES, value.channel) && CHANNEL_FORMATS[value.channel].includes(value.kind), "buffer_payload_format_invalid");
  check(typeof value.text === "string" && value.text.length <= (value.channel === "facebook" ? 5e3 : 2200) && typeof value.aiGenerated === "boolean", "buffer_payload_text_invalid");
  check(Array.isArray(value.assets) && value.assets.length <= 10, "buffer_payload_assets_invalid");
  const assets = value.assets.map((asset) => {
    check(exactKeys(asset, ["url", "sha256", "mimeType", "altText"]) && https(asset.url) && asset.url.length <= 2048 && HASH.test(asset.sha256), "buffer_payload_asset_invalid");
    check(["image/jpeg", "image/png", "image/webp", "video/mp4"].includes(asset.mimeType), "buffer_media_type_unsupported");
    check(asset.altText === void 0 || typeof asset.altText === "string" && asset.altText.length <= 1e3, "buffer_alt_text_invalid");
    return { url: asset.url, sha256: asset.sha256, mimeType: asset.mimeType, altText: asset.altText ?? null };
  });
  check(value.tiktokTitle === void 0 || value.channel === "tiktok" && ["image", "photos"].includes(value.kind) && nonempty(value.tiktokTitle, 90), "buffer_tiktok_title_invalid");
  return { schemaVersion: 1, channel: value.channel, kind: value.kind, text: value.text, aiGenerated: value.aiGenerated, tiktokTitle: value.tiktokTitle ?? null, assets };
}
async function bufferPayloadRevision(payload) {
  return bufferSha256(JSON.stringify(canonicalPayload(payload)));
}

// exploitation/cloud-publications/payload-store.mjs
var REVIEWED_PAYLOAD_LIMITS = Object.freeze({
  maxRefLength: 256,
  maxPayloadBytes: 64 * 1024,
  maxPayloads: 1024
});
var encoder3 = new TextEncoder();

// exploitation/cloud-publications/publication-extension.mjs
var PUBLICATION_EXTENSION_LIMITS = Object.freeze({ maxItems: 4, maxBatchBytes: 128 * 1024 });
var check2 = (ok, code) => {
  if (!ok) throw new GuardError(code);
};
var encoder4 = new TextEncoder();
function stableJson(value, depth = 0, budget = { nodes: 0 }) {
  check2(depth <= 24 && ++budget.nodes <= 2e4, "extension_batch_too_complex");
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    check2(value.length <= 65536, "extension_batch_too_large");
    return value;
  }
  if (typeof value === "number") {
    check2(Number.isFinite(value), "extension_batch_invalid");
    return value;
  }
  check2(typeof value === "object" && (Array.isArray(value) || Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null), "extension_batch_invalid");
  if (Array.isArray(value)) return value.map((item) => stableJson(item, depth + 1, budget));
  const result = {};
  for (const key of Object.keys(value).sort()) {
    check2(!["__proto__", "constructor", "prototype"].includes(key) && key.length <= 256, "extension_batch_invalid");
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check2(descriptor && Object.hasOwn(descriptor, "value"), "extension_batch_invalid");
    result[key] = stableJson(descriptor.value, depth + 1, budget);
  }
  return result;
}
function canonicalPublicationJson(value) {
  return stableJson(value);
}

// exploitation/cloud-publications/stock-status.mjs
var STOCK_STATUS_LIMITS = Object.freeze({ maxDescriptors: 8, maxDescriptorBytes: 8192, maxBundleBytes: 262144 });
var encoder5 = new TextEncoder();
var HASH2 = /^[a-f0-9]{64}$/;
var BATCH = /^[a-z0-9][a-z0-9._-]{0,99}$/;
var ISO = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/;
var check3 = (value, code = "stock_status_invalid") => {
  if (!value) throw new GuardError(code);
};
var plain = (value) => value !== null && typeof value === "object" && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
var identity = (value) => typeof value === "string" && value.length > 0 && value.length <= 200 && value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value);
var exact = (value, fields) => plain(value) && Object.keys(value).sort().join(",") === [...fields].sort().join(",");
var bytes = (value) => encoder5.encode(value).byteLength;
var hash = (value) => typeof value === "string" && HASH2.test(value);
var batchIdentity = (value) => typeof value === "string" && BATCH.test(value);
function timestamp(value) {
  if (typeof value !== "string" || !ISO.test(value) || !Number.isFinite(Date.parse(value))) return false;
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1] && Number(value.slice(11, 13)) <= 23 && Number(value.slice(14, 16)) <= 59 && Number(value.slice(17, 19)) <= 59;
}
function jsonData(value, maximum, depth = 0, budget = { nodes: 0, bytes: 0 }) {
  check3(depth <= 24 && ++budget.nodes <= 2e4);
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "number") {
    check3(Number.isFinite(value));
    return value;
  }
  if (typeof value === "string") {
    budget.bytes += bytes(value);
    check3(value.length <= 65536 && budget.bytes <= maximum);
    return value;
  }
  const array = Array.isArray(value);
  check3(array || plain(value));
  const keys = Reflect.ownKeys(value), copy = array ? [] : {};
  if (array) check3(value.length <= 2e4 && keys.length === value.length + 1);
  for (const key of keys) {
    if (array && key === "length") continue;
    check3(typeof key === "string" && key.length <= 256 && !["__proto__", "constructor", "prototype"].includes(key));
    if (array) check3(/^(?:0|[1-9]\d*)$/.test(key) && Number(key) < value.length);
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check3(descriptor?.enumerable === true && Object.hasOwn(descriptor, "value"));
    budget.bytes += bytes(key);
    check3(budget.bytes <= maximum);
    copy[key] = jsonData(descriptor.value, maximum, depth + 1, budget);
  }
  return copy;
}
function validateStockDescriptors(descriptors) {
  const copy = jsonData(descriptors, STOCK_STATUS_LIMITS.maxDescriptorBytes);
  check3(Array.isArray(copy) && copy.length >= 1 && copy.length <= STOCK_STATUS_LIMITS.maxDescriptors);
  check3(bytes(JSON.stringify(copy)) <= STOCK_STATUS_LIMITS.maxDescriptorBytes);
  const batchIds = /* @__PURE__ */ new Set(), itemIds = /* @__PURE__ */ new Set();
  for (const item of copy) {
    check3(exact(item, ["batchId", "batchSha256", "itemIds"]) && batchIdentity(item.batchId) && hash(item.batchSha256));
    check3(Array.isArray(item.itemIds) && item.itemIds.length === 1 && identity(item.itemIds[0]));
    check3(!batchIds.has(item.batchId) && !itemIds.has(item.itemIds[0]));
    batchIds.add(item.batchId);
    itemIds.add(item.itemIds[0]);
    Object.freeze(item.itemIds);
    Object.freeze(item);
  }
  return Object.freeze(copy);
}
async function describeStockBatch(batch) {
  const source = canonicalPublicationJson(jsonData(batch, PUBLICATION_EXTENSION_LIMITS.maxBatchBytes));
  check3(bytes(JSON.stringify(source)) <= PUBLICATION_EXTENSION_LIMITS.maxBatchBytes);
  check3(exact(source, ["schemaVersion", "batchId", "items"]) && source.schemaVersion === 1 && batchIdentity(source.batchId) && Array.isArray(source.items) && source.items.length === 1);
  const item = source.items[0], payload = item?.payload, review = item?.review;
  check3(exact(item, ["contentId", "deduplicationKey", "title", "dueAt", "payload", "review"]) && identity(item.contentId) && identity(item.deduplicationKey) && identity(item.title) && timestamp(item.dueAt));
  const instagramReel = payload?.channel === "instagram" && payload.kind === "reel";
  const facebookPhotos = payload?.channel === "facebook" && payload.kind === "photos";
  check3(payload?.schemaVersion === 1 && (instagramReel || facebookPhotos) && Array.isArray(payload.assets) && (instagramReel ? payload.assets.length === 1 && payload.assets[0]?.mimeType === "video/mp4" : payload.assets.length >= 2 && payload.assets.length <= 10 && payload.aiGenerated === false && payload.assets.every((asset) => ["image/jpeg", "image/png", "image/webp"].includes(asset?.mimeType))));
  check3(review?.schemaVersion === 1 && review.contentId === item.contentId && review.approved === true && hash(review.payloadRevision) && review.payloadRevision === await bufferPayloadRevision(payload) && review.checks?.requiresPaidCall === false);
  return validateStockDescriptors([{
    batchId: source.batchId,
    batchSha256: await bufferSha256(JSON.stringify(source)),
    itemIds: [item.contentId]
  }])[0];
}

// exploitation/cloud-publications/stock-selection.mjs
var STOCK_SELECTION_LIMITS = Object.freeze({
  maxBatches: 64,
  pageSize: 8,
  maxPages: 8,
  maxIndexBytes: 64 * 1024,
  maxBatchBytes: 128 * 1024,
  maxResponseBytes: 32 * 1024,
  maxStatusAgeMs: 6e4
});
var PREFIX = ".github/vsd-production/reviewed-social/";
var HASH3 = /^[a-f0-9]{64}$/;
var BATCH_ID = /^[a-z0-9][a-z0-9._-]{0,99}$/;
var sha = (value) => createHash("sha256").update(value).digest("hex");
var Refused = class extends Error {
  constructor(code) {
    super("Stock selection refused: " + code);
    this.name = "StockSelectionError";
  }
};
var check4 = (value, code) => {
  if (!value) throw new Refused(code);
};
var plain2 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
var exact2 = (value, keys) => plain2(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
var safeError = (error) => error instanceof Refused ? error : new Refused("invalid_input");
var same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function jsonCopy(value, depth = 0, budget = { nodes: 0, bytes: 0 }) {
  check4(depth <= 24 && ++budget.nodes <= 2e4, "json_too_complex");
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    budget.bytes += Buffer.byteLength(value);
    check4(value.length <= 65536 && budget.bytes <= STOCK_SELECTION_LIMITS.maxBatchBytes, "json_too_large");
    return value;
  }
  if (typeof value === "number") {
    check4(Number.isFinite(value), "invalid_json");
    return value;
  }
  check4(Array.isArray(value) || plain2(value), "invalid_json");
  const array = Array.isArray(value), copy = array ? [] : {}, keys = Reflect.ownKeys(value);
  if (array) check4(value.length <= 2e4 && keys.length === value.length + 1, "invalid_json");
  for (const key of keys) {
    if (array && key === "length") continue;
    check4(typeof key === "string" && key.length <= 256 && !["__proto__", "constructor", "prototype"].includes(key), "invalid_json");
    if (array) check4(/^(?:0|[1-9]\d*)$/.test(key) && Number(key) < value.length, "invalid_json");
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check4(descriptor?.enumerable === true && Object.hasOwn(descriptor, "value"), "invalid_json");
    budget.bytes += Buffer.byteLength(key);
    check4(budget.bytes <= STOCK_SELECTION_LIMITS.maxBatchBytes, "json_too_large");
    copy[key] = jsonCopy(descriptor.value, depth + 1, budget);
  }
  return Object.freeze(copy);
}
function boundedJson(bytes2, limit) {
  check4(Buffer.isBuffer(bytes2) && bytes2.length > 0 && bytes2.length <= limit, "file_size");
  return jsonCopy(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes2)));
}
function instant(value) {
  check4(typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value), "invalid_timestamp");
  const result = Date.parse(value);
  check4(Number.isSafeInteger(result) && result > 0 && new Date(result).toISOString().slice(0, 19) === value.slice(0, 19), "invalid_timestamp");
  return result;
}
function indexSnapshot(value) {
  const index = jsonCopy(value);
  check4(Buffer.byteLength(JSON.stringify(index)) <= STOCK_SELECTION_LIMITS.maxIndexBytes && exact2(index, Object.hasOwn(index, "retirements") ? ["schemaVersion", "items", "retirements"] : ["schemaVersion", "items"]) && index.schemaVersion === 1 && Array.isArray(index.items) && index.items.length <= STOCK_SELECTION_LIMITS.maxBatches, "invalid_index");
  const paths = /* @__PURE__ */ new Set(), batches = /* @__PURE__ */ new Set(), itemIds = /* @__PURE__ */ new Set();
  for (const entry of index.items) {
    check4(exact2(entry, ["path", "fileSha256", "batchId", "batchSha256", "itemIds"]) && typeof entry.batchId === "string" && BATCH_ID.test(entry.batchId) && !/^current(?:[._-]|$)/.test(entry.batchId) && entry.batchId !== "index" && entry.path === PREFIX + entry.batchId + ".json" && typeof entry.fileSha256 === "string" && HASH3.test(entry.fileSha256) && typeof entry.batchSha256 === "string" && HASH3.test(entry.batchSha256), "invalid_index_entry");
    validateStockDescriptors([{ batchId: entry.batchId, batchSha256: entry.batchSha256, itemIds: entry.itemIds }]);
    check4(!paths.has(entry.path) && !batches.has(entry.batchId) && entry.itemIds.every((id) => !itemIds.has(id)), "duplicate_index_identity");
    paths.add(entry.path);
    batches.add(entry.batchId);
    entry.itemIds.forEach((id) => itemIds.add(id));
  }
  const retired = /* @__PURE__ */ new Set();
  if (Object.hasOwn(index, "retirements")) {
    check4(Array.isArray(index.retirements) && index.retirements.length <= index.items.length, "invalid_retirements");
    for (const record of index.retirements) {
      check4(exact2(record, ["batchId", "batchSha256", "fileSha256", "itemIds", "retiredAt", "reason", "evidenceUrl", "existingPublicationUrl"]), "invalid_retirement");
      const entry = index.items.find((item) => item.batchId === record.batchId);
      check4(entry && !retired.has(record.batchId) && record.batchSha256 === entry.batchSha256 && record.fileSha256 === entry.fileSha256 && same(record.itemIds, entry.itemIds) && record.reason === "duplicate_media_on_channel" && /^https:\/\/github\.com\/MathCSN\/voyagesansdetour\/actions\/runs\/[1-9]\d*$/.test(record.evidenceUrl) && /^https:\/\/www\.facebook\.com\/[1-9]\d*\/posts\/[1-9]\d*$/.test(record.existingPublicationUrl), "invalid_retirement");
      instant(record.retiredAt);
      retired.add(record.batchId);
    }
  }
  return index;
}
function relativePath(value) {
  check4(typeof value === "string" && value.length <= 250 && /^[A-Za-z0-9._/-]+$/.test(value) && value.split("/").every((part) => part && part !== "." && part !== ".."), "unsafe_path");
  return value;
}
async function noLinks(path, directory = false) {
  const absolute = resolve(path), base = parse(absolute).root;
  let current = base;
  for (const part of relative(base, absolute).split(sep).filter(Boolean)) {
    current = join(current, part);
    const info = await lstat(current);
    check4(!info.isSymbolicLink(), "symbolic_link");
    if (current !== absolute || directory) check4(info.isDirectory(), "directory_required");
  }
  check4(await realpath(absolute) === absolute, "noncanonical_path");
  return absolute;
}
async function readSafe(root, name, limit) {
  relativePath(name);
  const path = join(root, name);
  await noLinks(path);
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const before = await handle.stat();
    check4(before.isFile() && before.size > 0 && before.size <= limit, "file_size");
    const bytes2 = await handle.readFile(), after = await handle.stat();
    check4(bytes2.length === before.size && after.size === before.size && before.mtimeMs === after.mtimeMs, "file_changed");
    return bytes2;
  } finally {
    await handle.close();
  }
}
async function loadStockIndex({ repositoryRoot, indexFile = PREFIX + "index.json" } = {}) {
  try {
    check4(typeof repositoryRoot === "string", "invalid_root");
    const root = await noLinks(repositoryRoot, true);
    const index = indexSnapshot(boundedJson(await readSafe(root, indexFile, STOCK_SELECTION_LIMITS.maxIndexBytes), STOCK_SELECTION_LIMITS.maxIndexBytes));
    const files = /* @__PURE__ */ new Map();
    for (const entry of index.items) files.set(entry.path, await readSafe(root, entry.path, STOCK_SELECTION_LIMITS.maxBatchBytes));
    await snapshotBatches({ index, files });
    return { index, files };
  } catch (error) {
    throw safeError(error);
  }
}
async function snapshotBatches(input) {
  const index = indexSnapshot(input?.index), files = input?.files;
  check4(files instanceof Map && files.size === index.items.length, "invalid_files");
  const snapshots = [];
  for (const entry of index.items) {
    const original = files.get(entry.path);
    check4(Buffer.isBuffer(original) && original.length <= STOCK_SELECTION_LIMITS.maxBatchBytes, "file_size");
    const bytes2 = Buffer.from(original);
    check4(sha(bytes2) === entry.fileSha256, "file_hash_mismatch");
    const batch = boundedJson(bytes2, STOCK_SELECTION_LIMITS.maxBatchBytes), descriptor = await describeStockBatch(batch);
    check4(descriptor.batchId === entry.batchId && descriptor.batchSha256 === entry.batchSha256 && same(descriptor.itemIds, entry.itemIds), "batch_descriptor_mismatch");
    snapshots.push({ entry, batch, descriptor, retirement: index.retirements?.find((record) => record.batchId === entry.batchId) ?? null });
  }
  return snapshots;
}

// exploitation/production-contenus/voice-admission.mjs
var STOP = Date.parse("2027-09-14T21:59:59Z");
var sha2 = (x) => createHash2("sha256").update(x).digest("hex");
async function exists(path) {
  try {
    const info = await lstat2(path);
    if (info.isSymbolicLink()) throw Error("symlink");
    return true;
  } catch (e) {
    if (e.code === "ENOENT") return false;
    throw e;
  }
}
async function directories(path) {
  if (!await exists(path)) return [];
  const entries = await readdir(path, { withFileTypes: true });
  if (entries.some((e) => !e.isDirectory() || e.isSymbolicLink())) throw Error("invalid_directory");
  return entries.map((e) => join2(path, e.name)).sort();
}
async function runVoiceAdmission({ repositoryRoot, now = () => Date.now(), build } = {}) {
  if (now() >= STOP) return { status: "period_ended", changed: false };
  const root = resolve2(repositoryRoot), production = join2(root, ".github/vsd-production");
  const snapshot = await loadStockIndex({ repositoryRoot: root });
  const occupied = [], existing = /* @__PURE__ */ new Map();
  for (const raw of snapshot.files.values()) for (const item of JSON.parse(raw).items) {
    if (item.payload.channel === "instagram") occupied.push(item.dueAt);
    existing.set(item.contentId, item);
  }
  const families = await directories(join2(production, "voice-revisions"));
  if (families.length > 16) throw Error("family_bound");
  const candidates = [];
  for (const folder of [join2(production, "voice-stock"), ...families]) candidates.push(...await directories(folder));
  if (candidates.length > 64) throw Error("candidate_bound");
  const skipped = [];
  for (const candidate of candidates) {
    const name = candidate.split("/").at(-1);
    if (!/^reel-article-[a-z0-9-]+$/.test(name)) throw Error("candidate_identity");
    if (!await exists(join2(candidate, "selection.json")) || !await exists(join2(candidate, "public-media-proof.json"))) continue;
    const selection = JSON.parse(await readFile(join2(candidate, "selection.json"), "utf8"));
    if (selection.contentId !== name) throw Error("selection_identity");
    const id = "vsd-production:instagram:" + name.slice("reel-article-".length) + ":voice-v1";
    if (existing.has(id)) {
      const item2 = existing.get(id);
      if (item2.payload.assets.length !== 1 || item2.payload.assets[0].sha256 !== selection.mediaSha256) throw Error("existing_content_conflict");
      skipped.push(id);
      continue;
    }
    if ([...existing.values()].some((item2) => item2.payload.channel === "instagram" && item2.payload.assets.some((asset) => asset.sha256 === selection.mediaSha256))) throw Error("existing_media_conflict");
    if (now() >= Date.parse(selection.validUntil)) continue;
    const context = { candidate, site: join2(root, "site-src"), occupied };
    const result = build ? await build(context) : JSON.parse(execFileSync("python", [join2(production, "voice/social_draft.py")], { input: JSON.stringify(context), encoding: "utf8", timeout: 15e4, maxBuffer: 128 * 1024 }));
    if (result.status !== "batch_prepared_not_imported") return { status: result.status, changed: false, id };
    const batch = result.batch;
    if (batch.items.length !== 1 || batch.items[0].contentId !== id) throw Error("batch_identity");
    const item = batch.items[0];
    item.review.payloadRevision = await bufferPayloadRevision(item.payload);
    if (now() >= Date.parse(item.review.validUntil) || Date.parse(item.dueAt) >= Date.parse(item.review.validUntil)) throw Error("expired_batch");
    const descriptor = await describeStockBatch(batch), path = ".github/vsd-production/reviewed-social/" + batch.batchId + ".json";
    const raw = JSON.stringify(batch, null, 2) + "\n";
    if (await exists(join2(root, path))) throw Error("existing_unindexed_batch_preserved");
    const indexPath = join2(production, "reviewed-social/index.json"), before = await readFile(indexPath);
    const index = JSON.parse(before);
    if (index.items.length >= 64) throw Error("stock_index_bound");
    index.items.push({ path, fileSha256: sha2(raw), ...descriptor });
    await writeFile(join2(root, path), raw, { flag: "wx" });
    const temporary = indexPath + ".voice-new";
    try {
      await writeFile(temporary, JSON.stringify(index, null, 2) + "\n", { flag: "wx" });
      if (sha2(await readFile(indexPath)) !== sha2(before)) throw Error("index_changed");
      await rename(temporary, indexPath);
    } finally {
      if (await exists(temporary)) await unlink(temporary);
    }
    await loadStockIndex({ repositoryRoot: root });
    return { status: "reviewed_batch_indexed_not_imported", changed: true, batchId: batch.batchId, id, dueAt: item.dueAt, publicationAttempted: false };
  }
  return { status: "no_new_public_voice_media", changed: false, skipped };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve2(process.argv[1])).href) {
  try {
    console.log(JSON.stringify(await runVoiceAdmission({ repositoryRoot: process.cwd() })));
  } catch (error) {
    console.error("Voice admission stopped:", error.message);
    process.exitCode = 1;
  }
}
export {
  runVoiceAdmission
};
