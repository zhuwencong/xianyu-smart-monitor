#!/usr/bin/env node
/**
 * 校验「上架材料」是否满足两条官方渠道的格式要求（零依赖，CI 可直接跑）：
 *
 *   1. awesome-dsh-plugin 精选目录条目（材料在 publish/dsh/）
 *      data/plugins/<owner>__<repo>[--<子包路径用-连接>].yml
 *      → 文件名、url、name 三者必须自洽；category 在枚举内；description 结尾与引号正确
 *
 *   2. WorkBuddy 技能包（材料在 publish/workbuddy/）
 *      plugins/workbuddy/<skill>/SKILL.md → 8 个必填 frontmatter 字段 + 命名规范
 *      release/<skill>.zip              → 根目录只有一层技能目录、无 __pycache__、CRC 完好
 *
 * 用法：
 *   node scripts/check-publish-artifacts.mjs
 *   node scripts/check-publish-artifacts.mjs --zip release/xianyu-monitor.zip
 */
import { readFileSync, existsSync, readdirSync } from 'node:fs'
import { dirname, join, resolve, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import { inflateRawSync } from 'node:zlib'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(HERE, '..')

const ENTRY_DIR = join(REPO_ROOT, 'publish', 'dsh', 'data', 'plugins')
const SKILL_DIR = join(REPO_ROOT, 'plugins', 'workbuddy', 'xianyu-monitor')
const PLUGIN_DIR = join(REPO_ROOT, 'plugins', 'dsh')
// 截图声明在插件自己的 package.json 旁边（monorepo 就放在子包目录里），
// 不再往目录仓库的 data/screenshots.json 里加东西。
const SHOTS = join(PLUGIN_DIR, 'screenshots.json')

/** 目录收录允许的分类（contributing.md 的枚举 + 站上已有的 agi） */
const CATEGORIES = new Set([
  'agi', 'ui', 'usage', 'theme', 'model', 'session', 'memory', 'tools', 'wsl',
  'browser', 'vision', 'voice', 'docs', 'skill', 'workflow', 'git', 'notify',
  'dev', 'security', 'remote', 'market', 'fun',
])

/** WorkBuddy SKILL.md 必填字段（open.workbuddy.cn/docs/skill） */
const SKILL_REQUIRED = [
  'name',
  'display_name',
  'display_name_en',
  'description',
  'description_zh',
  'description_en',
  'version',
  'author',
]

const errors = []
const warnings = []
const ok = (msg) => console.log(`  ✓ ${msg}`)
const fail = (msg) => {
  errors.push(msg)
  console.log(`  ✗ ${msg}`)
}
const warn = (msg) => {
  warnings.push(msg)
  console.log(`  ⚠ ${msg}`)
}

// ---- 极简 YAML 读取（只认本目录用到的形状：顶层标量 + 一层 mapping） --------

function unquote(value) {
  const trimmed = value.trim()
  if (trimmed.length >= 2) {
    const first = trimmed[0]
    const last = trimmed[trimmed.length - 1]
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return { value: trimmed.slice(1, -1), quoted: true, raw: trimmed }
    }
  }
  return { value: trimmed, quoted: false, raw: trimmed }
}

function parseSimpleYaml(text) {
  const result = {}
  let section = null
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith('#')) continue
    const indent = line.length - line.trimStart().length
    const match = line.trim().match(/^([A-Za-z][\w-]*):\s*(.*)$/)
    if (!match) continue
    const [, key, rest] = match
    if (indent === 0) {
      if (rest.trim() === '') {
        section = key
        result[key] = {}
      } else {
        section = null
        result[key] = unquote(rest)
      }
    } else if (section) {
      result[section][key] = unquote(rest)
    }
  }
  return result
}

// ---- zip 读取（中央目录 → 逐条解压 + CRC 校验） ---------------------------

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let c = n
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buffer) {
  let crc = 0xffffffff
  for (let i = 0; i < buffer.length; i += 1) crc = CRC_TABLE[(crc ^ buffer[i]) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function readZipEntries(buf) {
  let eocd = -1
  const floor = Math.max(0, buf.length - 22 - 0xffff)
  for (let i = buf.length - 22; i >= floor; i -= 1) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd < 0) throw new Error('找不到 zip 的 End of Central Directory 记录（不是合法 zip）')

  const count = buf.readUInt16LE(eocd + 10)
  let p = buf.readUInt32LE(eocd + 16)
  const entries = []
  for (let i = 0; i < count; i += 1) {
    if (buf.readUInt32LE(p) !== 0x02014b50) throw new Error('中央目录条目签名异常')
    const nameLen = buf.readUInt16LE(p + 28)
    const extraLen = buf.readUInt16LE(p + 30)
    const commentLen = buf.readUInt16LE(p + 32)
    entries.push({
      name: buf.toString('utf8', p + 46, p + 46 + nameLen),
      method: buf.readUInt16LE(p + 10),
      crc: buf.readUInt32LE(p + 16),
      compSize: buf.readUInt32LE(p + 20),
      size: buf.readUInt32LE(p + 24),
      localOffset: buf.readUInt32LE(p + 42),
    })
    p += 46 + nameLen + extraLen + commentLen
  }
  return entries
}

function readZipEntryData(buf, entry) {
  const p = entry.localOffset
  if (buf.readUInt32LE(p) !== 0x04034b50) throw new Error(`${entry.name}: 本地文件头签名异常`)
  const start = p + 30 + buf.readUInt16LE(p + 26) + buf.readUInt16LE(p + 28)
  const raw = buf.subarray(start, start + entry.compSize)
  if (entry.method === 0) return Buffer.from(raw)
  if (entry.method === 8) return inflateRawSync(raw)
  throw new Error(`${entry.name}: 不支持的压缩方式 ${entry.method}`)
}

function frontmatter(text) {
  const match = text.match(/^---\r?\n([\s\S]*?)\r?\n---/)
  if (!match) return null
  const fields = {}
  let current = null
  for (const line of match[1].split(/\r?\n/)) {
    // 列表项（examples_zh / examples_en 这类）
    const item = line.match(/^\s+-\s+(.*)$/)
    if (item && current) {
      if (!Array.isArray(fields[current])) fields[current] = []
      fields[current].push(unquote(item[1]).value)
      continue
    }
    const m = line.match(/^([A-Za-z][\w-]*):\s*(.*)$/)
    if (!m) continue
    current = m[1]
    const value = unquote(m[2]).value
    fields[current] = value === '' ? [] : value
  }
  return fields
}

// ---- 1. DSH 精选目录条目 ---------------------------------------------------

function checkCatalogEntry() {
  console.log('\n[1/3] DSH 精选目录条目（awesome-dsh-plugin）')
  if (!existsSync(ENTRY_DIR)) {
    fail(`找不到目录 ${ENTRY_DIR}`)
    return
  }
  const files = readdirSync(ENTRY_DIR).filter((name) => name.endsWith('.yml'))
  if (files.length !== 1) {
    fail(`data/plugins/ 里应该正好有 1 个 .yml，实际 ${files.length} 个`)
    return
  }

  const file = files[0]
  const text = readFileSync(join(ENTRY_DIR, file), 'utf8')
  const entry = parseSimpleYaml(text)

  // 文件名 → owner / repo / 子包路径
  const stem = file.replace(/\.yml$/, '')
  const [owner, rest] = stem.split('__')
  if (!owner || !rest) {
    fail(`文件名 ${file} 不符合 <owner>__<repo>[--path].yml`)
    return
  }
  const [repo, pathSeg] = rest.split('--')
  const expectedPath = pathSeg ? pathSeg.split('-').join('/') : null
  const expectedSub = expectedPath ? expectedPath.split('/').pop() : null

  // url
  const url = entry.url?.value
  if (!url) fail('缺 url')
  else {
    let parsed = null
    try {
      parsed = new URL(url)
    } catch {
      fail(`url 不是合法 URL：${url}`)
    }
    if (parsed) {
      const parts = parsed.pathname.split('/').filter(Boolean)
      if (parsed.hostname !== 'github.com') fail(`url 必须指向 github.com，当前 ${parsed.hostname}`)
      if (parts[0] !== owner || parts[1] !== repo) {
        fail(`url 的 owner/repo（${parts[0]}/${parts[1]}）与文件名（${owner}/${repo}）不一致`)
      }
      if (expectedPath) {
        const sub = parts.slice(4).join('/')
        if (parts[2] !== 'tree') fail('monorepo 子包的 url 必须是 .../tree/<branch>/<path>')
        if (sub !== expectedPath) fail(`url 里的子包路径（${sub}）与文件名推导的（${expectedPath}）不一致`)
      }
    }
  }

  // name
  const expectedName = expectedPath ? `${owner}/${repo}#${expectedSub}` : `${owner}/${repo}`
  if (!entry.name?.value) fail('缺 name')
  else if (entry.name.value !== expectedName) fail(`name 应为 ${expectedName}，当前 ${entry.name.value}`)

  // category
  if (!entry.category?.value) fail('缺 category')
  else if (!CATEGORIES.has(entry.category.value)) {
    fail(`category="${entry.category.value}" 不在收录枚举里`)
  }

  // description
  const desc = entry.description || {}
  const en = desc.en?.value
  const zh = desc.zh?.value
  if (!en) fail('缺 description.en（唯一必填的描述字段）')
  else {
    if (!en.endsWith('.')) fail('description.en 必须以英文句点结尾')
    if (en.length < 20 || en.length > 300) warn(`description.en 长度 ${en.length}，建议 20–300 字符`)
    if (/[<>]/.test(en)) fail('description.en 不能含 < 或 >')
    if (/\s{2,}/.test(en)) warn('description.en 有多余空格')
  }
  if (zh && !/[。.]$/.test(zh)) fail('description.zh 必须以句号结尾')

  // 含「: 」的标量必须加引号，否则 YAML 会当成嵌套键
  const scalars = [
    ['url', entry.url],
    ['name', entry.name],
    ['category', entry.category],
    ['description.en', desc.en],
    ['description.zh', desc.zh],
  ]
  for (const [label, node] of scalars) {
    if (!node) continue
    if (node.raw.includes(': ') && !node.quoted) fail(`${label} 含 ": "，必须整体加引号`)
  }

  if (errors.length === 0) ok(`${file} → ${entry.name?.value} / ${entry.category?.value}`)

  // 截图清单（可选，但存在就要合规）：官方要求放在插件自己的目录里
  // （`package.json` 旁边），1–8 张、路径相对该文件、图片必须已在仓库中。
  if (existsSync(SHOTS)) {
    try {
      const parsed = JSON.parse(readFileSync(SHOTS, 'utf8'))
      const list = Array.isArray(parsed) ? parsed : parsed.screenshots
      if (!Array.isArray(list) || list.length < 1 || list.length > 8) {
        fail('plugins/dsh/screenshots.json 需列出 1–8 张图')
      } else {
        for (const image of list) {
          if (typeof image !== 'string' || !image.trim()) {
            fail(`截图路径必须是非空字符串：${JSON.stringify(image)}`)
            continue
          }
          if (/^[a-z][a-z0-9+.-]*:/i.test(image) || image.startsWith('/')) {
            fail(`截图必须是仓库内相对路径，不能是 URL 或绝对路径：${image}`)
            continue
          }
          // 与上游 probe-screenshots.mjs 一致：相对路径不得跳出插件目录
          // （`../` 会被判 "relative paths must stay inside the plugin directory"）。
          if (image.split('/').includes('..')) {
            fail(`截图路径不能跳出 plugins/dsh/（不要用 ../）：${image}`)
            continue
          }
          const target = resolve(PLUGIN_DIR, image)
          if (!target.startsWith(PLUGIN_DIR)) fail(`截图路径越出 plugins/dsh/：${image}`)
          else if (!existsSync(target)) fail(`截图文件不存在：${image}`)
        }
        ok(`截图清单有效（${list.length} 张，相对 plugins/dsh/）`)
      }
    } catch (error) {
      fail(`screenshots.json 解析失败：${error.message}`)
    }
  }
}

// ---- 2. DSH 插件清单 -------------------------------------------------------

function checkDshManifest() {
  console.log('\n[2/3] DSH 插件清单（plugins/dsh/package.json）')
  const pkgPath = join(PLUGIN_DIR, 'package.json')
  if (!existsSync(pkgPath)) {
    fail('找不到 plugins/dsh/package.json')
    return null
  }
  let pkg
  try {
    pkg = JSON.parse(readFileSync(pkgPath, 'utf8'))
  } catch (error) {
    fail(`package.json 解析失败：${error.message}`)
    return null
  }

  const bundlePatch = pkg.dsh?.bundle?.patch
  if (!bundlePatch) {
    fail('缺 dsh.bundle.patch —— 只声明 dsh.client 的仓库无法安装，会被精选目录拒收')
  } else if (!existsSync(join(PLUGIN_DIR, bundlePatch))) {
    fail(`dsh.bundle.patch 指向的文件不存在：${bundlePatch}`)
  } else {
    const patch = readFileSync(join(PLUGIN_DIR, bundlePatch), 'utf8')
    if (!/^\s*-\s*insert:/m.test(patch)) fail(`${bundlePatch} 里没有 - insert: 行`)
    if (!patch.includes(pkg.name)) warn(`${bundlePatch} 里没有出现包名 ${pkg.name}，确认 patch 的 name 与包名一致`)
    ok(`dsh.bundle.patch → ${bundlePatch}，文件存在且含 insert 行`)
  }

  if (!pkg.engines?.dsh) warn('缺 engines.dsh，市场无法判断兼容性')
  else {
    ok(`engines.dsh = ${pkg.engines.dsh}`)
    if (!/-[0-9A-Za-z]/.test(pkg.engines.dsh)) {
      warn(`engines.dsh "${pkg.engines.dsh}" 不含预发布比较符：0.2.1-rc.2 这类宿主会被 semver 判为不满足（市场只当作未知，不会隐藏）`)
    }
  }

  const direct = Object.keys(pkg.dependencies || {}).filter((name) => name.startsWith('@deepseek-ai/'))
  if (direct.length > 0) fail(`@deepseek-ai/* 必须放 peerDependencies，不能进 dependencies：${direct.join(', ')}`)
  else ok('@deepseek-ai/* 未出现在 dependencies 里')
  for (const dep of Object.keys(pkg.peerDependencies || {})) {
    if (!dep.startsWith('@deepseek-ai/')) continue
    const range = pkg.peerDependencies[dep]
    if (range === '*') warn(`peer ${dep} 用 "*"，不含预发布比较符（当前宿主 0.2.1-rc.2 属于这种情况）`)
  }
  return pkg
}

// ---- 3. WorkBuddy 技能包 ---------------------------------------------------

function checkSkill(pkg, zipPath) {
  console.log('\n[3/3] WorkBuddy 技能包（SKILL.md + zip）')
  const skillMd = join(SKILL_DIR, 'SKILL.md')
  if (!existsSync(skillMd)) {
    fail('找不到 plugins/workbuddy/xianyu-monitor/SKILL.md')
    return
  }
  const text = readFileSync(skillMd, 'utf8')
  const fields = frontmatter(text)
  if (!fields) {
    fail('SKILL.md 缺少 YAML frontmatter')
    return
  }

  for (const field of SKILL_REQUIRED) {
    if (!fields[field]) fail(`frontmatter 缺必填字段 ${field}`)
  }
  if (fields.name && fields.name !== basename(SKILL_DIR)) {
    fail(`frontmatter name（${fields.name}）必须等于技能目录名（${basename(SKILL_DIR)}）`)
  }
  if (fields.name && !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(fields.name)) {
    fail(`name（${fields.name}）必须是连字符命名：小写字母、数字、单连字符`)
  }
  if (fields.version && pkg && fields.version !== pkg.version) {
    fail(`SKILL.md version（${fields.version}）与 package.json version（${pkg.version}）不一致`)
  }
  if (fields.description && /[<>]/.test(fields.description)) {
    fail('description 不能含 < 或 >（WorkBuddy 校验器会直接拒）')
  }

  // 平台实测约束（2026-11-20 上传被拒的原文）：examples 最多 3 条，且中英数量必须一致
  const exZh = fields.examples_zh
  const exEn = fields.examples_en
  for (const [label, list] of [
    ['examples_zh', exZh],
    ['examples_en', exEn],
  ]) {
    if (Array.isArray(list) && list.length > 3) {
      fail(`${label} 最多 3 条示例（平台会判解析失败），当前 ${list.length} 条`)
    }
    if (Array.isArray(list) && list.some((item) => !item.trim())) {
      fail(`${label} 里有空示例`)
    }
  }
  if (Array.isArray(exZh) && Array.isArray(exEn) && exZh.length !== exEn.length) {
    fail(`examples_zh 与 examples_en 数量必须一致：当前中文 ${exZh.length} 条、英文 ${exEn.length} 条`)
  }
  if (Array.isArray(exZh) !== Array.isArray(exEn)) {
    warn('examples 只写了一种语言：平台要求中英数量一致，建议两边都写或都删')
  }

  if (SKILL_REQUIRED.every((field) => fields[field])) {
    ok(`frontmatter 必填字段齐全，version=${fields.version}`)
  }

  // 正文引用的资源必须真的存在
  for (const match of text.matchAll(/@?(references\/[\w./-]+\.md)/g)) {
    if (!existsSync(join(SKILL_DIR, match[1]))) fail(`SKILL.md 引用了不存在的文件：${match[1]}`)
  }
  for (const match of text.matchAll(/scripts\/[\w./-]+\.py/g)) {
    if (!existsSync(join(SKILL_DIR, match[0]))) fail(`SKILL.md 引用了不存在的脚本：${match[0]}`)
  }

  // zip
  const target = zipPath || join(REPO_ROOT, 'release', 'xianyu-monitor.zip')
  if (!existsSync(target)) {
    warn(`没找到 ${target}，先跑 node scripts/package-workbuddy-skill.mjs`)
    return
  }
  const skillName = basename(SKILL_DIR)
  const zipBuffer = readFileSync(target)
  let entries
  try {
    entries = readZipEntries(zipBuffer)
  } catch (error) {
    fail(`${basename(target)} 读不了：${error.message}`)
    return
  }

  if (entries.length === 0) fail('zip 是空的')
  const outside = entries.filter((entry) => !entry.name.startsWith(`${skillName}/`))
  if (outside.length > 0) {
    fail(`zip 根目录必须是 ${skillName}/，越界条目：${outside.map((entry) => entry.name).join(', ')}`)
  }
  if (!entries.some((entry) => entry.name === `${skillName}/SKILL.md`)) {
    fail(`zip 里缺 ${skillName}/SKILL.md（多套一层目录会被平台判解析失败）`)
  }
  const junk = entries.filter((entry) =>
    /\/(__pycache__)\//.test(`/${entry.name}`) ||
    /\.pyc$/i.test(entry.name) ||
    entry.name.split('/').some((part) => part === '.DS_Store' || part === '.git' || part === 'node_modules'),
  )
  if (junk.length > 0) fail(`zip 里混进了不该上传的文件：${junk.map((entry) => entry.name).join(', ')}`)
  for (const entry of entries) {
    if (entry.name.endsWith('/')) continue
    try {
      const data = readZipEntryData(zipBuffer, entry)
      if (data.length !== entry.size) fail(`${entry.name}: 解压后大小不符`)
      else if (crc32(data) !== entry.crc) fail(`${entry.name}: CRC 校验失败`)
    } catch (error) {
      fail(`zip 条目损坏：${error.message}`)
    }
  }

  const inZip = entries.find((entry) => entry.name === `${skillName}/SKILL.md`)
  if (inZip) {
    try {
      const data = readZipEntryData(zipBuffer, inZip)
      const zipFields = frontmatter(data.toString('utf8'))
      if (!zipFields?.name) fail('zip 里的 SKILL.md 没有 name 字段')
      else if (zipFields.name !== skillName) fail(`zip 里 SKILL.md 的 name（${zipFields.name}）与目录名（${skillName}）不一致`)
      else ok(`${basename(target)}：${entries.length} 个条目，结构 / CRC / frontmatter 全通过`)
    } catch (error) {
      fail(`zip 里的 SKILL.md 读不了：${error.message}`)
    }
  }
}

// ---- 入口 ------------------------------------------------------------------

function main() {
  const argv = process.argv.slice(2)
  const zipIndex = argv.indexOf('--zip')
  const zipPath = zipIndex >= 0 ? resolve(argv[zipIndex + 1]) : null

  console.log('检查上架材料（DSH 精选目录 + WorkBuddy 技能包）')

  checkCatalogEntry()
  const pkg = checkDshManifest()
  checkSkill(pkg, zipPath)

  if (warnings.length > 0) {
    console.log(`\n⚠ ${warnings.length} 条提醒（不阻断）：`)
    for (const item of warnings) console.log(`  - ${item}`)
  }
  if (errors.length > 0) {
    console.error(`\n✗ 上架材料有 ${errors.length} 处不符合格式：`)
    for (const item of errors) console.error(`  - ${item}`)
    process.exit(1)
  }
  console.log('\n✓ 上架材料格式正确')
}

main()
