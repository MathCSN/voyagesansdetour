#!/usr/bin/env node

// exploitation/production-contenus/promotion-control.mjs
import { constants as constants4 } from "node:fs";
import { lstat as lstat4, mkdir as mkdir2, open as open4, realpath as realpath4, link as link2, rename as rename2, unlink as unlink2 } from "node:fs/promises";
import { createHash as createHash5, randomUUID as randomUUID2 } from "node:crypto";
import { resolve as resolve4, join as join4, dirname as dirname2, parse as parse4, relative as relative4, sep as sep4 } from "node:path";
import { pathToFileURL as pathToFileURL2 } from "node:url";

// exploitation/production-contenus/promotion-cli.mjs
import { constants as constants2 } from "node:fs";
import { lstat as lstat2, mkdir, open as open2, realpath as realpath2, rename, link, unlink } from "node:fs/promises";
import { createHash as createHash2, randomUUID } from "node:crypto";
import { resolve as resolve2, dirname, join as join2, parse as parse2, relative as relative2, sep as sep2, basename } from "node:path";
import { pathToFileURL } from "node:url";

// exploitation/production-contenus/promotion-bundle.mjs
import { constants } from "node:fs";
import { lstat, open, readdir, realpath } from "node:fs/promises";
import { createHash } from "node:crypto";
import { resolve, parse, join, relative, sep } from "node:path";

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
var encoder = new TextEncoder();
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
  const bytes2 = typeof value === "string" ? encoder.encode(value) : value;
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

// exploitation/production-contenus/promotion-bundle.mjs
var PUBLIC_NAMES = Object.freeze(["reel.mp4", "poster.jpg", "credits.txt", "dmsans-OFL.txt", "playfairdisplay-OFL.txt"]);
var ORIGIN = "https://voyagesansdetour.fr";
var REPOSITORY = "MathCSN/voyagesansdetour";
var HASH2 = /^[a-f0-9]{64}$/;
var COMMIT = /^[a-f0-9]{40}$/;
var ID = /^[a-z0-9][a-z0-9-]{0,95}$/;
var DAY = 864e5;
var STOP = Date.parse("2027-09-14T21:59:59Z");
var JSON_LIMIT = 512 * 1024;
var FILE_LIMIT = 5e7;
var TOTAL_LIMIT = 1e8;
var FORMAT_SOURCES = /* @__PURE__ */ new Set([
  "https://support.buffer.com/en-us/articles/sharing-videos-through-buffer-LOe2p2rnAI",
  "https://developers.buffer.com/types/InstagramPostMetadataInput.html",
  "https://developers.buffer.com/guides/posts-and-scheduling.html"
]);
var RENDER_NAMES = /* @__PURE__ */ new Set([
  ...PUBLIC_NAMES,
  "legende.txt",
  "scenario.json",
  "apercu.jpg",
  "encode.log",
  ...Array.from({ length: 8 }, (_, i) => `scene-${String(i + 1).padStart(2, "0")}.jpg`)
]);
var check2 = (ok, message) => {
  if (!ok) throw Error("Promotion refused: " + message);
};
var sha = (bytes2) => createHash("sha256").update(bytes2).digest("hex");
var plain = (v) => v !== null && typeof v === "object" && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
var exact = (v, keys) => plain(v) && Object.keys(v).length === keys.length && keys.every((k) => Object.hasOwn(v, k));
var json = (bytes2) => {
  check2(Buffer.isBuffer(bytes2) && bytes2.length <= JSON_LIMIT, "bounded JSON bytes required");
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes2));
};
var time = (value) => {
  check2(typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(value), "UTC timestamp required");
  const n = Date.parse(value);
  check2(Number.isFinite(n) && new Date(n).toISOString().slice(0, 19) === value.slice(0, 19), "invalid date");
  return n;
};
function stable(v) {
  if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
  if (plain(v)) return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}";
  return JSON.stringify(v);
}
function publicUrl(value) {
  check2(typeof value === "string" && value.length <= 1500, "public URL required");
  const u = new URL(value);
  check2(u.protocol === "https:" && !u.username && !u.password && !u.port && !u.search && !u.hash && u.href === value, "public URL cannot contain credentials or parameters");
  return u;
}
function musicSourceUrl(value) {
  check2(typeof value === "string" && value.length <= 1500, "music source URL");
  const u = new URL(value);
  if (!u.search) return publicUrl(value);
  check2(u.href === value && u.hostname === "incompetech.com" && u.pathname === "/music/royalty-free/index.html" && /^\?isrc=[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$/.test(u.search), "music query outside public ISRC allowlist");
  u.search = "";
  return publicUrl(u.href);
}
var mime = (name) => name.endsWith(".mp4") ? "video/mp4" : name.endsWith(".jpg") ? "image/jpeg" : "text/plain";
function relativePath(value) {
  check2(typeof value === "string" && value.length <= 250 && /^[A-Za-z0-9._/-]+$/.test(value) && value.split("/").every((part) => part && part !== "." && part !== ".."), "unsafe relative path");
  return value;
}
async function noLinkPath(path, kind) {
  const absolute = resolve(path), root = parse(absolute).root;
  let current = root;
  for (const component of relative(root, absolute).split(sep).filter(Boolean)) {
    current = join(current, component);
    const info = await lstat(current);
    check2(!info.isSymbolicLink(), "symbolic link");
    if (current !== absolute || kind === "directory") check2(info.isDirectory(), "directory required");
  }
  check2(await realpath(absolute) === absolute, "noncanonical root");
  return absolute;
}
async function readSafe(root, name, limit = JSON_LIMIT) {
  relativePath(name);
  const path = join(root, name);
  await noLinkPath(path, "file");
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const before = await handle.stat();
    check2(before.isFile() && before.size <= limit, "regular bounded file required");
    const bytes2 = await handle.readFile();
    const after = await handle.stat();
    check2(bytes2.length === before.size && after.size === before.size && after.mtimeMs === before.mtimeMs, "input changed while reading");
    return bytes2;
  } finally {
    await handle.close();
  }
}
async function loadPromotionInputs({ productionRoot, renderDirectory, independentReviewFile, cloudProofFile }) {
  const root = await noLinkPath(productionRoot, "directory");
  relativePath(renderDirectory);
  const render = await noLinkPath(join(root, renderDirectory), "directory");
  const receiptBytes = await readSafe(render, "receipt.json");
  const receipt = json(receiptBytes);
  check2(Array.isArray(receipt.files) && receipt.files.length <= 20, "receipt inventory");
  const files = /* @__PURE__ */ new Map();
  let total = 0;
  for (const entry of receipt.files) {
    check2(plain(entry) && RENDER_NAMES.has(entry.file) && !files.has(entry.file), "receipt filename");
    const bytes2 = await readSafe(render, entry.file, FILE_LIMIT);
    total += bytes2.length;
    check2(total <= TOTAL_LIMIT, "render too large");
    files.set(entry.file, bytes2);
  }
  const names2 = (await readdir(render)).sort();
  check2(stable(names2) === stable(["receipt.json", ...files.keys()].sort()), "unexpected render file");
  const catalogueBytes = await readSafe(root, "catalogue.json");
  const catalogue = json(catalogueBytes);
  check2(Array.isArray(catalogue.items), "catalogue items");
  const entries = catalogue.items.filter((item) => item.contentId === receipt.contentId);
  check2(entries.length === 1, "catalogue identity");
  check2(/^scenarios\/[a-z0-9][a-z0-9-]*\.json$/.test(entries[0].file) && independentReviewFile?.endsWith(".json") && cloudProofFile?.endsWith(".json"), "JSON source paths required");
  return {
    receiptBytes,
    files,
    catalogueBytes,
    sourceScenarioBytes: await readSafe(root, entries[0].file),
    independentReviewBytes: await readSafe(root, independentReviewFile),
    cloudProofBytes: await readSafe(root, cloudProofFile)
  };
}
function snapshotInputs(inputs) {
  const copy = {};
  for (const key of ["receiptBytes", "sourceScenarioBytes", "catalogueBytes", "independentReviewBytes", "cloudProofBytes"]) {
    check2(Buffer.isBuffer(inputs?.[key]) && inputs[key].length <= JSON_LIMIT, "bounded input required");
    copy[key] = Buffer.from(inputs[key]);
  }
  check2(inputs.files instanceof Map && inputs.files.size <= 20, "bounded file map required");
  copy.files = /* @__PURE__ */ new Map();
  let total = 0;
  for (const [name, bytes2] of inputs.files) {
    check2(RENDER_NAMES.has(name) && Buffer.isBuffer(bytes2) && bytes2.length <= FILE_LIMIT, "render file map");
    total += bytes2.length;
    check2(total <= TOTAL_LIMIT, "render too large");
    copy.files.set(name, Buffer.from(bytes2));
  }
  return copy;
}
function validate(inputs, now) {
  const at = time(now);
  check2(at <= STOP, "authorized period ended");
  const receipt = json(inputs.receiptBytes), scenario = json(inputs.files?.get("scenario.json"));
  const sourceScenario = json(inputs.sourceScenarioBytes), catalogue = json(inputs.catalogueBytes);
  const review = json(inputs.independentReviewBytes), cloud = json(inputs.cloudProofBytes);
  check2(receipt.schemaVersion === 1 && receipt.rendererContractVersion === 2 && receipt.status === "rendered_not_published", "contract-2 completed render required");
  const id = receipt.contentId;
  check2(typeof id === "string" && ID.test(id) && scenario.id === id && scenario.schemaVersion === 1, "render identity");
  check2(stable(scenario) === stable(sourceScenario), "scenario differs from approved catalogue source");
  check2(exact(catalogue, ["schemaVersion", "items"]) && catalogue.schemaVersion === 1 && Array.isArray(catalogue.items) && catalogue.items.length <= 104, "catalogue schema");
  const matches = catalogue.items.filter((item) => item?.contentId === id);
  check2(matches.length === 1 && exact(matches[0], ["contentId", "notBefore", "file", "sha256"]), "catalogue identity");
  relativePath(matches[0].file);
  check2(matches[0].sha256 === sha(inputs.sourceScenarioBytes) && time(matches[0].notBefore) <= time(receipt.createdAt), "catalogue hash or production window");
  check2(receipt.format === scenario.format && ["music_text", "silent_text"].includes(scenario.format) && receipt.presenter === "none" && scenario.presenter === "none" && receipt.voice === null && scenario.aiAssisted === true, "supported non-person format required");
  check2(HASH2.test(receipt.fingerprint) && HASH2.test(receipt.rendererSha256), "renderer provenance");
  check2(receipt.cost?.newPaidService === false && receipt.cost?.providerCalls === 0 && receipt.cost?.monetarySpendEur === 0, "free render required");
  check2(exact(receipt.publication, ["uploaded", "scheduled", "published", "readyForAutomaticImport"]) && Object.values(receipt.publication).every((v) => v === false), "render receipt is not publication evidence");
  const target = publicUrl(scenario.targetUrl);
  check2(target.origin === ORIGIN && /^\/portugal\/[a-z0-9-]+\/$/.test(target.pathname) && receipt.targetUrl === target.href, "guide target");
  check2(scenario.review?.status === "reviewed_for_render" && receipt.reviewValidUntil === scenario.review.validUntil && receipt.sourceCheckedOn === scenario.source?.checkedOn, "source review differs");
  const sourceDay = receipt.sourceCheckedOn;
  check2(typeof sourceDay === "string" && /^\d{4}-\d\d-\d\d$/.test(sourceDay) && (/* @__PURE__ */ new Date(sourceDay + "T00:00:00Z")).toISOString().slice(0, 10) === sourceDay, "source day");
  const sourceAt = Date.parse(sourceDay + "T00:00:00Z"), sourceExpiry = time(receipt.reviewValidUntil);
  check2(sourceAt <= time(scenario.review.checkedAt) && time(scenario.review.checkedAt) <= time(receipt.createdAt) && time(receipt.createdAt) <= time(receipt.renderFinishedAt) && time(receipt.renderFinishedAt) <= at, "render chronology");
  check2(at < sourceExpiry && sourceExpiry <= sourceAt + 31 * DAY && sourceExpiry <= STOP && at < sourceAt + 31 * DAY, "source review expired or stale");
  check2(Array.isArray(receipt.sourceUrls) && receipt.sourceUrls.length > 0 && receipt.sourceUrls.length <= 12, "source URLs");
  receipt.sourceUrls.forEach(publicUrl);
  const scenes = scenario.scenes;
  check2(Array.isArray(scenes) && scenes.length >= 4 && scenes.length <= 8, "scene inventory");
  const expectedNames = [...PUBLIC_NAMES, "legende.txt", "scenario.json", "apercu.jpg", "encode.log", ...scenes.map((_, i) => `scene-${String(i + 1).padStart(2, "0")}.jpg`)].sort();
  check2(inputs.files instanceof Map && stable([...inputs.files.keys()].sort()) === stable(expectedNames), "exact render allowlist required");
  check2(Array.isArray(receipt.files) && stable(receipt.files.map((f) => f.file).sort()) === stable(expectedNames), "receipt allowlist differs");
  let total = 0;
  for (const entry of receipt.files) {
    const bytes2 = inputs.files.get(entry.file);
    check2(exact(entry, ["file", "sha256", "bytes"]) && HASH2.test(entry.sha256) && Number.isSafeInteger(entry.bytes) && entry.bytes >= 0 && entry.bytes <= FILE_LIMIT && Buffer.isBuffer(bytes2) && bytes2.length === entry.bytes && sha(bytes2) === entry.sha256, "render bytes changed");
    check2(entry.file === "encode.log" || entry.bytes > 0, "empty render output");
    total += bytes2.length;
    check2(total <= TOTAL_LIMIT, "render too large");
  }
  const spec = receipt.video;
  check2(spec?.width === 1080 && spec.height === 1920 && spec.fps === 30 && spec.videoCodec === "h264" && spec.pixelFormat === "yuv420p" && spec.fullDecodePassed === true && Number.isFinite(spec.durationSeconds) && spec.durationSeconds >= 15 && spec.durationSeconds <= 45.2 && Number.isInteger(spec.videoBitrateBps) && spec.videoBitrateBps > 0 && spec.videoBitrateBps < 25e6, "video QA");
  if (scenario.format === "music_text") check2(spec.audioCodec === "aac" && spec.audioSampleRate === 48e3 && Number.isInteger(spec.audioBitrateBps) && spec.audioBitrateBps > 0 && spec.audioBitrateBps < 128e3 && Number.isFinite(spec.loudness?.integratedLufs) && spec.loudness.integratedLufs >= -22 && spec.loudness.integratedLufs <= -14 && Number.isFinite(spec.loudness?.truePeakDbfs) && spec.loudness.truePeakDbfs <= -1, "audio QA");
  else check2(spec.audioCodec === null && spec.audioSampleRate === null && spec.audioBitrateBps === null, "silent format audio");
  const reviewKeys = ["schemaVersion", "contentId", "contentAndFormatApproved", "publicMediaApproved", "publicationApproved", "reviewedAt", "validUntil", "receiptSha256", "mediaSha256", "captionSha256", "scenarioSha256", "cloudProofSha256", "checks", "sources", "formatCapability", "publication"];
  check2(exact(review, reviewKeys) && review.schemaVersion === 1 && review.contentId === id && review.contentAndFormatApproved === true && review.publicMediaApproved === true && review.publicationApproved === true, "explicit independent approvals required");
  check2(review.receiptSha256 === sha(inputs.receiptBytes) && review.mediaSha256 === sha(inputs.files.get("reel.mp4")) && review.captionSha256 === sha(inputs.files.get("legende.txt")) && review.scenarioSha256 === sha(inputs.files.get("scenario.json")) && review.cloudProofSha256 === sha(inputs.cloudProofBytes), "independent review fingerprints differ");
  const reviewed = time(review.reviewedAt), expiry = time(review.validUntil);
  check2(time(receipt.renderFinishedAt) <= reviewed && reviewed <= at && at < expiry && expiry <= sourceExpiry && expiry - reviewed <= 31 * DAY, "independent review expired or future");
  const checks = review.checks;
  check2(exact(checks, ["editorialApproved", "rightsApproved", "creditsPreserved", "disclosurePreserved", "formatRequirementsVerified", "requiresPaidCall"]) && checks.editorialApproved === true && checks.rightsApproved === true && checks.creditsPreserved === true && checks.disclosurePreserved === true && checks.formatRequirementsVerified === true && checks.requiresPaidCall === false, "independent review checks");
  const fresh = (e, keys) => {
    check2(exact(e, keys) && e.status === "verified" && time(e.observedAt) <= reviewed && time(e.observedAt) >= sourceAt && e.validUntil === review.validUntil, "explicit dated verification required");
  };
  fresh(review.sources, ["status", "observedAt", "validUntil"]);
  fresh(review.formatCapability, ["status", "observedAt", "validUntil", "automaticPublishing", "verificationMethod", "sourceUrls"]);
  check2(review.formatCapability.automaticPublishing === true && review.formatCapability.verificationMethod === "official_documentation" && Array.isArray(review.formatCapability.sourceUrls) && review.formatCapability.sourceUrls.length > 0 && review.formatCapability.sourceUrls.every((url) => FORMAT_SOURCES.has(url)), "format qualification");
  const intent = review.publication;
  check2(exact(intent, ["batchId", "dueAt", "title"]) && typeof intent.batchId === "string" && /^[a-z0-9][a-z0-9._-]{0,99}$/.test(intent.batchId) && typeof intent.title === "string" && intent.title.trim() === intent.title && intent.title.length > 0 && intent.title.length <= 150 && !/[\x00-\x1f\x7f]/.test(intent.title), "reviewed publication intent");
  check2(at < time(intent.dueAt) && time(intent.dueAt) < expiry, "past or expired planned slot");
  check2(cloud.schemaVersion === 1 && cloud.repository === REPOSITORY && cloud.run?.status === "completed" && cloud.run.conclusion === "success" && ["schedule", "workflow_dispatch"].includes(cloud.run.event) && cloud.run.head_branch === "main" && COMMIT.test(cloud.run.head_sha) && COMMIT.test(cloud.artifactCommit?.sha) && Number.isSafeInteger(cloud.run.id) && cloud.run.id > 0, "verified trusted cloud run required");
  check2(cloud.run.html_url === `https://github.com/${REPOSITORY}/actions/runs/${cloud.run.id}` && cloud.artifactPath === `.github/vsd-production/output/${id}/` && cloud.receiptSha256 === review.receiptSha256 && cloud.allFileHashesVerified === true && time(receipt.renderFinishedAt) <= time(cloud.verifiedAt) && time(cloud.verifiedAt) <= reviewed, "cloud evidence differs");
  if (cloud.cloudReceipt !== void 0) check2(stable(cloud.cloudReceipt) === stable(receipt), "cloud receipt differs");
  const caption = new TextDecoder("utf-8", { fatal: true }).decode(inputs.files.get("legende.txt"));
  check2(caption.length > 0 && caption.length <= 2200 && caption.includes(target.href) && caption.includes("Texte et montage assist\xE9s par IA.") && caption.includes("sans r\xE9cit de trajet v\xE9cu."), "caption or disclosure");
  const credits = new TextDecoder("utf-8", { fatal: true }).decode(inputs.files.get("credits.txt"));
  check2(credits.includes(caption), "public credits must retain the complete caption");
  for (const [font, name] of [["regular", "dmsans-OFL.txt"], ["bold", "dmsans-OFL.txt"], ["serif", "playfairdisplay-OFL.txt"]]) {
    check2(scenario.assets?.[font]?.license === "OFL-1.1" && scenario.assets[font].licenseFile?.sha256 === sha(inputs.files.get(name)), "font licence changed");
  }
  if (scenario.format === "music_text") {
    const music = scenario.assets?.music;
    check2(music?.license === "CC-BY-4.0" && music.commercialUseAllowed === true && music.licenseUrl === "https://creativecommons.org/licenses/by/4.0/", "music rights");
    musicSourceUrl(music.sourceUrl);
    check2([music.title, music.author, music.sourceUrl, music.licenseUrl].every((value) => typeof value === "string" && value.length > 0 && caption.includes(value)), "music credits omitted");
  }
  return { id, receipt, review, cloud, caption, target: target.href };
}
async function buildPromotionBundle(inputs, { now = (/* @__PURE__ */ new Date()).toISOString() } = {}) {
  inputs = snapshotInputs(inputs);
  const { id, receipt, review, cloud, caption, target } = validate(inputs, now);
  const mediaBase = `${ORIGIN}/social-media/production/${id}/`, contentId = `vsd-production:instagram:${id}:cloud-v2`;
  const publicFiles = PUBLIC_NAMES.map((name) => {
    const bytes2 = Buffer.from(inputs.files.get(name));
    return { path: `social-media/production/${id}/${name}`, name, sha256: sha(bytes2), size: bytes2.length, mimeType: mime(name), bytes: bytes2 };
  });
  const entry = { contentId: id, approved: review.publicMediaApproved, files: publicFiles.map((f) => ({ name: f.name, sha256: f.sha256, bytes: f.size })) };
  const asset = { url: mediaBase + "reel.mp4", mimeType: "video/mp4", sha256: review.mediaSha256 };
  const payload = { schemaVersion: 1, channel: "instagram", kind: "reel", text: caption, aiGenerated: false, assets: [asset] };
  const pending = { status: "pending_public_delivery", observedAt: null, validUntil: review.validUntil };
  const batch = { schemaVersion: 1, batchId: review.publication.batchId, items: [{
    contentId,
    deduplicationKey: contentId,
    title: review.publication.title,
    dueAt: review.publication.dueAt,
    payload,
    review: {
      schemaVersion: 1,
      contentId,
      approved: false,
      reviewedAt: review.reviewedAt,
      validUntil: review.validUntil,
      payloadRevision: await bufferPayloadRevision(payload),
      checks: { ...review.checks, sources: structuredClone(review.sources), syntheticPerson: false, providerSyntheticSettingVerified: false },
      media: { ...asset, required: true, ...pending },
      destination: { url: target, ...pending },
      monetization: { containsAffiliateLinks: false, partnerApproved: false, linksVerified: false, disclosurePreserved: false },
      formatCapability: structuredClone(review.formatCapability),
      evidence: {
        status: "candidate_requires_public_hash_check",
        rendererContractVersion: 2,
        finalMediaProducedInCloud: true,
        sourceCloudRun: cloud.run.html_url,
        sourceCloudArtifactCommit: cloud.artifactCommit.sha,
        receiptSha256: review.receiptSha256,
        independentReviewSha256: sha(inputs.independentReviewBytes),
        mediaSha256: review.mediaSha256,
        captionSha256: review.captionSha256,
        sourceCheckedOn: receipt.sourceCheckedOn,
        sourceUrls: [...receipt.sourceUrls],
        audioBitrateBps: receipt.video.audioBitrateBps,
        note: "An intended slot is not a Buffer reservation. Existing scheduler gates remain mandatory."
      }
    }
  }] };
  check2(Buffer.byteLength(JSON.stringify(batch)) <= 128 * 1024, "batch too large");
  return {
    schemaVersion: 1,
    status: "prepared_not_deployed_or_imported",
    publicFiles,
    publicEntry: entry,
    candidateBatch: batch,
    provenance: { receiptSha256: review.receiptSha256, independentReviewSha256: sha(inputs.independentReviewBytes), cloudProofSha256: sha(inputs.cloudProofBytes) }
  };
}
async function finalizePromotionBundle(inputs, publicProofBytes, { now = (/* @__PURE__ */ new Date()).toISOString() } = {}) {
  inputs = snapshotInputs(inputs);
  const bundle = await buildPromotionBundle(inputs, { now }), proof = json(publicProofBytes), at = time(now);
  check2(proof.schemaVersion === 1 && proof.source === "bounded_live_http_get" && time(proof.observedAt) <= at && at - time(proof.observedAt) <= 36e5, "fresh public HTTP proof required");
  const batch = structuredClone(bundle.candidateBatch), review = batch.items[0].review;
  check2(time(proof.observedAt) >= time(review.reviewedAt) && Array.isArray(proof.files) && proof.files.length === PUBLIC_NAMES.length, "public proof chronology or inventory");
  for (const file of bundle.publicFiles) {
    const url = ORIGIN + "/" + file.path, observations = proof.files.filter((f2) => f2.url === url);
    check2(observations.length === 1, "public proof duplicate or missing file");
    const f = observations[0];
    check2(f.finalUrl === url && f.httpStatus === 200 && f.mimeType === file.mimeType && f.sha256 === file.sha256 && f.bytes === file.size, "public bytes or MIME differ");
  }
  const target = review.destination.url, d = proof.destination;
  check2(d?.url === target && d.finalUrl === target && d.canonicalUrl === target && d.httpStatus === 200 && HASH2.test(d.sha256), "guide canonical proof");
  review.approved = json(inputs.independentReviewBytes).publicationApproved;
  review.media.status = review.destination.status = "verified";
  review.media.observedAt = review.destination.observedAt = proof.observedAt;
  review.evidence.status = "reviewed_public_bytes_verified_not_imported";
  review.evidence.publicProofSha256 = sha(publicProofBytes);
  return { ...bundle, status: "reviewed_not_imported", reviewedBatch: batch };
}
function mergePublicMediaCatalogue(catalogue, entry) {
  const validEntry = (item) => {
    check2(exact(item, ["contentId", "approved", "files"]) && /^[a-z0-9][a-z0-9-]{0,99}$/.test(item.contentId) && item.approved === true && Array.isArray(item.files) && item.files.length >= 3 && item.files.length <= 5 && item.files.every((f) => PUBLIC_NAMES.includes(f.name)) && new Set(item.files.map((f) => f.name)).size === item.files.length && ["reel.mp4", "poster.jpg", "credits.txt"].every((name) => item.files.some((f) => f.name === name)), "public catalogue entry");
    for (const f of item.files) check2(exact(f, ["name", "sha256", "bytes"]) && HASH2.test(f.sha256) && Number.isSafeInteger(f.bytes) && f.bytes > 0 && f.bytes <= FILE_LIMIT, "public catalogue file");
  };
  check2(exact(catalogue, ["schemaVersion", "items"]) && catalogue.schemaVersion === 1 && Array.isArray(catalogue.items) && catalogue.items.length <= 104, "public catalogue schema");
  validEntry(entry);
  catalogue.items.forEach(validEntry);
  check2(new Set(catalogue.items.map((i) => i.contentId)).size === catalogue.items.length, "duplicate public identity");
  const previous = catalogue.items.find((i) => i.contentId === entry.contentId);
  if (previous) check2(stable(previous) === stable(entry), "public identity is immutable");
  else check2(catalogue.items.length < 104, "public inventory full");
  return structuredClone(previous ? catalogue : { schemaVersion: 1, items: [...catalogue.items, entry] });
}

// exploitation/production-contenus/promotion-cli.mjs
var sha2 = (bytes2) => createHash2("sha256").update(bytes2).digest("hex");
var encode = (value) => Buffer.from(JSON.stringify(value, null, 2) + "\n");
var LIMIT = 512 * 1024;
var Refused = class extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
};
var check3 = (ok, code) => {
  if (!ok) throw new Refused(code);
};
var within = (root, path) => path === root || path.startsWith(root + sep2);
var safeRelative = (value) => typeof value === "string" && value.length <= 250 && /^[A-Za-z0-9._/-]+$/.test(value) && value.split("/").every((p) => p && p !== "." && p !== "..");
async function inspectPath(path, { createDirectories = false, directory = false } = {}) {
  const absolute = resolve2(path), base = parse2(absolute).root;
  let cursor = base;
  for (const component of relative2(base, absolute).split(sep2).filter(Boolean)) {
    cursor = join2(cursor, component);
    let info;
    try {
      info = await lstat2(cursor);
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      if (!createDirectories) return null;
      try {
        await mkdir(cursor, { mode: 493 });
      } catch (e) {
        if (e.code !== "EEXIST") throw e;
      }
      info = await lstat2(cursor);
    }
    check3(!info.isSymbolicLink(), "symlink_refused");
    if (cursor !== absolute || directory) check3(info.isDirectory(), "directory_required");
  }
  check3(await realpath2(absolute) === absolute, "noncanonical_path");
  return absolute;
}
async function readBounded(path, max = LIMIT) {
  check3(await inspectPath(path), "required_file_missing");
  const file = await open2(path, constants2.O_RDONLY | constants2.O_NOFOLLOW);
  try {
    const before = await file.stat();
    check3(before.isFile() && before.size <= max, "invalid_file");
    const bytes2 = await file.readFile(), after = await file.stat();
    check3(bytes2.length === before.size && after.size === before.size && after.mtimeMs === before.mtimeMs, "file_changed_during_read");
    return bytes2;
  } finally {
    await file.close();
  }
}
async function existingMatches(path, bytes2) {
  const existing = await inspectPath(path);
  if (!existing) return false;
  check3((await readBounded(existing, bytes2.length)).equals(bytes2), "immutable_file_conflict");
  return true;
}
async function syncDirectory(path) {
  const folder = await open2(path, constants2.O_RDONLY);
  try {
    await folder.sync();
  } finally {
    await folder.close();
  }
}
async function temporaryBytes(path, bytes2) {
  const temporary = join2(dirname(path), `.vsd-promotion-${randomUUID()}.tmp`);
  const file = await open2(temporary, constants2.O_WRONLY | constants2.O_CREAT | constants2.O_EXCL | constants2.O_NOFOLLOW, 384);
  try {
    await file.writeFile(bytes2);
    await file.sync();
  } catch (error) {
    await unlink(temporary).catch(() => {
    });
    throw error;
  } finally {
    await file.close();
  }
  return temporary;
}
async function immutableWrite(path, bytes2) {
  if (await existingMatches(path, bytes2)) return false;
  await inspectPath(dirname(path), { createDirectories: true, directory: true });
  const temporary = await temporaryBytes(path, bytes2);
  try {
    try {
      await link(temporary, path);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      check3(await existingMatches(path, bytes2), "immutable_target_disappeared");
      return false;
    }
    await syncDirectory(dirname(path));
    return true;
  } finally {
    await unlink(temporary);
  }
}
async function replaceCatalogue(path, before, after) {
  if (before.equals(after)) return false;
  check3((await readBounded(path)).equals(before), "catalogue_changed_during_stage");
  const temporary = await temporaryBytes(path, after);
  try {
    check3((await readBounded(path)).equals(before), "catalogue_changed_during_stage");
    await rename(temporary, path);
    await syncDirectory(dirname(path));
    return true;
  } finally {
    await unlink(temporary).catch((error) => {
      if (error.code !== "ENOENT") throw error;
    });
  }
}
async function locked(siteRoot, operation) {
  const path = join2(siteRoot, ".vsd-promotion.lock");
  let handle;
  try {
    handle = await open2(path, constants2.O_WRONLY | constants2.O_CREAT | constants2.O_EXCL | constants2.O_NOFOLLOW, 384);
  } catch (error) {
    if (["EEXIST", "ELOOP"].includes(error.code)) throw new Refused("site_locked");
    throw error;
  }
  const owner = await handle.stat();
  try {
    await handle.writeFile(encode({ schemaVersion: 1, pid: process.pid, nonce: randomUUID() }));
    await handle.sync();
    return await operation();
  } finally {
    await handle.close();
    const current = await lstat2(path).catch((error) => {
      if (error.code === "ENOENT") return null;
      throw error;
    });
    check3(current && !current.isSymbolicLink() && current.dev === owner.dev && current.ino === owner.ino, "lock_owner_changed");
    await unlink(path);
  }
}
async function context(options2) {
  check3(options2 && typeof options2.siteRoot === "string" && typeof options2.outputRoot === "string", "roots_required");
  const siteRoot = resolve2(options2.siteRoot), outputRoot = resolve2(options2.outputRoot);
  check3(!within(siteRoot, outputRoot), "private_output_must_be_outside_site");
  check3(await inspectPath(siteRoot, { directory: true }), "site_root_missing");
  await inspectPath(outputRoot, { createDirectories: true, directory: true });
  const inputs = await loadPromotionInputs({
    productionRoot: options2.productionRoot,
    renderDirectory: options2.renderDirectory,
    independentReviewFile: options2.independentReviewFile,
    cloudProofFile: options2.cloudProofFile
  });
  return { siteRoot, outputRoot, inputs };
}
function pathsFor(context2, bundle) {
  const batchId = bundle.candidateBatch.batchId;
  check3(/^[a-z0-9][a-z0-9._-]{0,99}$/.test(batchId), "batch_identity");
  const paths = {
    catalogue: join2(context2.siteRoot, "public-media.json"),
    candidate: join2(context2.outputRoot, "candidates", batchId + ".json"),
    stageReceipt: join2(context2.outputRoot, "staged", batchId + ".json"),
    reviewed: join2(context2.outputRoot, "reviewed", batchId + ".json")
  };
  for (const p of [paths.candidate, paths.stageReceipt, paths.reviewed]) check3(!within(context2.siteRoot, p), "private_output_must_be_outside_site");
  return paths;
}
function receiptFor(bundle) {
  return {
    schemaVersion: 1,
    status: "staged_not_deployed_or_imported",
    batchId: bundle.candidateBatch.batchId,
    contentId: bundle.publicEntry.contentId,
    candidateSha256: sha2(encode(bundle.candidateBatch)),
    publicEntrySha256: sha2(encode(bundle.publicEntry)),
    files: bundle.publicFiles.map((f) => ({ path: f.path, sha256: f.sha256, bytes: f.size }))
  };
}
function fileTarget(context2, bundle, file) {
  check3(safeRelative(file.path) && file.path === `social-media/production/${bundle.publicEntry.contentId}/${file.name}`, "public_path_escape");
  const path = join2(context2.siteRoot, file.path);
  check3(within(context2.siteRoot, path), "public_path_escape");
  return path;
}
async function stagePromotion(options2, { now = (/* @__PURE__ */ new Date()).toISOString(), onPhase = async () => {
} } = {}) {
  const ctx = await context(options2), bundle = await buildPromotionBundle(ctx.inputs, { now });
  const paths = pathsFor(ctx, bundle), candidate = encode(bundle.candidateBatch), stageReceipt = encode(receiptFor(bundle));
  return locked(ctx.siteRoot, async () => {
    const before = await readBounded(paths.catalogue), existing = JSON.parse(before);
    const proposed = mergePublicMediaCatalogue(existing, bundle.publicEntry);
    const after = proposed.items.length === existing.items.length ? before : encode(proposed);
    await existingMatches(paths.candidate, candidate);
    await existingMatches(paths.stageReceipt, stageReceipt);
    for (const f of bundle.publicFiles) await existingMatches(fileTarget(ctx, bundle, f), f.bytes);
    let changed = false;
    for (const f of bundle.publicFiles) {
      changed = await immutableWrite(fileTarget(ctx, bundle, f), f.bytes) || changed;
      await onPhase("public_file_written", { name: f.name });
    }
    await onPhase("public_files_ready");
    changed = await immutableWrite(paths.candidate, candidate) || changed;
    await onPhase("candidate_ready");
    for (const f of bundle.publicFiles) check3(await existingMatches(fileTarget(ctx, bundle, f), f.bytes), "public_file_missing_before_catalogue");
    check3(await existingMatches(paths.candidate, candidate), "candidate_missing_before_catalogue");
    changed = await replaceCatalogue(paths.catalogue, before, after) || changed;
    await onPhase("catalogue_ready");
    changed = await immutableWrite(paths.stageReceipt, stageReceipt) || changed;
    return {
      status: changed ? "staged_not_deployed_or_imported" : "already_staged",
      candidatePath: paths.candidate,
      candidateSha256: sha2(candidate),
      stageReceiptPath: paths.stageReceipt,
      publicCataloguePath: paths.catalogue,
      publicEntrySha256: sha2(encode(bundle.publicEntry))
    };
  });
}
async function finalizePromotion(options2, { now = (/* @__PURE__ */ new Date()).toISOString() } = {}) {
  const ctx = await context(options2);
  check3(safeRelative(options2.publicProofFile) && options2.publicProofFile.endsWith(".json"), "public_proof_relative_json_required");
  const proofRoot = resolve2(options2.productionRoot), proofPath = join2(proofRoot, options2.publicProofFile);
  check3(within(proofRoot, proofPath), "public_proof_path_escape");
  const proof = await readBounded(proofPath);
  const bundle = await finalizePromotionBundle(ctx.inputs, proof, { now }), paths = pathsFor(ctx, bundle);
  return locked(ctx.siteRoot, async () => {
    check3(await existingMatches(paths.candidate, encode(bundle.candidateBatch)), "candidate_stage_required");
    check3(await existingMatches(paths.stageReceipt, encode(receiptFor(bundle))), "stage_receipt_required");
    for (const f of bundle.publicFiles) check3(await existingMatches(fileTarget(ctx, bundle, f), f.bytes), "staged_public_file_missing");
    const catalogue = JSON.parse(await readBounded(paths.catalogue));
    check3(mergePublicMediaCatalogue(catalogue, bundle.publicEntry).items.length === catalogue.items.length, "staged_catalogue_entry_missing");
    const bytes2 = encode(bundle.reviewedBatch), changed = await immutableWrite(paths.reviewed, bytes2);
    return { status: changed ? "reviewed_not_imported" : "already_finalized", reviewedBatchPath: paths.reviewed, reviewedBatchSha256: sha2(bytes2) };
  });
}
function parseArguments(argv) {
  const [mode, ...flags] = argv;
  check3(["stage", "finalize"].includes(mode), "stage_or_finalize_required");
  const keys = /* @__PURE__ */ new Map([
    ["--production-root", "productionRoot"],
    ["--render-dir", "renderDirectory"],
    ["--review", "independentReviewFile"],
    ["--cloud-proof", "cloudProofFile"],
    ["--site-root", "siteRoot"],
    ["--output-root", "outputRoot"],
    ["--public-proof", "publicProofFile"]
  ]);
  const options2 = {};
  check3(flags.length % 2 === 0, "flag_value_required");
  for (let i = 0; i < flags.length; i += 2) {
    const key = keys.get(flags[i]), value = flags[i + 1];
    check3(key && !Object.hasOwn(options2, key) && typeof value === "string" && value.trim() && !value.startsWith("--"), "invalid_or_duplicate_flag");
    options2[key] = value;
  }
  for (const key of ["productionRoot", "renderDirectory", "independentReviewFile", "cloudProofFile", "siteRoot", "outputRoot"]) check3(options2[key], "missing_required_flag");
  check3(mode === "finalize" ? options2.publicProofFile : !options2.publicProofFile, "public_proof_mode_mismatch");
  return { mode, options: options2 };
}
if (process.argv[1] && basename(process.argv[1]) === "promotion-cli.mjs" && import.meta.url === pathToFileURL(resolve2(process.argv[1])).href) {
  try {
    const { mode, options: options2 } = parseArguments(process.argv.slice(2));
    const result = await (mode === "stage" ? stagePromotion(options2) : finalizePromotion(options2));
    console.log(JSON.stringify(result));
  } catch (error) {
    console.error(JSON.stringify({ status: "refused", reason: error instanceof Refused ? error.code : "input_or_local_operation_failed" }));
    process.exitCode = 1;
  }
}

// exploitation/production-contenus/public-proof.mjs
import { createHash as createHash3 } from "node:crypto";
import { performance } from "node:perf_hooks";
var ORIGIN2 = "https://voyagesansdetour.fr";
var HASH3 = /^[a-f0-9]{64}$/;
var ID2 = "[a-z0-9][a-z0-9-]{0,95}";
var FILE_LIMIT2 = 5e7;
var TOTAL_LIMIT2 = 1e8;
var GUIDE_LIMIT = 1024 * 1024;
var MIME = Object.freeze({
  "reel.mp4": "video/mp4",
  "poster.jpg": "image/jpeg",
  "credits.txt": "text/plain",
  "dmsans-OFL.txt": "text/plain",
  "playfairdisplay-OFL.txt": "text/plain"
});
var Refused2 = class extends Error {
  constructor(code) {
    super("Public verification refused: " + code);
    this.name = "PublicProofError";
  }
};
var requireThat = (value, code) => {
  if (!value) throw new Refused2(code);
};
var plain2 = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
var failSafe = (error) => error instanceof Refused2 ? error : new Refused2("request_failed");
var silently = (callback) => {
  try {
    Promise.resolve(callback()).catch(() => {
    });
  } catch {
  }
};
function jobsFor(bundle, expectedGuideSha256) {
  requireThat(plain2(bundle) && bundle.schemaVersion === 1 && bundle.status === "prepared_not_deployed_or_imported" && Array.isArray(bundle.publicFiles) && bundle.publicFiles.length === PUBLIC_NAMES.length && typeof expectedGuideSha256 === "string" && HASH3.test(expectedGuideSha256), "invalid_bundle");
  const items = bundle.candidateBatch?.items;
  requireThat(Array.isArray(items) && items.length === 1 && items[0]?.review?.approved === false, "invalid_candidate");
  const target = items[0].review.destination?.url;
  requireThat(typeof target === "string" && /^https:\/\/voyagesansdetour\.fr\/portugal\/[a-z0-9][a-z0-9-]*\/$/.test(target) && target.length <= 250, "invalid_guide");
  let identity2, total = 0;
  const found = /* @__PURE__ */ new Map();
  for (const file of bundle.publicFiles) {
    requireThat(plain2(file) && PUBLIC_NAMES.includes(file.name) && !found.has(file.name) && typeof file.path === "string" && typeof file.sha256 === "string" && HASH3.test(file.sha256) && Number.isSafeInteger(file.size) && file.size > 0 && file.size <= FILE_LIMIT2 && file.mimeType === MIME[file.name], "invalid_file");
    const match = new RegExp("^social-media/production/(" + ID2 + ")/([^/]+)$").exec(file.path);
    requireThat(match && match[2] === file.name && (!identity2 || identity2 === match[1]), "invalid_file_path");
    identity2 = match[1];
    total += file.size;
    requireThat(total <= TOTAL_LIMIT2, "inventory_too_large");
    found.set(file.name, { url: ORIGIN2 + "/" + file.path, mimeType: file.mimeType, size: file.size, sha256: file.sha256, guide: false });
  }
  requireThat(PUBLIC_NAMES.every((name) => found.has(name)), "invalid_inventory");
  return [...PUBLIC_NAMES.map((name) => found.get(name)), {
    url: target,
    mimeType: "text/html",
    size: null,
    sha256: expectedGuideSha256,
    guide: true
  }];
}
function canonicalFromHtml(html) {
  let cursor = 0, inHead = false, sawHtml = false, sawHead = false, sawDoctype = false, closedHead = false;
  const canonicals = [];
  const token = /<\/?([A-Za-z][A-Za-z0-9:-]*)((?:[^<>"']|"[^"]*"|'[^']*')*)>/y;
  while (cursor < html.length) {
    const start = html.indexOf("<", cursor);
    if (start < 0) break;
    requireThat(/^[\t\n\f\r ]*$/.test(html.slice(cursor, start)), "invalid_guide_html");
    if (html.startsWith("<!--", start)) {
      const end = html.indexOf("-->", start + 4);
      requireThat(end >= 0, "invalid_guide_html");
      cursor = end + 3;
      continue;
    }
    if (/^<!doctype\s/i.test(html.slice(start, start + 12))) {
      const end = html.indexOf(">", start + 2);
      requireThat(end >= 0 && !sawDoctype && !sawHtml && !sawHead && /^<!doctype[\t\n\f\r ]+html[\t\n\f\r ]*>$/i.test(html.slice(start, end + 1)), "invalid_guide_html");
      sawDoctype = true;
      cursor = end + 1;
      continue;
    }
    token.lastIndex = start;
    const match = token.exec(html);
    requireThat(match && /^(?:[\t\n\f\r /]|$)/.test(match[2]), "invalid_guide_html");
    cursor = token.lastIndex;
    const name = match[1].toLowerCase(), closing = html[start + 1] === "/";
    if (!inHead) {
      if (name === "html" && !closing && !sawHtml && !sawHead) {
        sawHtml = true;
        continue;
      }
      requireThat(name === "head" && !closing && !sawHead, "invalid_guide_html");
      sawHead = inHead = true;
      continue;
    }
    if (name === "head") {
      requireThat(closing, "invalid_guide_html");
      inHead = false;
      closedHead = true;
      break;
    }
    requireThat(!closing && ["base", "link", "meta", "script", "style", "title"].includes(name), "invalid_guide_html");
    if (["script", "style", "title"].includes(name)) {
      const close = new RegExp("</" + name + "[\\t\\n\\f\\r ]*>", "ig");
      close.lastIndex = cursor;
      const end = close.exec(html);
      requireThat(end, "invalid_guide_html");
      cursor = close.lastIndex;
      continue;
    }
    if (name === "link") {
      const attributes = /* @__PURE__ */ new Map();
      let rest = match[2];
      while (!/^[\t\n\f\r ]*\/?[\t\n\f\r ]*$/.test(rest)) {
        const attr = /^[\t\n\f\r ]+([A-Za-z_:][A-Za-z0-9_.:-]*)(?:[\t\n\f\r ]*=[\t\n\f\r ]*(?:"([^"]*)"|'([^']*)'|([^\t\n\f\r "'=<>`]+)))?/.exec(rest);
        requireThat(attr, "invalid_guide_html");
        const key = attr[1].toLowerCase();
        requireThat(!attributes.has(key), "invalid_guide_html");
        attributes.set(key, attr[2] ?? attr[3] ?? attr[4] ?? "");
        rest = rest.slice(attr[0].length);
      }
      if ((attributes.get("rel") || "").toLowerCase().split(/[\t\n\f\r ]+/).includes("canonical")) canonicals.push(attributes.get("href"));
    }
  }
  requireThat(closedHead && canonicals.length === 1 && typeof canonicals[0] === "string", "invalid_guide_canonical");
  return canonicals[0];
}
async function collectPublicProof(bundle, expectedGuideSha256, {
  fetcher = (url, options2) => globalThis.fetch(url, options2),
  now = () => (/* @__PURE__ */ new Date()).toISOString(),
  timeoutMs = 15e3
} = {}) {
  let jobs;
  try {
    requireThat(typeof fetcher === "function" && typeof now === "function" && Number.isSafeInteger(timeoutMs) && timeoutMs > 0 && timeoutMs <= 15e3, "invalid_options");
    jobs = jobsFor(bundle, expectedGuideSha256);
  } catch (error) {
    throw failSafe(error);
  }
  const abort = new AbortController(), readers = /* @__PURE__ */ new Set();
  const deadlineAt = performance.now() + timeoutMs;
  let stopped = false, timer, next = 0;
  const stop = () => {
    stopped = true;
    abort.abort();
    for (const reader of readers) silently(() => reader.cancel());
  };
  const checkDeadline = () => {
    if (stopped || performance.now() >= deadlineAt) {
      stop();
      throw new Refused2("deadline_exceeded");
    }
  };
  async function get(job) {
    let reader, response;
    try {
      checkDeadline();
      response = await fetcher(job.url, {
        method: "GET",
        redirect: "error",
        credentials: "omit",
        referrerPolicy: "no-referrer",
        cache: "no-store",
        signal: abort.signal,
        headers: { Accept: job.mimeType, "Accept-Encoding": "identity", "Cache-Control": "no-store" }
      });
      checkDeadline();
      requireThat(response && response.status === 200 && response.redirected === false && response.url === job.url, "unexpected_response");
      const type = response.headers.get("content-type");
      requireThat(typeof type === "string" && type.length <= 200 && !/[\x00-\x1f\x7f]/.test(type) && type.split(";")[0].trim().toLowerCase() === job.mimeType, "mime_mismatch");
      const limit = job.guide ? GUIDE_LIMIT : job.size;
      const length = response.headers.get("content-length");
      if (length !== null && !response.headers.get("content-encoding")) {
        requireThat(/^\d{1,10}$/.test(length) && Number(length) <= limit && (job.guide || Number(length) === job.size), "size_mismatch");
      }
      requireThat(response.body && typeof response.body.getReader === "function", "missing_body");
      reader = response.body.getReader();
      readers.add(reader);
      const digest = createHash3("sha256"), chunks = job.guide ? [] : null;
      let size = 0;
      while (true) {
        checkDeadline();
        const part = await reader.read();
        checkDeadline();
        if (part.done) break;
        requireThat(part.value instanceof Uint8Array, "invalid_body");
        size += part.value.byteLength;
        requireThat(size <= limit, "body_too_large");
        digest.update(part.value);
        if (chunks) chunks.push(Buffer.from(part.value));
      }
      requireThat(size > 0 && (job.guide || size === job.size), "size_mismatch");
      const sha256 = digest.digest("hex");
      requireThat(sha256 === job.sha256, "hash_mismatch");
      checkDeadline();
      if (job.guide) {
        const html = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks, size));
        requireThat(canonicalFromHtml(html) === job.url, "canonical_mismatch");
        checkDeadline();
        return { url: job.url, finalUrl: job.url, canonicalUrl: job.url, httpStatus: 200, sha256 };
      }
      return { url: job.url, finalUrl: job.url, httpStatus: 200, mimeType: job.mimeType, bytes: size, sha256 };
    } catch (error) {
      if (reader) silently(() => reader.cancel());
      else silently(() => response?.body?.cancel());
      throw failSafe(error);
    } finally {
      if (reader) {
        readers.delete(reader);
        silently(() => reader.releaseLock());
      }
    }
  }
  const observations = new Array(jobs.length);
  async function worker() {
    while (!stopped && next < jobs.length) {
      const index = next++;
      try {
        observations[index] = await get(jobs[index]);
      } catch (error) {
        stop();
        throw error;
      }
    }
  }
  try {
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        stop();
        reject(new Refused2("deadline_exceeded"));
      }, timeoutMs);
    });
    await Promise.race([Promise.all([worker(), worker()]), deadline]);
    checkDeadline();
    requireThat(!stopped && observations.every(Boolean), "incomplete_observation");
    const observedAt = now();
    requireThat(typeof observedAt === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(observedAt) && new Date(observedAt).toISOString() === observedAt, "invalid_clock");
    checkDeadline();
    return { schemaVersion: 1, source: "bounded_live_http_get", observedAt, files: observations.slice(0, 5), destination: observations[5] };
  } catch (error) {
    throw failSafe(error);
  } finally {
    clearTimeout(timer);
    stop();
  }
}

// exploitation/cloud-publications/stock-selection.mjs
import { constants as constants3 } from "node:fs";
import { lstat as lstat3, open as open3, realpath as realpath3 } from "node:fs/promises";
import { createHash as createHash4 } from "node:crypto";
import { join as join3, parse as parse3, relative as relative3, resolve as resolve3, sep as sep3 } from "node:path";

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
var encoder2 = new TextEncoder();

// exploitation/cloud-publications/payload-store.mjs
var REVIEWED_PAYLOAD_LIMITS = Object.freeze({
  maxRefLength: 256,
  maxPayloadBytes: 64 * 1024,
  maxPayloads: 1024
});
var encoder3 = new TextEncoder();

// exploitation/cloud-publications/publication-extension.mjs
var PUBLICATION_EXTENSION_LIMITS = Object.freeze({ maxItems: 4, maxBatchBytes: 128 * 1024 });
var check4 = (ok, code) => {
  if (!ok) throw new GuardError(code);
};
var encoder4 = new TextEncoder();
function stableJson(value, depth = 0, budget = { nodes: 0 }) {
  check4(depth <= 24 && ++budget.nodes <= 2e4, "extension_batch_too_complex");
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    check4(value.length <= 65536, "extension_batch_too_large");
    return value;
  }
  if (typeof value === "number") {
    check4(Number.isFinite(value), "extension_batch_invalid");
    return value;
  }
  check4(typeof value === "object" && (Array.isArray(value) || Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null), "extension_batch_invalid");
  if (Array.isArray(value)) return value.map((item) => stableJson(item, depth + 1, budget));
  const result = {};
  for (const key of Object.keys(value).sort()) {
    check4(!["__proto__", "constructor", "prototype"].includes(key) && key.length <= 256, "extension_batch_invalid");
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check4(descriptor && Object.hasOwn(descriptor, "value"), "extension_batch_invalid");
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
var HASH4 = /^[a-f0-9]{64}$/;
var BATCH = /^[a-z0-9][a-z0-9._-]{0,99}$/;
var ISO = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/;
var check5 = (value, code = "stock_status_invalid") => {
  if (!value) throw new GuardError(code);
};
var plain3 = (value) => value !== null && typeof value === "object" && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
var identity = (value) => typeof value === "string" && value.length > 0 && value.length <= 200 && value.trim() === value && !/[\u0000-\u001f\u007f]/.test(value);
var exact2 = (value, fields) => plain3(value) && Object.keys(value).sort().join(",") === [...fields].sort().join(",");
var bytes = (value) => encoder5.encode(value).byteLength;
var hash = (value) => typeof value === "string" && HASH4.test(value);
var batchIdentity = (value) => typeof value === "string" && BATCH.test(value);
function timestamp(value) {
  if (typeof value !== "string" || !ISO.test(value) || !Number.isFinite(Date.parse(value))) return false;
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1] && Number(value.slice(11, 13)) <= 23 && Number(value.slice(14, 16)) <= 59 && Number(value.slice(17, 19)) <= 59;
}
function jsonData(value, maximum, depth = 0, budget = { nodes: 0, bytes: 0 }) {
  check5(depth <= 24 && ++budget.nodes <= 2e4);
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "number") {
    check5(Number.isFinite(value));
    return value;
  }
  if (typeof value === "string") {
    budget.bytes += bytes(value);
    check5(value.length <= 65536 && budget.bytes <= maximum);
    return value;
  }
  const array = Array.isArray(value);
  check5(array || plain3(value));
  const keys = Reflect.ownKeys(value), copy = array ? [] : {};
  if (array) check5(value.length <= 2e4 && keys.length === value.length + 1);
  for (const key of keys) {
    if (array && key === "length") continue;
    check5(typeof key === "string" && key.length <= 256 && !["__proto__", "constructor", "prototype"].includes(key));
    if (array) check5(/^(?:0|[1-9]\d*)$/.test(key) && Number(key) < value.length);
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check5(descriptor?.enumerable === true && Object.hasOwn(descriptor, "value"));
    budget.bytes += bytes(key);
    check5(budget.bytes <= maximum);
    copy[key] = jsonData(descriptor.value, maximum, depth + 1, budget);
  }
  return copy;
}
function validateStockDescriptors(descriptors) {
  const copy = jsonData(descriptors, STOCK_STATUS_LIMITS.maxDescriptorBytes);
  check5(Array.isArray(copy) && copy.length >= 1 && copy.length <= STOCK_STATUS_LIMITS.maxDescriptors);
  check5(bytes(JSON.stringify(copy)) <= STOCK_STATUS_LIMITS.maxDescriptorBytes);
  const batchIds = /* @__PURE__ */ new Set(), itemIds = /* @__PURE__ */ new Set();
  for (const item of copy) {
    check5(exact2(item, ["batchId", "batchSha256", "itemIds"]) && batchIdentity(item.batchId) && hash(item.batchSha256));
    check5(Array.isArray(item.itemIds) && item.itemIds.length === 1 && identity(item.itemIds[0]));
    check5(!batchIds.has(item.batchId) && !itemIds.has(item.itemIds[0]));
    batchIds.add(item.batchId);
    itemIds.add(item.itemIds[0]);
    Object.freeze(item.itemIds);
    Object.freeze(item);
  }
  return Object.freeze(copy);
}
async function describeStockBatch(batch) {
  const source = canonicalPublicationJson(jsonData(batch, PUBLICATION_EXTENSION_LIMITS.maxBatchBytes));
  check5(bytes(JSON.stringify(source)) <= PUBLICATION_EXTENSION_LIMITS.maxBatchBytes);
  check5(exact2(source, ["schemaVersion", "batchId", "items"]) && source.schemaVersion === 1 && batchIdentity(source.batchId) && Array.isArray(source.items) && source.items.length === 1);
  const item = source.items[0], payload = item?.payload, review = item?.review;
  check5(exact2(item, ["contentId", "deduplicationKey", "title", "dueAt", "payload", "review"]) && identity(item.contentId) && identity(item.deduplicationKey) && identity(item.title) && timestamp(item.dueAt));
  check5(payload?.schemaVersion === 1 && payload.channel === "instagram" && payload.kind === "reel" && Array.isArray(payload.assets) && payload.assets.length === 1 && payload.assets[0]?.mimeType === "video/mp4");
  check5(review?.schemaVersion === 1 && review.contentId === item.contentId && review.approved === true && hash(review.payloadRevision) && review.payloadRevision === await bufferPayloadRevision(payload) && review.checks?.requiresPaidCall === false);
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
var HASH5 = /^[a-f0-9]{64}$/;
var BATCH_ID = /^[a-z0-9][a-z0-9._-]{0,99}$/;
var sha3 = (value) => createHash4("sha256").update(value).digest("hex");
var Refused3 = class extends Error {
  constructor(code) {
    super("Stock selection refused: " + code);
    this.name = "StockSelectionError";
  }
};
var check6 = (value, code) => {
  if (!value) throw new Refused3(code);
};
var plain4 = (value) => value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));
var exact3 = (value, keys) => plain4(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
var safeError = (error) => error instanceof Refused3 ? error : new Refused3("invalid_input");
var same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function jsonCopy(value, depth = 0, budget = { nodes: 0, bytes: 0 }) {
  check6(depth <= 24 && ++budget.nodes <= 2e4, "json_too_complex");
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    budget.bytes += Buffer.byteLength(value);
    check6(value.length <= 65536 && budget.bytes <= STOCK_SELECTION_LIMITS.maxBatchBytes, "json_too_large");
    return value;
  }
  if (typeof value === "number") {
    check6(Number.isFinite(value), "invalid_json");
    return value;
  }
  check6(Array.isArray(value) || plain4(value), "invalid_json");
  const array = Array.isArray(value), copy = array ? [] : {}, keys = Reflect.ownKeys(value);
  if (array) check6(value.length <= 2e4 && keys.length === value.length + 1, "invalid_json");
  for (const key of keys) {
    if (array && key === "length") continue;
    check6(typeof key === "string" && key.length <= 256 && !["__proto__", "constructor", "prototype"].includes(key), "invalid_json");
    if (array) check6(/^(?:0|[1-9]\d*)$/.test(key) && Number(key) < value.length, "invalid_json");
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    check6(descriptor?.enumerable === true && Object.hasOwn(descriptor, "value"), "invalid_json");
    budget.bytes += Buffer.byteLength(key);
    check6(budget.bytes <= STOCK_SELECTION_LIMITS.maxBatchBytes, "json_too_large");
    copy[key] = jsonCopy(descriptor.value, depth + 1, budget);
  }
  return Object.freeze(copy);
}
function boundedJson(bytes2, limit) {
  check6(Buffer.isBuffer(bytes2) && bytes2.length > 0 && bytes2.length <= limit, "file_size");
  return jsonCopy(JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes2)));
}
function indexSnapshot(value) {
  const index = jsonCopy(value);
  check6(Buffer.byteLength(JSON.stringify(index)) <= STOCK_SELECTION_LIMITS.maxIndexBytes && exact3(index, ["schemaVersion", "items"]) && index.schemaVersion === 1 && Array.isArray(index.items) && index.items.length <= STOCK_SELECTION_LIMITS.maxBatches, "invalid_index");
  const paths = /* @__PURE__ */ new Set(), batches = /* @__PURE__ */ new Set(), itemIds = /* @__PURE__ */ new Set();
  for (const entry of index.items) {
    check6(exact3(entry, ["path", "fileSha256", "batchId", "batchSha256", "itemIds"]) && typeof entry.batchId === "string" && BATCH_ID.test(entry.batchId) && !/^current(?:[._-]|$)/.test(entry.batchId) && entry.batchId !== "index" && entry.path === PREFIX + entry.batchId + ".json" && typeof entry.fileSha256 === "string" && HASH5.test(entry.fileSha256) && typeof entry.batchSha256 === "string" && HASH5.test(entry.batchSha256), "invalid_index_entry");
    validateStockDescriptors([{ batchId: entry.batchId, batchSha256: entry.batchSha256, itemIds: entry.itemIds }]);
    check6(!paths.has(entry.path) && !batches.has(entry.batchId) && entry.itemIds.every((id) => !itemIds.has(id)), "duplicate_index_identity");
    paths.add(entry.path);
    batches.add(entry.batchId);
    entry.itemIds.forEach((id) => itemIds.add(id));
  }
  return index;
}
function relativePath2(value) {
  check6(typeof value === "string" && value.length <= 250 && /^[A-Za-z0-9._/-]+$/.test(value) && value.split("/").every((part) => part && part !== "." && part !== ".."), "unsafe_path");
  return value;
}
async function noLinks(path, directory = false) {
  const absolute = resolve3(path), base = parse3(absolute).root;
  let current = base;
  for (const part of relative3(base, absolute).split(sep3).filter(Boolean)) {
    current = join3(current, part);
    const info = await lstat3(current);
    check6(!info.isSymbolicLink(), "symbolic_link");
    if (current !== absolute || directory) check6(info.isDirectory(), "directory_required");
  }
  check6(await realpath3(absolute) === absolute, "noncanonical_path");
  return absolute;
}
async function readSafe2(root, name, limit) {
  relativePath2(name);
  const path = join3(root, name);
  await noLinks(path);
  const handle = await open3(path, constants3.O_RDONLY | constants3.O_NOFOLLOW);
  try {
    const before = await handle.stat();
    check6(before.isFile() && before.size > 0 && before.size <= limit, "file_size");
    const bytes2 = await handle.readFile(), after = await handle.stat();
    check6(bytes2.length === before.size && after.size === before.size && before.mtimeMs === after.mtimeMs, "file_changed");
    return bytes2;
  } finally {
    await handle.close();
  }
}
async function loadStockIndex({ repositoryRoot, indexFile = PREFIX + "index.json" } = {}) {
  try {
    check6(typeof repositoryRoot === "string", "invalid_root");
    const root = await noLinks(repositoryRoot, true);
    const index = indexSnapshot(boundedJson(await readSafe2(root, indexFile, STOCK_SELECTION_LIMITS.maxIndexBytes), STOCK_SELECTION_LIMITS.maxIndexBytes));
    const files = /* @__PURE__ */ new Map();
    for (const entry of index.items) files.set(entry.path, await readSafe2(root, entry.path, STOCK_SELECTION_LIMITS.maxBatchBytes));
    await snapshotBatches({ index, files });
    return { index, files };
  } catch (error) {
    throw safeError(error);
  }
}
async function snapshotBatches(input) {
  const index = indexSnapshot(input?.index), files = input?.files;
  check6(files instanceof Map && files.size === index.items.length, "invalid_files");
  const snapshots = [];
  for (const entry of index.items) {
    const original = files.get(entry.path);
    check6(Buffer.isBuffer(original) && original.length <= STOCK_SELECTION_LIMITS.maxBatchBytes, "file_size");
    const bytes2 = Buffer.from(original);
    check6(sha3(bytes2) === entry.fileSha256, "file_hash_mismatch");
    const batch = boundedJson(bytes2, STOCK_SELECTION_LIMITS.maxBatchBytes), descriptor = await describeStockBatch(batch);
    check6(descriptor.batchId === entry.batchId && descriptor.batchSha256 === entry.batchSha256 && same(descriptor.itemIds, entry.itemIds), "batch_descriptor_mismatch");
    snapshots.push({ entry, batch, descriptor });
  }
  return snapshots;
}

// exploitation/production-contenus/promotion-control.mjs
var PROD = ".github/vsd-production";
var SITE = "site-src";
var STOCK = PROD + "/reviewed-social";
var MANIFEST = PROD + "/promotion-index.json";
var INDEX = STOCK + "/index.json";
var ORIGIN3 = "https://voyagesansdetour.fr";
var MAX = 512 * 1024;
var HASH6 = /^[a-f0-9]{64}$/;
var ID3 = /^[a-z0-9][a-z0-9-]{0,95}$/;
var BATCH2 = /^[a-z0-9][a-z0-9._-]{0,99}$/;
var sha4 = (bytes2) => createHash5("sha256").update(bytes2).digest("hex");
var encode2 = (value) => Buffer.from(JSON.stringify(value, null, 2) + "\n");
var canonical = (value) => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])])) : value;
var same2 = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
var exact4 = (v, keys) => v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === keys.length && keys.every((key) => Object.hasOwn(v, key));
var Refused4 = class extends Error {
  constructor(code) {
    super("Promotion control refused: " + code);
    this.code = code;
    this.name = "PromotionControlError";
  }
};
var check7 = (value, code) => {
  if (!value) throw new Refused4(code);
};
var json2 = (bytes2) => JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes2));
var iso = (value) => {
  check7(typeof value === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$/.test(value), "invalid_date");
  const at = Date.parse(value);
  check7(Number.isFinite(at) && new Date(at).toISOString().slice(0, 19) === value.slice(0, 19), "invalid_date");
  return at;
};
async function inspect(path, make = false, directory = false) {
  const absolute = resolve4(path);
  let cursor = parse4(absolute).root;
  for (const part of relative4(cursor, absolute).split(sep4).filter(Boolean)) {
    cursor = join4(cursor, part);
    let stat;
    try {
      stat = await lstat4(cursor);
    } catch (e) {
      if (e.code !== "ENOENT") throw e;
      if (!make) return null;
      try {
        await mkdir2(cursor);
      } catch (e2) {
        if (e2.code !== "EEXIST") throw e2;
      }
      stat = await lstat4(cursor);
    }
    check7(!stat.isSymbolicLink(), "symlink_refused");
    if (cursor !== absolute || directory) check7(stat.isDirectory(), "directory_required");
  }
  check7(await realpath4(absolute) === absolute, "noncanonical_path");
  return absolute;
}
async function read(path, limit = MAX, optional = false) {
  if (!await inspect(path)) {
    check7(optional, "file_missing");
    return null;
  }
  const handle = await open4(path, constants4.O_RDONLY | constants4.O_NOFOLLOW);
  try {
    const before = await handle.stat();
    check7(before.isFile() && before.size <= limit, "file_size");
    const bytes2 = await handle.readFile(), after = await handle.stat();
    check7(bytes2.length === before.size && before.size === after.size && before.mtimeMs === after.mtimeMs, "file_changed");
    return bytes2;
  } finally {
    await handle.close();
  }
}
async function syncDir(path) {
  const f = await open4(path, constants4.O_RDONLY);
  try {
    await f.sync();
  } finally {
    await f.close();
  }
}
async function temp(path, bytes2) {
  await inspect(dirname2(path), true, true);
  const name = join4(dirname2(path), ".vsd-control-" + randomUUID2() + ".tmp");
  const f = await open4(name, constants4.O_WRONLY | constants4.O_CREAT | constants4.O_EXCL | constants4.O_NOFOLLOW, 384);
  try {
    await f.writeFile(bytes2);
    await f.sync();
  } finally {
    await f.close();
  }
  return name;
}
async function immutable(path, bytes2) {
  const existing = await read(path, bytes2.length, true);
  if (existing) {
    check7(existing.equals(bytes2), "immutable_conflict");
    return false;
  }
  const name = await temp(path, bytes2);
  try {
    try {
      await link2(name, path);
    } catch (e) {
      if (e.code !== "EEXIST") throw e;
      check7((await read(path, bytes2.length)).equals(bytes2), "immutable_conflict");
      return false;
    }
    await syncDir(dirname2(path));
    return true;
  } finally {
    await unlink2(name);
  }
}
async function replace(path, before, after) {
  if (before.equals(after)) return false;
  check7((await read(path)).equals(before), "index_changed");
  const name = await temp(path, after);
  try {
    check7((await read(path)).equals(before), "index_changed");
    await rename2(name, path);
    await syncDir(dirname2(path));
    return true;
  } finally {
    await unlink2(name).catch((e) => {
      if (e.code !== "ENOENT") throw e;
    });
  }
}
async function locked2(root, callback) {
  const path = join4(root, PROD, ".promotion-control.lock");
  let handle;
  try {
    handle = await open4(path, constants4.O_WRONLY | constants4.O_CREAT | constants4.O_EXCL | constants4.O_NOFOLLOW, 384);
  } catch (e) {
    if (["EEXIST", "ELOOP"].includes(e.code)) throw new Refused4("controller_locked");
    throw e;
  }
  const owner = await handle.stat();
  try {
    return await callback();
  } finally {
    await handle.close();
    const current = await lstat4(path);
    check7(!current.isSymbolicLink() && current.dev === owner.dev && current.ino === owner.ino, "lock_changed");
    await unlink2(path);
  }
}
function names(batchId) {
  check7(typeof batchId === "string" && BATCH2.test(batchId) && !/^current(?:[._-]|$)/.test(batchId) && batchId !== "index", "batch_id");
  const p = PROD + "/promotion/";
  return {
    control: p + "control/" + batchId + ".json",
    candidate: p + "candidates/" + batchId + ".json",
    stage: p + "staged/" + batchId + ".json",
    proof: p + "proofs/" + batchId + ".json",
    reviewed: p + "reviewed/" + batchId + ".json",
    stock: STOCK + "/" + batchId + ".json"
  };
}
async function manifest(root) {
  const bytes2 = await read(join4(root, MANIFEST), 128 * 1024), value = json2(bytes2);
  check7(exact4(value, ["schemaVersion", "items"]) && value.schemaVersion === 1 && Array.isArray(value.items) && value.items.length <= 64, "manifest_schema");
  const seen = /* @__PURE__ */ new Set(), batches = /* @__PURE__ */ new Set(), entries = [];
  for (const e of value.items) {
    check7(exact4(e, ["contentId", "renderDirectory", "receiptSha256", "review", "cloudProof"]) && typeof e.contentId === "string" && ID3.test(e.contentId) && !seen.has(e.contentId) && e.renderDirectory === "output/" + e.contentId && typeof e.receiptSha256 === "string" && HASH6.test(e.receiptSha256), "manifest_entry");
    for (const [name, prefix] of [["review", "reviews"], ["cloudProof", "evidence"]]) {
      check7(exact4(e[name], ["file", "sha256"]) && typeof e[name].file === "string" && new RegExp("^" + prefix + "/[a-z0-9][a-z0-9._-]{0,180}\\.json$").test(e[name].file) && typeof e[name].sha256 === "string" && HASH6.test(e[name].sha256), "manifest_path");
      check7(sha4(await read(join4(root, PROD, e[name].file))) === e[name].sha256, "manifest_file_hash");
    }
    check7(sha4(await read(join4(root, PROD, e.renderDirectory, "receipt.json"))) === e.receiptSha256, "manifest_receipt_hash");
    const review = json2(await read(join4(root, PROD, e.review.file))), batchId = review.publication?.batchId;
    names(batchId);
    check7(review.contentId === e.contentId && !batches.has(batchId), "manifest_review_identity");
    iso(review.publication.dueAt);
    iso(review.validUntil);
    seen.add(e.contentId);
    batches.add(batchId);
    entries.push({ entry: e, review, batchId });
  }
  return { entries, sha256: sha4(bytes2) };
}
function options(root, record) {
  return {
    productionRoot: join4(root, PROD),
    renderDirectory: record.entry.renderDirectory,
    independentReviewFile: record.entry.review.file,
    cloudProofFile: record.entry.cloudProof.file,
    siteRoot: join4(root, SITE),
    outputRoot: join4(root, PROD, "promotion"),
    publicProofFile: "promotion/proofs/" + record.batchId + ".json"
  };
}
async function inputsFor(root, record) {
  const input = await loadPromotionInputs(options(root, record));
  check7(sha4(input.receiptBytes) === record.entry.receiptSha256 && sha4(input.independentReviewBytes) === record.entry.review.sha256 && sha4(input.cloudProofBytes) === record.entry.cloudProof.sha256, "pinned_input_changed");
  return input;
}
function controlFor(record) {
  return {
    schemaVersion: 1,
    contentId: record.entry.contentId,
    batchId: record.batchId,
    manifestEntrySha256: sha4(encode2(record.entry)),
    receiptSha256: record.entry.receiptSha256,
    reviewSha256: record.entry.review.sha256,
    cloudProofSha256: record.entry.cloudProof.sha256
  };
}
function stageReceiptFor(bundle) {
  return {
    schemaVersion: 1,
    status: "staged_not_deployed_or_imported",
    batchId: bundle.candidateBatch.batchId,
    contentId: bundle.publicEntry.contentId,
    candidateSha256: sha4(encode2(bundle.candidateBatch)),
    publicEntrySha256: sha4(encode2(bundle.publicEntry)),
    files: bundle.publicFiles.map((f) => ({ path: f.path, sha256: f.sha256, bytes: f.size }))
  };
}
function guideFor(batch) {
  const url = batch?.items?.[0]?.review?.destination?.url;
  check7(typeof url === "string" && /^https:\/\/voyagesansdetour\.fr\/portugal\/[a-z0-9][a-z0-9-]*\/$/.test(url), "guide_url_invalid");
  return url;
}
async function historicalExpected(input, proofBytes) {
  const receipt = json2(input.receiptBytes), review = json2(input.independentReviewBytes), cloud = json2(input.cloudProofBytes);
  const scenario = json2(input.files.get("scenario.json")), catalogue = json2(input.catalogueBytes);
  const id = receipt.contentId, expiry = review.validUntil;
  check7(ID3.test(id) && receipt.schemaVersion === 1 && receipt.rendererContractVersion === 2 && receipt.status === "rendered_not_published" && receipt.contentId === scenario.id && review.contentId === id && same2(scenario, json2(input.sourceScenarioBytes)), "historical_source");
  const source = catalogue.items.filter((e) => e.contentId === id);
  check7(source.length === 1 && source[0].sha256 === sha4(input.sourceScenarioBytes), "historical_catalogue");
  check7(review.schemaVersion === 1 && review.contentAndFormatApproved === true && review.publicMediaApproved === true && review.publicationApproved === true && review.receiptSha256 === sha4(input.receiptBytes) && review.mediaSha256 === sha4(input.files.get("reel.mp4")) && review.captionSha256 === sha4(input.files.get("legende.txt")) && review.scenarioSha256 === sha4(input.files.get("scenario.json")) && review.cloudProofSha256 === sha4(input.cloudProofBytes), "historical_review");
  check7(["editorialApproved", "rightsApproved", "creditsPreserved", "disclosurePreserved", "formatRequirementsVerified"].every((k) => review.checks?.[k] === true) && review.checks.requiresPaidCall === false && receipt.presenter === "none" && receipt.voice === null && scenario.presenter === "none", "historical_approval");
  check7(cloud.repository === "MathCSN/voyagesansdetour" && cloud.run?.head_branch === "main" && cloud.run.status === "completed" && cloud.run.conclusion === "success" && cloud.receiptSha256 === review.receiptSha256 && cloud.allFileHashesVerified === true && cloud.artifactPath === ".github/vsd-production/output/" + id + "/", "historical_cloud");
  check7(iso(receipt.renderFinishedAt) <= iso(review.reviewedAt) && iso(review.reviewedAt) < iso(expiry) && expiry === receipt.reviewValidUntil, "historical_dates");
  for (const file of receipt.files) {
    const bytes2 = input.files.get(file.file);
    check7(bytes2 && bytes2.length === file.bytes && sha4(bytes2) === file.sha256, "historical_file_hash");
  }
  const caption = new TextDecoder("utf-8", { fatal: true }).decode(input.files.get("legende.txt"));
  const target = scenario.targetUrl;
  check7(/^https:\/\/voyagesansdetour\.fr\/portugal\/[a-z0-9-]+\/$/.test(target), "historical_target");
  const proof = json2(proofBytes);
  check7(exact4(proof, ["schemaVersion", "source", "observedAt", "files", "destination"]) && proof.schemaVersion === 1 && proof.source === "bounded_live_http_get" && iso(proof.observedAt) >= iso(review.reviewedAt) && iso(proof.observedAt) < Math.min(iso(expiry), iso(review.publication.dueAt)) && Array.isArray(proof.files) && proof.files.length === 5, "historical_proof");
  const mime2 = (name) => name === "reel.mp4" ? "video/mp4" : name === "poster.jpg" ? "image/jpeg" : "text/plain";
  for (const name of PUBLIC_NAMES) {
    const url = ORIGIN3 + "/social-media/production/" + id + "/" + name, rows = proof.files.filter((f) => f.url === url), bytes2 = input.files.get(name);
    check7(rows.length === 1 && same2(rows[0], { url, finalUrl: url, httpStatus: 200, mimeType: mime2(name), bytes: bytes2.length, sha256: sha4(bytes2) }), "historical_public_file");
  }
  const guideFields = ["url", "finalUrl", "canonicalUrl", "httpStatus", "sha256"];
  const historicGuideFields = [...guideFields, "mimeType", "bytes"];
  check7((exact4(proof.destination, guideFields) || exact4(proof.destination, historicGuideFields) && proof.destination.mimeType === "text/html" && Number.isSafeInteger(proof.destination.bytes) && proof.destination.bytes > 0 && proof.destination.bytes <= 1024 * 1024) && proof.destination.url === target && proof.destination.finalUrl === target && proof.destination.canonicalUrl === target && proof.destination.httpStatus === 200 && HASH6.test(proof.destination.sha256), "historical_guide");
  const asset = { url: ORIGIN3 + "/social-media/production/" + id + "/reel.mp4", mimeType: "video/mp4", sha256: review.mediaSha256 };
  const contentId = "vsd-production:instagram:" + id + ":cloud-v2";
  const payload = { schemaVersion: 1, channel: "instagram", kind: "reel", text: caption, aiGenerated: false, assets: [asset] };
  const verification = { status: "verified", observedAt: proof.observedAt, validUntil: expiry };
  return { schemaVersion: 1, batchId: review.publication.batchId, items: [{
    contentId,
    deduplicationKey: contentId,
    title: review.publication.title,
    dueAt: review.publication.dueAt,
    payload,
    review: {
      schemaVersion: 1,
      contentId,
      approved: true,
      reviewedAt: review.reviewedAt,
      validUntil: expiry,
      payloadRevision: await bufferPayloadRevision(payload),
      checks: { ...review.checks, sources: structuredClone(review.sources), syntheticPerson: false, providerSyntheticSettingVerified: false },
      media: { ...asset, required: true, ...verification },
      destination: { url: target, ...verification },
      monetization: { containsAffiliateLinks: false, partnerApproved: false, linksVerified: false, disclosurePreserved: false },
      formatCapability: structuredClone(review.formatCapability),
      evidence: {
        status: "reviewed_public_bytes_verified_not_imported",
        rendererContractVersion: 2,
        finalMediaProducedInCloud: true,
        sourceCloudRun: cloud.run.html_url,
        sourceCloudArtifactCommit: cloud.artifactCommit.sha,
        receiptSha256: review.receiptSha256,
        independentReviewSha256: sha4(input.independentReviewBytes),
        mediaSha256: review.mediaSha256,
        captionSha256: review.captionSha256,
        sourceCheckedOn: receipt.sourceCheckedOn,
        sourceUrls: [...receipt.sourceUrls],
        audioBitrateBps: receipt.video.audioBitrateBps,
        note: "An intended slot is not a Buffer reservation. Existing scheduler gates remain mandatory.",
        publicProofSha256: sha4(proofBytes)
      }
    }
  }] };
}
async function history(root, record, stock) {
  const p = names(record.batchId), indexed = stock.index.items.find((e) => e.batchId === record.batchId);
  const stored = indexed ? stock.files.get(indexed.path) : await read(join4(root, p.reviewed), 128 * 1024, true);
  if (!stored) return null;
  const proof = await read(join4(root, p.proof)), input = await inputsFor(root, record), expected = await historicalExpected(input, proof);
  check7(same2(json2(stored), expected), "historical_final_mismatch");
  const existingPrivate = await read(join4(root, p.reviewed), 128 * 1024, true);
  if (existingPrivate) check7(existingPrivate.equals(stored), "historical_copy_conflict");
  return { indexed: Boolean(indexed), bytes: stored, descriptor: await describeStockBatch(json2(stored)) };
}
async function stagePresent(root, record, bundle) {
  const p = names(record.batchId);
  check7((await read(join4(root, p.control))).equals(encode2(controlFor(record))), "stage_control_required");
  check7((await read(join4(root, p.candidate))).equals(encode2(bundle.candidateBatch)) && (await read(join4(root, p.stage))).equals(encode2(stageReceiptFor(bundle))), "stage_required");
  for (const f of bundle.publicFiles) check7((await read(join4(root, SITE, f.path), f.size)).equals(f.bytes), "stage_media_mismatch");
  const catalogue = json2(await read(join4(root, SITE, "public-media.json")));
  check7(mergePublicMediaCatalogue(catalogue, bundle.publicEntry).items.length === catalogue.items.length, "stage_catalogue_missing");
}
async function builtGuide(root, bundle) {
  for (const f of bundle.publicFiles) check7((await read(join4(root, SITE, "public", f.path), f.size)).equals(f.bytes), "built_media_mismatch");
  const target = new URL(bundle.candidateBatch.items[0].review.destination.url);
  check7(target.origin === ORIGIN3 && /^\/portugal\/[a-z0-9-]+\/$/.test(target.pathname) && !target.search && !target.hash, "built_guide_path");
  return sha4(await read(join4(root, SITE, "public", target.pathname.slice(1), "index.html"), 1024 * 1024));
}
async function beforePaths(root, paths) {
  const map = /* @__PURE__ */ new Map();
  for (const p of paths) {
    const b = await read(join4(root, p), 5e7, true);
    map.set(p, b ? sha4(b) : null);
  }
  return map;
}
async function changedPaths(root, before) {
  const changed = [];
  for (const [p, hash2] of before) {
    const b = await read(join4(root, p), 5e7, true);
    if ((b ? sha4(b) : null) !== hash2) changed.push(p);
  }
  return changed;
}
async function indexFinal(root, record, bytes2, stock, onPhase) {
  const p = names(record.batchId), descriptor = await describeStockBatch(json2(bytes2));
  check7(descriptor.batchId === record.batchId && same2(descriptor.itemIds, ["vsd-production:instagram:" + record.entry.contentId + ":cloud-v2"]), "final_identity");
  const entry = { path: p.stock, fileSha256: sha4(bytes2), ...descriptor };
  check7(stock.index.items.length < 64 && !stock.index.items.some((e) => e.batchId === entry.batchId || e.path === entry.path || e.itemIds.some((id) => entry.itemIds.includes(id))), "stock_index_conflict");
  const before = await read(join4(root, INDEX), 64 * 1024);
  check7(same2(json2(before), stock.index), "stock_index_changed");
  await immutable(join4(root, p.stock), bytes2);
  await onPhase("stock_file_ready");
  const after = encode2({ schemaVersion: 1, items: [...stock.index.items, entry] });
  check7(after.length <= 64 * 1024, "stock_index_too_large");
  await replace(join4(root, INDEX), before, after);
  await onPhase("index_ready");
}
async function runPromotionControl({ mode, repositoryRoot, contentId } = {}, {
  now = () => (/* @__PURE__ */ new Date()).toISOString(),
  fetcher,
  onPhase = async () => {
  }
} = {}) {
  try {
    check7(["stage", "finalize"].includes(mode) && typeof repositoryRoot === "string" && typeof now === "function" && typeof onPhase === "function" && (contentId === void 0 || ID3.test(contentId)) && (mode !== "finalize" || contentId), "invalid_options");
    const root = resolve4(repositoryRoot);
    check7(await inspect(root, false, true) && await inspect(join4(root, PROD), false, true) && await inspect(join4(root, SITE), false, true), "roots_missing");
    return await locked2(root, async () => {
      const source = await manifest(root), stock = await loadStockIndex({ repositoryRoot: root });
      let records = source.entries;
      if (contentId) {
        records = records.filter((r) => r.entry.contentId === contentId);
        check7(records.length === 1, "unknown_content");
      }
      records.sort((a, b) => iso(a.review.publication.dueAt) - iso(b.review.publication.dueAt) || a.entry.contentId.localeCompare(b.entry.contentId, "en"));
      let selected, previous;
      for (const record of records) {
        const old = await history(root, record, stock);
        if (old?.indexed) {
          if (contentId) return {
            schemaVersion: 1,
            status: "already_finalized",
            contentId,
            batchId: record.batchId,
            changedPaths: [],
            requiresDeployment: false,
            manifestSha256: source.sha256,
            proofPath: names(record.batchId).proof,
            reviewedBatchPath: names(record.batchId).stock,
            stockIndexPath: INDEX
          };
          continue;
        }
        if (old || iso(record.review.reviewedAt) <= iso(now()) && iso(now()) < Math.min(iso(record.review.validUntil), iso(record.review.publication.dueAt))) {
          selected = record;
          previous = old;
          break;
        }
      }
      if (!selected) return { schemaVersion: 1, status: "idle", reason: "no_pending_eligible_promotion", contentId: null, batchId: null, changedPaths: [], requiresDeployment: false, manifestSha256: source.sha256 };
      const p = names(selected.batchId), base = {
        schemaVersion: 1,
        contentId: selected.entry.contentId,
        batchId: selected.batchId,
        manifestSha256: source.sha256,
        proofPath: p.proof,
        reviewedBatchPath: p.stock,
        stockIndexPath: INDEX
      };
      if (mode === "stage" && previous) return { ...base, guideUrl: guideFor(json2(previous.bytes)), status: "finalization_ready", changedPaths: [], requiresDeployment: false };
      const paths = mode === "stage" ? [p.control, p.candidate, p.stage, SITE + "/public-media.json", ...PUBLIC_NAMES.map((n) => SITE + "/social-media/production/" + selected.entry.contentId + "/" + n)] : [p.proof, p.reviewed, p.stock, INDEX];
      const before = await beforePaths(root, paths);
      if (previous) {
        await indexFinal(root, selected, previous.bytes, stock, onPhase);
        return { ...base, guideUrl: guideFor(json2(previous.bytes)), status: "finalized", changedPaths: await changedPaths(root, before), requiresDeployment: false };
      }
      const input = await inputsFor(root, selected), bundle = await buildPromotionBundle(input, { now: now() });
      base.guideUrl = guideFor(bundle.candidateBatch);
      if (mode === "stage") {
        await immutable(join4(root, p.control), encode2(controlFor(selected)));
        await stagePromotion(options(root, selected), { now: now() });
        await onPhase("stage_ready");
        return { ...base, status: "stage_ready", changedPaths: await changedPaths(root, before), requiresDeployment: true };
      }
      await stagePresent(root, selected, bundle);
      const guideSha256 = await builtGuide(root, bundle);
      let proofBytes = await read(join4(root, p.proof), MAX, true);
      if (!proofBytes) {
        const proof = await collectPublicProof(bundle, guideSha256, { ...fetcher ? { fetcher } : {}, now });
        proofBytes = encode2(proof);
        await immutable(join4(root, p.proof), proofBytes);
        await onPhase("proof_frozen");
      }
      check7(json2(proofBytes).destination?.sha256 === guideSha256, "original_proof_guide_mismatch");
      await finalizePromotion(options(root, selected), { now: now() });
      await onPhase("reviewed_ready");
      const reviewed = await read(join4(root, p.reviewed), 128 * 1024);
      check7(same2(json2(reviewed), await historicalExpected(input, proofBytes)), "final_mapping_mismatch");
      await indexFinal(root, selected, reviewed, stock, onPhase);
      return { ...base, status: "finalized", changedPaths: await changedPaths(root, before), requiresDeployment: false };
    });
  } catch (e) {
    throw e instanceof Refused4 ? e : new Refused4("input_or_operation_failed");
  }
}
function parsePromotionArguments(argv) {
  const [mode, ...args] = argv, values = {};
  check7(["stage", "finalize"].includes(mode) && args.length % 2 === 0, "arguments");
  for (let i = 0; i < args.length; i += 2) {
    const key = { "--repository-root": "repositoryRoot", "--content-id": "contentId" }[args[i]];
    check7(key && !Object.hasOwn(values, key) && args[i + 1] && !args[i + 1].startsWith("--"), "arguments");
    values[key] = args[i + 1];
  }
  check7(values.repositoryRoot && (mode !== "finalize" || values.contentId), "arguments");
  return { mode, ...values };
}
if (process.argv[1] && import.meta.url === pathToFileURL2(resolve4(process.argv[1])).href) {
  try {
    console.log(JSON.stringify(await runPromotionControl(parsePromotionArguments(process.argv.slice(2)))));
  } catch (e) {
    console.error(JSON.stringify({ status: "refused", reason: e instanceof Refused4 ? e.code : "input_or_operation_failed" }));
    process.exitCode = 1;
  }
}
export {
  parsePromotionArguments,
  runPromotionControl
};
