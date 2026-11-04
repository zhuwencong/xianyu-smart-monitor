#!/usr/bin/env node
/**
 * 把 WorkBuddy 技能目录打包成可上传的 zip（无第三方依赖）。
 *
 * 用法：
 *   node scripts/package-workbuddy-skill.mjs
 *   node scripts/package-workbuddy-skill.mjs --source plugins/workbuddy/xianyu-monitor --out release/xianyu-monitor.zip
 *
 * 产物结构（WorkBuddy 开放平台要求 zip 根目录下就是技能目录）：
 *   xianyu-monitor/SKILL.md
 *   xianyu-monitor/scripts/xy.py
 *   xianyu-monitor/references/*.md
 */
import { deflateRawSync } from 'node:zlib'
import { readdirSync, readFileSync, statSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(HERE, '..')

const SKIP_NAMES = new Set(['__pycache__', '.git', '.DS_Store', 'Thumbs.db', 'node_modules'])
const SKIP_EXT = new Set(['.pyc', '.pyo', '.zip', '.log'])

function parseArgs(argv) {
  const args = {
    source: 'plugins/workbuddy/xianyu-monitor',
    out: 'release/xianyu-monitor.zip',
  }
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i] === '--source') args.source = argv[++i]
    else if (argv[i] === '--out') args.out = argv[++i]
  }
  return args
}

// ---- 极简 zip 写入器 -------------------------------------------------------

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n += 1) {
    let c = n
    for (let k = 0; k < 8; k += 1) {
      c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    }
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buffer) {
  let crc = 0xffffffff
  for (let i = 0; i < buffer.length; i += 1) {
    crc = CRC_TABLE[(crc ^ buffer[i]) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function dosDateTime(date) {
  const time =
    ((date.getHours() & 0x1f) << 11) |
    ((date.getMinutes() & 0x3f) << 5) |
    (Math.floor(date.getSeconds() / 2) & 0x1f)
  const day =
    (((date.getFullYear() - 1980) & 0x7f) << 9) |
    (((date.getMonth() + 1) & 0x0f) << 5) |
    (date.getDate() & 0x1f)
  return { time, day }
}

function buildZip(entries) {
  const chunks = []
  const central = []
  let offset = 0

  for (const entry of entries) {
    const nameBuf = Buffer.from(entry.name, 'utf8')
    const raw = entry.data
    const crc = crc32(raw)
    const deflated = deflateRawSync(raw, { level: 9 })
    const useDeflate = deflated.length < raw.length
    const payload = useDeflate ? deflated : raw
    const method = useDeflate ? 8 : 0
    const { time, day } = dosDateTime(entry.mtime)

    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0x0800, 6) // UTF-8 文件名
    local.writeUInt16LE(method, 8)
    local.writeUInt16LE(time, 10)
    local.writeUInt16LE(day, 12)
    local.writeUInt32LE(crc, 14)
    local.writeUInt32LE(payload.length, 18)
    local.writeUInt32LE(raw.length, 22)
    local.writeUInt16LE(nameBuf.length, 26)
    local.writeUInt16LE(0, 28)

    chunks.push(local, nameBuf, payload)

    const cd = Buffer.alloc(46)
    cd.writeUInt32LE(0x02014b50, 0)
    cd.writeUInt16LE(20, 4)
    cd.writeUInt16LE(20, 6)
    cd.writeUInt16LE(0x0800, 8)
    cd.writeUInt16LE(method, 10)
    cd.writeUInt16LE(time, 12)
    cd.writeUInt16LE(day, 14)
    cd.writeUInt32LE(crc, 16)
    cd.writeUInt32LE(payload.length, 20)
    cd.writeUInt32LE(raw.length, 24)
    cd.writeUInt16LE(nameBuf.length, 28)
    cd.writeUInt16LE(0, 30)
    cd.writeUInt16LE(0, 32)
    cd.writeUInt16LE(0, 34)
    cd.writeUInt16LE(0, 36)
    cd.writeUInt32LE(0, 38)
    cd.writeUInt32LE(offset, 42)
    central.push(cd, nameBuf)

    offset += local.length + nameBuf.length + payload.length
  }

  const centralBuf = Buffer.concat(central)
  const eocd = Buffer.alloc(22)
  eocd.writeUInt32LE(0x06054b50, 0)
  eocd.writeUInt16LE(0, 4)
  eocd.writeUInt16LE(0, 6)
  eocd.writeUInt16LE(entries.length, 8)
  eocd.writeUInt16LE(entries.length, 10)
  eocd.writeUInt32LE(centralBuf.length, 12)
  eocd.writeUInt32LE(offset, 16)
  eocd.writeUInt16LE(0, 20)

  return Buffer.concat([...chunks, centralBuf, eocd])
}

function collectFiles(rootDir, prefix) {
  const entries = []
  const walk = (dir) => {
    for (const name of readdirSync(dir).sort()) {
      if (SKIP_NAMES.has(name)) continue
      const full = join(dir, name)
      const stats = statSync(full)
      if (stats.isDirectory()) {
        walk(full)
        continue
      }
      const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')).toLowerCase() : ''
      if (SKIP_EXT.has(ext)) continue
      entries.push({
        name: `${prefix}/${relative(rootDir, full).split('\\').join('/')}`,
        data: readFileSync(full),
        mtime: stats.mtime,
      })
    }
  }
  walk(rootDir)
  return entries
}

function main() {
  const args = parseArgs(process.argv.slice(2))
  const sourceDir = resolve(REPO_ROOT, args.source)

  if (!existsSync(join(sourceDir, 'SKILL.md'))) {
    console.error(`✗ ${relative(REPO_ROOT, sourceDir)} 下没有 SKILL.md，WorkBuddy 会解析失败。`)
    process.exit(1)
  }

  const skillName = basename(sourceDir)
  const entries = collectFiles(sourceDir, skillName)
  const zip = buildZip(entries)

  const outPath = resolve(REPO_ROOT, args.out)
  mkdirSync(dirname(outPath), { recursive: true })
  writeFileSync(outPath, zip)

  console.log(`✓ 已生成 ${relative(REPO_ROOT, outPath)}（${(zip.length / 1024).toFixed(1)} KiB）`)
  for (const entry of entries) {
    console.log(`  ${entry.name}  (${(entry.data.length / 1024).toFixed(1)} KiB)`)
  }
  console.log('\n下一步：WorkBuddy 开放平台 → 技能 → 添加技能 → 上传该 zip。')
}

main()
