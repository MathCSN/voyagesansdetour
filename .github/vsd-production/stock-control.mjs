// exploitation/cloud-publications/stock-control.mjs
import { createHash as createHash2, createHmac, randomUUID } from "node:crypto";
import { writeFile, realpath as realpath2 } from "node:fs/promises";
import { resolve as resolve2 } from "node:path";
import { pathToFileURL } from "node:url";

// exploitation/cloud-publications/stock-selection.mjs
import { constants } from "node:fs";
import { lstat, open, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
import { join, parse, relative, resolve, sep } from "node:path";

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
var POST_FIELDS = "id channelId status schedulingType sentAt externalLink";
var CREATE = `mutation BufferPublish($input: CreatePostInput!) { createPost(input: $input) {
  __typename ... on PostActionSuccess { post { ${POST_FIELDS} } } ... on MutationError { message }
} }`;
var POST_QUERY = `query BufferReceipt($input: PostInput!) { post(input: $input) { ${POST_FIELDS} } }`;
var POSTS_QUERY = `query BufferLostPhotoReceipt($input: PostsInput!) { posts(first: 20, input: $input) {
  edges { node { ${POST_FIELDS} createdAt text assets { type mimeType source }
    metadata { __typename ... on FacebookPostMetadata { type } }
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
async function stockDescriptorsHash(descriptors) {
  return bufferSha256(JSON.stringify(canonicalPublicationJson(validateStockDescriptors(descriptors))));
}
async function describeStockBatch(batch) {
  const source = canonicalPublicationJson(jsonData(batch, PUBLICATION_EXTENSION_LIMITS.maxBatchBytes));
  check3(bytes(JSON.stringify(source)) <= PUBLICATION_EXTENSION_LIMITS.maxBatchBytes);
  check3(exact(source, ["schemaVersion", "batchId", "items"]) && source.schemaVersion === 1 && batchIdentity(source.batchId) && Array.isArray(source.items) && source.items.length === 1);
  const item = source.items[0], payload = item?.payload, review = item?.review;
  check3(exact(item, ["contentId", "deduplicationKey", "title", "dueAt", "payload", "review"]) && identity(item.contentId) && identity(item.deduplicationKey) && identity(item.title) && timestamp(item.dueAt));
  const instagramReel = payload?.schemaVersion === 1 && payload.channel === "instagram" && payload.kind === "reel" && Array.isArray(payload.assets) && payload.assets.length === 1 && payload.assets[0]?.mimeType === "video/mp4";
  const facebookPhotos = payload?.schemaVersion === 1 && payload.channel === "facebook" && payload.kind === "photos" && payload.aiGenerated === false && Array.isArray(payload.assets) && payload.assets.length >= 2 && payload.assets.length <= 10 && payload.assets.every((asset) => ["image/jpeg", "image/png", "image/webp"].includes(asset?.mimeType));
  check3(instagramReel || facebookPhotos);
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
  check4(typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(value), "invalid_timestamp");
  const result = Date.parse(value);
  check4(Number.isSafeInteger(result) && result > 0 && new Date(result).toISOString().slice(0, 19) === value.slice(0, 19), "invalid_timestamp");
  return result;
}
function indexSnapshot(value) {
  const index = jsonCopy(value);
  check4(Buffer.byteLength(JSON.stringify(index)) <= STOCK_SELECTION_LIMITS.maxIndexBytes && exact2(index, ["schemaVersion", "items"]) && index.schemaVersion === 1 && Array.isArray(index.items) && index.items.length <= STOCK_SELECTION_LIMITS.maxBatches, "invalid_index");
  const paths = /* @__PURE__ */ new Set(), batches = /* @__PURE__ */ new Set(), itemIds = /* @__PURE__ */ new Set();
  for (const entry of index.items) {
    check4(exact2(entry, ["path", "fileSha256", "batchId", "batchSha256", "itemIds"]) && typeof entry.batchId === "string" && BATCH_ID.test(entry.batchId) && !/^current(?:[._-]|$)/.test(entry.batchId) && entry.batchId !== "index" && entry.path === PREFIX + entry.batchId + ".json" && typeof entry.fileSha256 === "string" && HASH3.test(entry.fileSha256) && typeof entry.batchSha256 === "string" && HASH3.test(entry.batchSha256), "invalid_index_entry");
    validateStockDescriptors([{ batchId: entry.batchId, batchSha256: entry.batchSha256, itemIds: entry.itemIds }]);
    check4(!paths.has(entry.path) && !batches.has(entry.batchId) && entry.itemIds.every((id) => !itemIds.has(id)), "duplicate_index_identity");
    paths.add(entry.path);
    batches.add(entry.batchId);
    entry.itemIds.forEach((id) => itemIds.add(id));
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
    snapshots.push({ entry, batch, descriptor });
  }
  return snapshots;
}
function statusResponse(raw, descriptors, requestSha256, receivedAt) {
  const response = jsonCopy(raw);
  check4(Buffer.byteLength(JSON.stringify(response)) <= STOCK_SELECTION_LIMITS.maxResponseBytes, "response_too_large");
  if (response?.status !== "stock_checked") {
    check4(exact2(response, ["kind", "status"]) && response.kind === "publications" && ["busy", "disabled", "refused", "unavailable"].includes(response.status), "invalid_status_response");
    return { unavailable: response.status };
  }
  check4(exact2(response, ["kind", "status", "schemaVersion", "checkedAt", "requestSha256", "revision", "batches"]) && response.kind === "publications" && response.schemaVersion === 1 && response.requestSha256 === requestSha256 && Number.isSafeInteger(response.revision) && response.revision >= 0 && Array.isArray(response.batches) && response.batches.length === descriptors.length, "invalid_status_response");
  const checkedAt = instant(response.checkedAt);
  check4(checkedAt <= receivedAt && receivedAt - checkedAt <= STOCK_SELECTION_LIMITS.maxStatusAgeMs, "stale_status_response");
  const expected = new Map(descriptors.map((item) => [item.batchId, item])), seen = /* @__PURE__ */ new Set();
  for (const row of response.batches) {
    check4(exact2(row, ["batchId", "batchSha256", "state", "itemIds", "importedAt"]) && expected.has(row.batchId) && !seen.has(row.batchId), "invalid_status_identity");
    const descriptor = expected.get(row.batchId);
    check4(row.batchSha256 === descriptor.batchSha256 && same(row.itemIds, descriptor.itemIds) && ["imported", "absent", "partial", "conflict"].includes(row.state), "invalid_status_identity");
    if (row.state === "imported") check4(instant(row.importedAt) <= checkedAt, "invalid_import_date");
    else check4(row.importedAt === null, "invalid_import_date");
    seen.add(row.batchId);
  }
  return { response, checkedAt };
}
function absentEligibility(batch, at) {
  const item = batch.items[0], review = item.review;
  const dueAt = instant(item.dueAt), reviewedAt = instant(review.reviewedAt), expiry = instant(review.validUntil);
  check4(reviewedAt < expiry, "invalid_review_dates");
  if (reviewedAt > at) return { eligible: false, reason: "future_review" };
  if (expiry <= Math.max(at, dueAt)) return { eligible: false, reason: "review_expired_or_slot_uncovered" };
  const mediaRecords = batch.items[0].payload.channel === "facebook" ? review.media?.items : [review.media];
  const records = [review.checks?.sources, ...(Array.isArray(mediaRecords) ? mediaRecords : []), review.destination, review.formatCapability];
  for (const record of records) {
    check4(plain2(record) && record.status === "verified", "unverified_absent_batch");
    const observed = instant(record.observedAt), validUntil = instant(record.validUntil);
    check4(observed < validUntil && validUntil <= expiry, "invalid_review_dates");
    if (observed > at) return { eligible: false, reason: "future_verification" };
    if (validUntil <= Math.max(at, dueAt)) return { eligible: false, reason: "verification_expired_or_slot_uncovered" };
  }
  return { eligible: true, dueAt };
}
async function selectStockBatch(input, { transport, now = () => (/* @__PURE__ */ new Date()).toISOString() } = {}) {
  let snapshots, started;
  try {
    check4(typeof transport === "function" && typeof now === "function", "invalid_options");
    started = instant(now());
    snapshots = await snapshotBatches(input);
  } catch (error) {
    throw safeError(error);
  }
  let pagesChecked = 0, revision = null;
  const states = /* @__PURE__ */ new Map(), checkedTimes = [];
  for (let offset = 0; offset < snapshots.length; offset += STOCK_SELECTION_LIMITS.pageSize) {
    const descriptors = validateStockDescriptors(snapshots.slice(offset, offset + STOCK_SELECTION_LIMITS.pageSize).map((item) => item.descriptor));
    const requestSha256 = await stockDescriptorsHash(descriptors);
    const body = Object.freeze({ kind: "publications", action: "stock_status", batches: descriptors });
    let raw;
    try {
      pagesChecked++;
      raw = await transport(body);
    } catch {
      return { schemaVersion: 1, status: "status_unavailable", reason: "transport_failed", pagesChecked };
    }
    let response, observed;
    try {
      const receivedAt = instant(now());
      check4(receivedAt >= started, "clock_moved_backwards");
      observed = statusResponse(raw, descriptors, requestSha256, receivedAt);
      if (observed.unavailable) return { schemaVersion: 1, status: "status_unavailable", reason: observed.unavailable, pagesChecked };
      response = observed.response;
    } catch {
      return { schemaVersion: 1, status: "attention_required", reason: "invalid_status_response", pagesChecked };
    }
    if (revision !== null && revision !== response.revision) return { schemaVersion: 1, status: "attention_required", reason: "revision_changed", pagesChecked };
    revision = response.revision;
    checkedTimes.push(observed.checkedAt);
    const problems = response.batches.filter((row) => ["partial", "conflict"].includes(row.state)).map((row) => ({ batchId: row.batchId, state: row.state }));
    if (problems.length) return { schemaVersion: 1, status: "attention_required", reason: "partial_or_conflicting_stock", pagesChecked, problems };
    response.batches.forEach((row) => states.set(row.batchId, row.state));
  }
  let at, checkedAt;
  try {
    checkedAt = now();
    at = instant(checkedAt);
    check4(at >= started && checkedTimes.every((value) => value <= at && at - value <= STOCK_SELECTION_LIMITS.maxStatusAgeMs), "status_expired_during_selection");
  } catch {
    return { schemaVersion: 1, status: "attention_required", reason: "status_expired_during_selection", pagesChecked };
  }
  const importedBatchIds = [], expiredAbsentBatches = [], candidates = [];
  for (const snapshot of snapshots) {
    if (states.get(snapshot.entry.batchId) === "imported") {
      importedBatchIds.push(snapshot.entry.batchId);
      continue;
    }
    if (states.get(snapshot.entry.batchId) !== "absent") return { schemaVersion: 1, status: "attention_required", reason: "missing_stock_state", pagesChecked };
    try {
      const eligibility = absentEligibility(snapshot.batch, at);
      if (eligibility.eligible) candidates.push({ ...snapshot, dueAt: eligibility.dueAt });
      else expiredAbsentBatches.push({ batchId: snapshot.entry.batchId, reason: eligibility.reason });
    } catch {
      return { schemaVersion: 1, status: "attention_required", reason: "invalid_absent_review", pagesChecked, batchId: snapshot.entry.batchId };
    }
  }
  const base = { schemaVersion: 1, checkedAt, revision, pagesChecked, importedBatchIds, expiredAbsentBatches };
  if (importedBatchIds.length === snapshots.length) return { ...base, status: "all_imported", selected: null };
  if (!candidates.length) return { ...base, status: "no_eligible_stock", selected: null };
  candidates.sort((a, b) => a.dueAt - b.dueAt || (a.entry.batchId < b.entry.batchId ? -1 : a.entry.batchId > b.entry.batchId ? 1 : 0));
  const chosen = candidates[0];
  return { ...base, status: "stock_selected", selected: { ...chosen.entry, batch: chosen.batch } };
}

// exploitation/cloud-publications/stock-control.mjs
var ORIGIN = "https://voyage-sans-detour-admin.cousinmathis31.chatgpt.site";
var SITE = "appgprj_6ab8ae0785988191a26f73b4a4e6c687";
var END = Date.parse("2027-09-14T21:59:59Z");
var fail = () => {
  throw Error("stock_control_not_confirmed");
};
function createStockTransport({ key, dispatcher, fetcher = (...args) => fetch(...args), now = Date.now } = {}) {
  if (!/^[A-Za-z0-9_-]{43}$/.test(key ?? "") || typeof dispatcher !== "string" || !dispatcher || dispatcher.length > 4096 || typeof fetcher !== "function" || typeof now !== "function") fail();
  let attempts = 0, lastSent = 0;
  const deadline = performance.now() + 15e4;
  return async function transport(payload) {
    const importing = payload?.action === "import_stock";
    if (payload?.kind !== "publications" || !["stock_status", "import_stock"].includes(payload.action) || Object.keys(payload).sort().join(",") !== (importing ? "action,batch,kind" : "action,batches,kind")) fail();
    const stamp = now();
    if (!Number.isSafeInteger(stamp) || stamp <= 0 || stamp > END || performance.now() >= deadline || attempts >= 10) fail();
    const body = JSON.stringify(payload);
    if (Buffer.byteLength(body) > (importing ? 133120 : 8192)) fail();
    const sent = String(Math.max(stamp, lastSent + 1));
    lastSent = Number(sent);
    attempts++;
    const nonce = randomUUID(), path = "/internal/tick";
    const digest = createHash2("sha256").update(body).digest("hex");
    const signature = createHmac("sha256", Buffer.from(key, "base64url")).update(["vsd-cloud-v1", SITE, ORIGIN, "POST", path, sent, nonce, digest].join("\n")).digest("hex");
    const abort = new AbortController();
    let timer;
    const timeout = Math.min(importing ? 3e4 : 1e4, Math.max(1, deadline - performance.now()));
    const requestDeadline = performance.now() + timeout;
    const request = async () => {
      const response = await fetcher(ORIGIN + path, {
        method: "POST",
        redirect: "error",
        signal: abort.signal,
        headers: {
          "Content-Type": "application/json",
          "OAI-Sites-Authorization": "Bearer " + dispatcher,
          "X-VSD-Sent-At": sent,
          "X-VSD-Nonce": nonce,
          "X-VSD-Signature": signature
        },
        body
      });
      if (abort.signal.aborted || performance.now() >= requestDeadline || response.status !== 200 || response.redirected || response.url !== ORIGIN + path || response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() !== "application/json" || !response.body) fail();
      const reader = response.body.getReader(), chunks = [];
      let size = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (abort.signal.aborted || performance.now() >= requestDeadline) fail();
          if (done) break;
          size += value.byteLength;
          if (size > 16384) fail();
          chunks.push(Buffer.from(value));
        }
        const parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, size)));
        if (performance.now() >= requestDeadline) fail();
        return parsed;
      } finally {
        reader.cancel().catch(() => {
        });
        reader.releaseLock();
      }
    };
    try {
      return await Promise.race([request(), new Promise((_, reject) => {
        timer = setTimeout(() => {
          abort.abort();
          reject(Error("stock_control_not_confirmed"));
        }, timeout);
      })]);
    } catch {
      fail();
    } finally {
      clearTimeout(timer);
      abort.abort();
    }
  };
}
async function runStockControl({ repositoryRoot, transport, now = () => (/* @__PURE__ */ new Date()).toISOString(), readOnly = false } = {}) {
  if (typeof readOnly !== "boolean" || Date.parse(now()) > END) fail();
  const snapshot = await loadStockIndex({ repositoryRoot });
  const selection = await selectStockBatch(snapshot, { transport, now });
  const common = {
    schemaVersion: 1,
    checkedAt: now(),
    selectionStatus: selection.status,
    pagesChecked: selection.pagesChecked,
    importedBatchIds: selection.importedBatchIds ?? [],
    expiredAbsentBatches: selection.expiredAbsentBatches ?? [],
    revision: selection.revision ?? null,
    readOnly,
    importAttempted: false
  };
  if (selection.status !== "stock_selected") return { ...common, status: selection.status, ...selection.reason ? { reason: selection.reason } : {} };
  const { batch, ...identity2 } = selection.selected;
  if (readOnly) return { ...common, status: "stock_available", selected: identity2 };
  let acknowledgement = "unconfirmed", importReason;
  try {
    const reply = await transport({ kind: "publications", action: "import_stock", batch });
    if (reply && reply.kind === "publications" && ["kind,status", "kind,reason,status"].includes(Object.keys(reply).sort().join(",")) && ["stock_imported", "stock_existing", "busy", "disabled", "refused"].includes(reply.status) && (reply.reason === undefined || /^[a-z_]{1,64}$/.test(reply.reason))) {
      acknowledgement = reply.status;
      importReason = reply.reason;
    }
  } catch {
  }
  const entry = snapshot.index.items.find((item) => item.path === identity2.path);
  const only = { index: { schemaVersion: 1, items: [entry] }, files: /* @__PURE__ */ new Map([[entry.path, snapshot.files.get(entry.path)]]) };
  const confirmation = await selectStockBatch(only, { transport, now });
  const confirmed = confirmation.status === "all_imported" && confirmation.importedBatchIds.length === 1 && confirmation.importedBatchIds[0] === identity2.batchId;
  return {
    ...common,
    status: confirmed ? "stock_confirmed" : "import_uncertain",
    selected: identity2,
    importAttempted: true,
    acknowledgement,
    confirmationStatus: confirmation.status,
    confirmationRevision: confirmation.revision ?? null,
    ...(importReason ? { importReason } : {})
  };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve2(process.argv[1])).href) {
  try {
    if (Date.now() > END) {
      console.log("Follow-up period ended; no request sent.");
      process.exit(0);
    }
    const commit = process.env.GITHUB_SHA;
    if (!/^[a-f0-9]{40}$/.test(commit ?? "") || process.env.GITHUB_REPOSITORY !== "MathCSN/voyagesansdetour" || process.env.GITHUB_REF !== "refs/heads/main" || !["true", "false"].includes(process.env.VSD_STOCK_READ_ONLY ?? "")) fail();
    const transport = createStockTransport({ key: process.env.VSD_CLOUD_KEY, dispatcher: process.env.VSD_SITES_DISPATCH_TOKEN });
    const report = await runStockControl({ repositoryRoot: await realpath2("."), transport, readOnly: process.env.VSD_STOCK_READ_ONLY === "true" });
    const evidence = { ...report, sourceCommit: commit, runId: process.env.GITHUB_RUN_ID ?? null };
    await writeFile("stock-control-result.json", JSON.stringify(evidence, null, 2) + "\n", { flag: "wx" });
    console.log("Cloud receipt: stock / " + report.status + ".");
    console.log(JSON.stringify(evidence));
    if (!["all_imported", "stock_confirmed", "stock_available"].includes(report.status)) process.exitCode = 1;
  } catch {
    console.error("Cloud stock not confirmed. No automatic import retry was made.");
    process.exitCode = 1;
  }
}
export {
  createStockTransport,
  runStockControl
};
