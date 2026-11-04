#!/usr/bin/env node
/**
 * 校验 DSH 插件市场索引是否符合格式要求。
 * 用法：node scripts/validate-market-index.mjs market/index.json
 *
 * 只做结构与取值检查，不联网、不安装任何包。
 */
import { readFileSync } from 'node:fs'

const SEMVER = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/
const HEX40 = /^[0-9a-f]{40}$/

const errors = []

function fail(path, message) {
  errors.push(`${path}: ${message}`)
}

function isLocalizedText(value) {
  if (typeof value === 'string') return value.trim().length > 0
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return typeof value.en === 'string' && value.en.trim().length > 0
}

function checkLocalized(path, value, required) {
  if (value === undefined) {
    if (required) fail(path, '必填')
    return
  }
  if (!isLocalizedText(value)) fail(path, '必须是字符串或以 en 为必填键的本地化对象')
}

function main() {
  const target = process.argv[2]
  if (!target) {
    console.error('用法: node scripts/validate-market-index.mjs <index.json>')
    process.exit(2)
  }

  let index
  try {
    index = JSON.parse(readFileSync(target, 'utf8'))
  } catch (error) {
    console.error(`✗ 无法解析 ${target}: ${error.message}`)
    process.exit(1)
  }

  if (index.format !== 1) fail('format', '必须是 1')
  checkLocalized('title', index.title, true)
  checkLocalized('description', index.description, false)

  const categories = new Set()
  const labels = new Set()
  const sortKeys = new Set()

  if (index.metadata) {
    for (const [id, entry] of Object.entries(index.metadata.categories || {})) {
      categories.add(id)
      checkLocalized(`metadata.categories.${id}.title`, entry && entry.title, true)
    }
    for (const [id, entry] of Object.entries(index.metadata.labels || {})) {
      labels.add(id)
      checkLocalized(`metadata.labels.${id}.title`, entry && entry.title, true)
    }
    for (const [id, entry] of Object.entries(index.metadata.sortKeys || {})) {
      sortKeys.add(id)
      checkLocalized(`metadata.sortKeys.${id}.title`, entry && entry.title, true)
      if (entry && entry.order && !['asc', 'desc'].includes(entry.order)) {
        fail(`metadata.sortKeys.${id}.order`, '只能是 asc 或 desc')
      }
    }
  }

  if (!Array.isArray(index.plugins) || index.plugins.length === 0) {
    fail('plugins', '必须是非空数组')
  }

  const names = new Set()

  for (const [i, plugin] of (index.plugins || []).entries()) {
    const base = `plugins[${i}]`
    if (!plugin || typeof plugin !== 'object') {
      fail(base, '必须是对象')
      continue
    }
    if (typeof plugin.name !== 'string' || !plugin.name.trim()) {
      fail(`${base}.name`, '必填，且为 npm 包名')
    } else if (names.has(plugin.name)) {
      fail(`${base}.name`, `重复的包名 ${plugin.name}`)
    } else {
      names.add(plugin.name)
    }

    checkLocalized(`${base}.title`, plugin.title, false)
    checkLocalized(`${base}.description`, plugin.description, false)

    if (plugin.icon !== undefined) {
      const icon = String(plugin.icon)
      const isInline = icon.startsWith('data:')
      const isRelative = !/^[a-z]+:/i.test(icon)
      const isHttps = /^https:\/\//i.test(icon)
      if (!isInline && !isRelative && !isHttps) {
        fail(`${base}.icon`, '只允许 data: 内联、相对路径或 https: 绝对地址')
      }
    }

    if (plugin.homepage !== undefined && !/^https?:\/\//i.test(String(plugin.homepage))) {
      fail(`${base}.homepage`, '必须是 http(s) 绝对地址')
    }

    const meta = plugin.metadata || {}
    if (meta.category !== undefined && !categories.has(meta.category)) {
      fail(`${base}.metadata.category`, `未在 metadata.categories 中声明：${meta.category}`)
    }
    for (const label of meta.labels || []) {
      if (!labels.has(label)) fail(`${base}.metadata.labels`, `未声明的标签：${label}`)
    }
    for (const key of Object.keys(meta.sortKeys || {})) {
      if (!sortKeys.has(key)) fail(`${base}.metadata.sortKeys`, `未声明的排序键：${key}`)
    }

    if (!Array.isArray(plugin.versions) || plugin.versions.length === 0) {
      fail(`${base}.versions`, '至少需要一个版本')
      continue
    }

    const versions = new Set()
    for (const [j, version] of plugin.versions.entries()) {
      const vbase = `${base}.versions[${j}]`
      if (!version || typeof version !== 'object') {
        fail(vbase, '必须是对象')
        continue
      }
      if (typeof version.version !== 'string' || !SEMVER.test(version.version)) {
        fail(`${vbase}.version`, `不是合法 SemVer：${version.version}`)
      } else if (versions.has(version.version)) {
        fail(`${vbase}.version`, `版本重复：${version.version}`)
      } else {
        versions.add(version.version)
      }

      if (!Number.isInteger(version.publishTimestamp) || version.publishTimestamp <= 0) {
        fail(`${vbase}.publishTimestamp`, '必须是 Unix 秒（正整数）')
      }

      const source = version.source
      if (!source || typeof source !== 'object') {
        fail(`${vbase}.source`, '必填')
      } else if (source.type === 'npm') {
        if (source.registry !== undefined && !/^https:\/\//i.test(String(source.registry))) {
          fail(`${vbase}.source.registry`, '必须是 https 地址')
        }
      } else if (source.type === 'git') {
        if (!/^https:\/\//i.test(String(source.url || ''))) {
          fail(`${vbase}.source.url`, '必须是 https Git 地址')
        }
        if (!HEX40.test(String(source.commit || ''))) {
          fail(`${vbase}.source.commit`, '必须是 40 位十六进制 SHA')
        }
        if (source.path !== undefined && /^[\\/]/.test(String(source.path))) {
          fail(`${vbase}.source.path`, '必须是相对于仓库根目录的相对路径')
        }
      } else {
        fail(`${vbase}.source.type`, '只能是 npm 或 git')
      }

      if (version.engines && version.engines.dsh !== undefined) {
        if (typeof version.engines.dsh !== 'string' || !version.engines.dsh.trim()) {
          fail(`${vbase}.engines.dsh`, '必须是非空字符串（SemVer 范围）')
        }
      }
    }
  }

  if (errors.length > 0) {
    console.error(`✗ ${target} 校验失败（${errors.length} 项）：`)
    for (const message of errors) console.error(`  - ${message}`)
    process.exit(1)
  }

  console.log(`✓ ${target} 格式正确（${(index.plugins || []).length} 个插件）`)
}

main()
