import os
import sys
import datetime
import shutil
import time
from pathlib import Path
from tkinter import filedialog, Tk, simpledialog, Toplevel, ttk, Label, IntVar, Button, messagebox

# 全局变量
file_count = 0
current_count = 0
root_dir = ""
is_canceled = False  # 全局取消标识

# 安全的跨盘符计算相对路径
def safe_relpath(path, start):
    try:
        return os.path.relpath(path, start).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")

# 判断是否是隐藏文件夹 (Windows / Linux 通用)
def is_hidden_or_system(path):
    basename = os.path.basename(path)
    if basename.startswith(".") or basename.lower().startswith("found."):
        return True
    try:
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs != -1 and (attrs & 2 or attrs & 4):  # 2: 隐藏, 4: 系统
            return True
    except Exception:
        pass
    return False

# 转义 HTML 字符
def escape_html(text):
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', '&quot;')
                .replace("'", "&#39;"))

# 文件大小格式化
def human_readable_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 ** 3:
        return f"{size / (1024 ** 2):.2f} MB"
    else:
        return f"{size / (1024 ** 3):.2f} GB"

# 生成安全的 file:// 链接 (自动做 URL 编码)
def safe_file_uri(path):
    try:
        return Path(path).as_uri()
    except Exception:
        return "file:///" + safe_relpath(path, root_dir)

# 获取路径修改时间戳及格式化字符串 (保留小数秒, 保证同秒排序稳定)
def get_mtime_info(path):
    try:
        mtime = os.path.getmtime(path)
        dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        return mtime, dt_str
    except Exception:
        return 0, "未知时间"

# 根据文件后缀获取图标
def get_file_icon(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.ico']:
        return '🖼️'
    elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm']:
        return '🎬'
    elif ext in ['.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a']:
        return '🎵'
    elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.iso']:
        return '📦'
    elif ext in ['.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.md', '.epub']:
        return '📄'
    elif ext in ['.py', '.js', '.html', '.css', '.json', '.cpp', '.c', '.java', '.go', '.rs', '.php']:
        return '💻'
    elif ext in ['.exe', '.msi', '.bat', '.sh', '.cmd', '.apk']:
        return '⚙️'
    return '📄'

# 统计文件总数 (带中断检查; 与生成阶段口径一致, 排除隐藏文件)
def count_files(path, excluded_dirs, check_cancel_func):
    global file_count, root_dir
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(path):
        if check_cancel_func():
            return
        dirnames[:] = [d for d in dirnames if not is_hidden_or_system(os.path.join(dirpath, d))]
        rel = safe_relpath(dirpath, root_dir)
        if any(rel == ex or rel.startswith(ex + "/") for ex in excluded_dirs):
            dirnames[:] = []
            continue
        for f in filenames:
            if not is_hidden_or_system(os.path.join(dirpath, f)):
                file_count += 1

# 生成 HTML 索引 (单次递归遍历: 边统计边生成, 目录大小自底向上累加, 避免 O(N^2))
def generate_html_index(root_dir_arg, excluded_dirs, progress_callback, check_cancel_func):
    global root_dir, current_count, is_canceled
    root_dir = root_dir_arg
    current_count = 0
    is_canceled = False

    stats = {"folders": 0, "files": 0, "bytes": 0}

    def walk_dir(path, is_root=False):
        """返回 (html片段, 该目录总大小); 取消时返回 None"""
        global current_count
        if check_cancel_func():
            return None

        rel = safe_relpath(path, root_dir)
        if any(rel == ex or rel.startswith(ex + "/") for ex in excluded_dirs):
            return "", 0

        try:
            items = sorted(os.listdir(path), key=lambda x: x.lower())
        except Exception:
            items = []

        dirs = [d for d in items if os.path.isdir(os.path.join(path, d)) and not is_hidden_or_system(os.path.join(path, d))]
        files = [f for f in items if os.path.isfile(os.path.join(path, f)) and not is_hidden_or_system(os.path.join(path, f))]

        # 1. 先递归子目录, 取得它们的 HTML 与大小
        child_htmls = []
        sub_size = 0
        for d in dirs:
            if check_cancel_func():
                return None
            res = walk_dir(os.path.join(path, d))
            if res is None:
                return None
            ch, sz = res
            child_htmls.append(ch)
            sub_size += sz

        # 2. 处理本目录下的文件
        file_items = []
        own_size = 0
        for f in files:
            if check_cancel_func():
                return None
            p = os.path.join(path, f)
            ext = os.path.splitext(f)[1].lower()
            try:
                sz_val = os.path.getsize(p)
                sz_str = human_readable_size(sz_val)
            except Exception:
                sz_val = 0
                sz_str = "未知大小"

            mtime_ts, mtime_str = get_mtime_info(p)
            icon = get_file_icon(f)
            uri = safe_file_uri(p)

            file_items.append(
                f"<li data-name='{escape_html(f)}' data-ext='{escape_html(ext)}' data-size='{sz_val}' data-time='{mtime_ts}' data-type='file'>"
                f"<div class='file-row'>"
                f"<span class='item-name' data-name='{escape_html(f)}' data-icon='{icon}' data-href='{escape_html(uri)}'>"
                f"<span class='icon'>{icon}</span><a href='{escape_html(uri)}' target='_blank'>{escape_html(f)}</a>"
                f"</span>"
                f"<span class='item-meta'><span class='item-size'>{sz_str}</span><span class='item-date'>{mtime_str}</span></span>"
                f"</div>"
                f"</li>"
            )
            own_size += sz_val
            current_count += 1
            stats["files"] += 1
            stats["bytes"] += sz_val
            if progress_callback:
                progress_callback(current_count, file_count)

        dir_size = own_size + sub_size
        children_html = "".join(child_htmls)
        files_html = ("<ul>" + "".join(file_items) + "</ul>") if file_items else ""

        if is_root:
            return children_html + files_html, dir_size

        # 3. 组装本目录的 <details> 块 (大小此时已自底向上算好)
        folder_name = os.path.basename(path)
        mtime_ts, mtime_str = get_mtime_info(path)
        size_str = human_readable_size(dir_size)
        stats["folders"] += 1

        head = (
            f"<details data-name='{escape_html(folder_name)}' data-ext='' data-size='{dir_size}' data-time='{mtime_ts}' data-type='dir'>"
            f"<summary>"
            f"<span class='item-name' data-name='{escape_html(folder_name)}' data-icon='📁'>📁 {escape_html(folder_name)}</span>"
            f"<span class='item-meta'><span class='item-size'>{size_str}</span><span class='item-date'>{mtime_str}</span></span>"
            f"</summary>"
        )
        return head + children_html + files_html + "</details>", dir_size

    result = walk_dir(root_dir_arg, is_root=True)
    if result is None or is_canceled:
        return None
    body_html, _ = result

    total_size_str = human_readable_size(stats["bytes"])
    gen_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    head_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        "<title>资源索引</title>",
        "<style>",
        "  * { box-sizing: border-box; }",
        "  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 25px; background: #f8f9fa; color: #333; }",
        "  h1 { font-size: 22px; margin-top: 0; margin-bottom: 15px; color: #1a1a1a; word-break: break-all; }",
        "",
        "  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }",
        "  .stat-card { background: #fff; padding: 12px 16px; border-radius: 8px; border: 1px solid #e9ecef; box-shadow: 0 2px 4px rgba(0,0,0,0.02); display: flex; align-items: center; gap: 12px; }",
        "  .stat-icon { font-size: 22px; width: 42px; height: 42px; background: #f1f3f5; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }",
        "  .stat-info { display: flex; flex-direction: column; overflow: hidden; }",
        "  .stat-value { font-size: 16px; font-weight: 700; color: #1a1a1a; white-space: nowrap; text-overflow: ellipsis; overflow: hidden; }",
        "  .stat-label { font-size: 12px; color: #868e96; margin-top: 2px; }",
        "",
        "  .toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; background: #fff; padding: 12px 15px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.03); margin-bottom: 15px; border: 1px solid #e9ecef; }",
        "  .search-group { display: flex; gap: 8px; flex: 1; min-width: 280px; }",
        "  .search-group input { flex: 1; padding: 8px 12px; font-size: 14px; border: 1px solid #ced4da; border-radius: 6px; outline: none; transition: border-color 0.2s; }",
        "  .search-group input:focus { border-color: #1a73e8; }",
        "  .action-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }",
        "  button, select { padding: 8px 12px; font-size: 14px; border: 1px solid #ced4da; background: #fff; border-radius: 6px; cursor: pointer; transition: all 0.2s; color: #495057; }",
        "  button:hover, select:hover { background: #f1f3f5; border-color: #adb5bd; }",
        "  .sort-label { font-size: 13px; color: #6c757d; margin-left: 5px; }",
        "",
        "  .status-bar { font-size: 13px; color: #495057; margin-bottom: 15px; padding: 0 5px; font-weight: 500; }",
        "  .empty-state { text-align: center; padding: 40px; color: #868e96; font-size: 15px; display: none; }",
        "",
        "  details { margin-left: 18px; margin-bottom: 4px; }",
        "  body > details { margin-left: 0; }",
        "  summary { display: flex; justify-content: space-between; align-items: center; padding: 6px 10px; background: #fff; border-radius: 6px; font-weight: 600; cursor: pointer; user-select: none; border: 1px solid #e9ecef; }",
        "  summary:hover { background: #eef2f7; }",
        "  ul { list-style: none; padding-left: 22px; margin: 4px 0; }",
        "  body > ul { padding-left: 0; }",
        "  li { margin: 2px 0; }",
        "  .file-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 10px; background: #fff; border-radius: 6px; border: 1px solid #f1f3f5; }",
        "  .file-row:hover { background: #eef2f7; }",
        "  .item-name { display: flex; align-items: center; gap: 8px; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }",
        "  .item-name a { color: #1a73e8; text-decoration: none; }",
        "  .item-name a:hover { text-decoration: underline; }",
        "  .item-meta { display: flex; gap: 15px; font-size: 13px; color: #6c757d; font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace; white-space: nowrap; flex-shrink: 0; }",
        "  .item-size { width: 85px; text-align: right; }",
        "  .item-date { width: 130px; text-align: right; }",
        "  mark { background: #ffe066; padding: 0 2px; border-radius: 2px; }",
        "</style>",
        "<script>",
        "let debounceTimer = null;",
        "function onSearchInput() {",
        "  clearTimeout(debounceTimer);",
        "  debounceTimer = setTimeout(() => { filterFiles(); }, 200);",
        "}",
        "function escapeHtml(s) {",
        "  return String(s)",
        "    .replace(/&/g, '&amp;')",
        "    .replace(/</g, '&lt;')",
        "    .replace(/>/g, '&gt;')",
        "    .replace(/'/g, '&#39;');",
        "}",
        "// 在原始文本上做不区分大小写的查找, 每段先转义再插入 <mark>, 杜绝 XSS",
        "function highlight(name, query) {",
        "  if (!query) return escapeHtml(name);",
        "  const lower = name.toLowerCase();",
        "  const q = query.toLowerCase();",
        "  let out = '';",
        "  let i = 0;",
        "  while (i < name.length) {",
        "    const idx = lower.indexOf(q, i);",
        "    if (idx === -1) {",
        "      out += escapeHtml(name.slice(i));",
        "      break;",
        "    }",
        "    out += escapeHtml(name.slice(i, idx));",
        "    out += '<mark>' + escapeHtml(name.slice(idx, idx + q.length)) + '</mark>';",
        "    i = idx + q.length;",
        "  }",
        "  return out;",
        "}",
        "// 依据 data-name / data-icon / data-href 安全重建 .item-name 内容",
        "function renderName(el, query) {",
        "  const name = el.dataset.name || '';",
        "  const icon = el.dataset.icon || '';",
        "  const href = el.dataset.href;",
        "  const nameHtml = highlight(name, query);",
        "  if (href !== undefined && href !== '') {",
        "    el.innerHTML = `<span class='icon'>${escapeHtml(icon)}</span><a href='${escapeHtml(href)}' target='_blank'>${nameHtml}</a>`;",
        "  } else {",
        "    el.innerHTML = `${escapeHtml(icon)} ${nameHtml}`;",
        "  }",
        "}",
        "function clearSearch() {",
        "  document.getElementById('search').value = '';",
        "  filterFiles();",
        "}",
        "function toggleExpandAll(openState) {",
        "  document.querySelectorAll('details').forEach(d => {",
        "    if (d.style.display !== 'none') d.open = openState;",
        "  });",
        "}",
        "",
        "// 判定字符首字符类型优先级：1: 数字 < 2: 英文 < 3: 汉字 < 4: 其他",
        "function getItemType(str) {",
        "  if (!str) return 4;",
        "  const ch = str.trim().charAt(0);",
        "  if (/[0-9]/.test(ch)) return 1;",
        "  if (/[a-zA-Z]/.test(ch)) return 2;",
        "  if (/[\\u4e00-\\u9fa5]/.test(ch)) return 3;",
        "  return 4;",
        "}",
        "",
        "// 自定义文本比较函数，优先保障 数字 -> 英文 -> 中文 顺序",
        "function compareText(a, b, asc) {",
        "  const typeA = getItemType(a);",
        "  const typeB = getItemType(b);",
        "  if (typeA !== typeB) {",
        "    return asc ? typeA - typeB : typeB - typeA;",
        "  }",
        "  const res = a.localeCompare(b, 'zh-Hans-CN', { numeric: true });",
        "  return asc ? res : -res;",
        "}",
        "",
        "function applySort() {",
        "  const key = document.getElementById('sortKey').value;",
        "  const order = document.getElementById('sortOrder').value;",
        "  const asc = order === 'asc';",
        "",
        "  // 文件夹相对文件的摆放顺序:",
        "  // 按类型排序时：文件夹始终固定在最顶端",
        "  // 按名称/时间/大小排序时：升序文件夹在顶端，降序文件夹在末尾",
        "  let folderFirst = (key === 'type') ? true : asc;",
        "",
        "  const containers = document.querySelectorAll('body, details');",
        "  containers.forEach(container => {",
        "    const subDirs = Array.from(container.children).filter(el => el.tagName === 'DETAILS');",
        "    const ul = Array.from(container.children).find(el => el.tagName === 'UL');",
        "",
        "    // 1. 文件夹自身排序",
        "    if (subDirs.length > 0) {",
        "      subDirs.sort((a, b) => {",
        "        let valA, valB;",
        "        if (key === 'time') {",
        "          valA = parseFloat(a.dataset.time || '0');",
        "          valB = parseFloat(b.dataset.time || '0');",
        "          return asc ? valA - valB : valB - valA;",
        "        } else if (key === 'size') {",
        "          valA = parseInt(a.dataset.size || '0', 10);",
        "          valB = parseInt(b.dataset.size || '0', 10);",
        "          return asc ? valA - valB : valB - valA;",
        "        } else {",
        "          valA = (a.dataset.name || '').toLowerCase();",
        "          valB = (b.dataset.name || '').toLowerCase();",
        "          return compareText(valA, valB, asc);",
        "        }",
        "      });",
        "    }",
        "",
        "    // 2. 文件列表自身排序",
        "    if (ul) {",
        "      const lis = Array.from(ul.children).filter(el => el.tagName === 'LI');",
        "      if (lis.length > 1) {",
        "        lis.sort((a, b) => {",
        "          let valA, valB;",
        "          if (key === 'type') {",
        "            valA = (a.dataset.ext || '').toLowerCase();",
        "            valB = (b.dataset.ext || '').toLowerCase();",
        "            if (valA === valB) {",
        "              let nameA = (a.dataset.name || '').toLowerCase();",
        "              let nameB = (b.dataset.name || '').toLowerCase();",
        "              // 同后缀名内部固定保持按文件名升序 (数字 -> 英文 -> 汉字)",
        "              return compareText(nameA, nameB, true);",
        "            }",
        "            return compareText(valA, valB, asc);",
        "          } else if (key === 'time') {",
        "            valA = parseFloat(a.dataset.time || '0');",
        "            valB = parseFloat(b.dataset.time || '0');",
        "            return asc ? valA - valB : valB - valA;",
        "          } else if (key === 'size') {",
        "            valA = parseInt(a.dataset.size || '0', 10);",
        "            valB = parseInt(b.dataset.size || '0', 10);",
        "            return asc ? valA - valB : valB - valA;",
        "          } else {",
        "            valA = (a.dataset.name || '').toLowerCase();",
        "            valB = (b.dataset.name || '').toLowerCase();",
        "            return compareText(valA, valB, asc);",
        "          }",
        "        });",
        "        lis.forEach(li => ul.appendChild(li));",
        "      }",
        "    }",
        "",
        "    // 3. 调整 DOM 放置顺序 (文件夹在前还是文件在前)",
        "    if (folderFirst) {",
        "      subDirs.forEach(d => container.appendChild(d));",
        "      if (ul) container.appendChild(ul);",
        "    } else {",
        "      if (ul) container.appendChild(ul);",
        "      subDirs.forEach(d => container.appendChild(d));",
        "    }",
        "  });",
        "}",
        "function filterFiles() {",
        "  const q = document.getElementById('search').value.trim().toLowerCase();",
        "  const allDetails = Array.from(document.querySelectorAll('details'));",
        "  const allLis = Array.from(document.querySelectorAll('li'));",
        "  const statusBar = document.getElementById('status-bar');",
        "  const emptyState = document.getElementById('empty-state');",
        "",
        "  // 1. 恢复所有元素显示, 并按关键词安全重建名称 (无关键词时复原)",
        "  allDetails.forEach(d => {",
        "    d.open = false;",
        "    d.style.display = '';",
        "    const nameEl = d.querySelector('summary .item-name');",
        "    if (nameEl) renderName(nameEl, q);",
        "  });",
        "  allLis.forEach(li => {",
        "    li.style.display = '';",
        "    const nameEl = li.querySelector('.item-name');",
        "    if (nameEl) renderName(nameEl, q);",
        "  });",
        "",
        "  if (!q) {",
        "    statusBar.textContent = '显示全部内容';",
        "    emptyState.style.display = 'none';",
        "    return;",
        "  }",
        "",
        "  allDetails.forEach(d => d.style.display = 'none');",
        "  allLis.forEach(li => li.style.display = 'none');",
        "",
        "  function showAncestors(el) {",
        "    let p = el.parentElement;",
        "    while (p) {",
        "      if (p.tagName === 'DETAILS') {",
        "        p.style.display = '';",
        "        p.open = true;",
        "      }",
        "      p = p.parentElement;",
        "    }",
        "  }",
        "",
        "  let matchCount = 0;",
        "  allLis.forEach(li => {",
        "    const name = li.dataset.name || '';",
        "    if (name.toLowerCase().includes(q)) {",
        "      li.style.display = '';",
        "      matchCount++;",
        "      showAncestors(li);",
        "    }",
        "  });",
        "  allDetails.forEach(d => {",
        "    const folderName = d.dataset.name || '';",
        "    if (folderName.toLowerCase().includes(q)) {",
        "      d.style.display = '';",
        "      d.open = true;",
        "      showAncestors(d);",
        "      d.querySelectorAll('li').forEach(childLi => childLi.style.display = '');",
        "      d.querySelectorAll('details').forEach(childD => {",
        "        childD.style.display = '';",
        "        childD.open = true;",
        "      });",
        "    }",
        "  });",
        "  if (matchCount > 0) {",
        "    statusBar.textContent = `搜索结果：共匹配到 ${matchCount} 个文件`;",
        "    emptyState.style.display = 'none';",
        "  } else {",
        "    statusBar.textContent = '搜索结果：无匹配项';",
        "    emptyState.style.display = 'block';",
        "  }",
        "}",
        "</script>",
        "</head>",
        "<body>",
        f"<h1>📁 资源目录索引：{escape_html(root_dir)}</h1>",
        "",
        "<div class='stats-grid'>",
        f"  <div class='stat-card'><div class='stat-icon'>📁</div><div class='stat-info'><div class='stat-value'>{stats['folders']:,}</div><div class='stat-label'>文件夹总数</div></div></div>",
        f"  <div class='stat-card'><div class='stat-icon'>📄</div><div class='stat-info'><div class='stat-value'>{stats['files']:,}</div><div class='stat-label'>文件总数</div></div></div>",
        f"  <div class='stat-card'><div class='stat-icon'>💾</div><div class='stat-info'><div class='stat-value'>{total_size_str}</div><div class='stat-label'>总占用空间</div></div></div>",
        f"  <div class='stat-card'><div class='stat-icon'>⏱️</div><div class='stat-info'><div class='stat-value'>{gen_time_str}</div><div class='stat-label'>索引生成时间</div></div></div>",
        "</div>",
        "",
        "<div class='toolbar'>",
        "  <div class='search-group'>",
        "    <input type='text' id='search' placeholder='🔍 实时搜索文件名或文件夹...' oninput='onSearchInput()'>",
        "    <button onclick='clearSearch()'>清空</button>",
        "  </div>",
        "  <div class='action-group'>",
        "    <button onclick='toggleExpandAll(true)'>📂 全部展开</button>",
        "    <button onclick='toggleExpandAll(false)'>📁 全部折叠</button>",
        "    <span class='sort-label'>排序:</span>",
        "    <select id='sortKey' onchange='applySort()'>",
        "      <option value='name'>按名称</option>",
        "      <option value='type'>按文件类型</option>",
        "      <option value='time'>按修改时间</option>",
        "      <option value='size'>按大小</option>",
        "    </select>",
        "    <select id='sortOrder' onchange='applySort()'>",
        "      <option value='asc'>升序 ⬆️</option>",
        "      <option value='desc'>降序 ⬇️</option>",
        "    </select>",
        "  </div>",
        "</div>",
        "<div id='status-bar' class='status-bar'>显示全部内容</div>",
        "<div id='empty-state' class='empty-state'>🔍 未找到与关键词匹配的文件或文件夹</div>",
    ]

    html_parts = head_parts + [body_html, "</body>", "</html>"]
    return "\n".join(html_parts)

# 主程序入口
def main():
    global root_dir, is_canceled
    root = Tk()
    root.withdraw()

    # 1. 选择目录
    folder = filedialog.askdirectory(title="请选择要索引的目录")
    if not folder:
        root.destroy()
        return

    root_dir = folder

    # 2. 默认排除清单
    default_ex = ["$RECYCLE.BIN", "System Volume Information", "found.000"]
    ei = simpledialog.askstring("排除子目录(可选)",
        "默认排除：隐藏文件夹、$RECYCLE.BIN、System Volume Information 等\n如有额外要排除的请输入，每行一个：",
        initialvalue=""
    )
    extra = [e.strip().replace("\\", "/") for e in (ei.splitlines() if ei else []) if e.strip()]
    excl = default_ex + extra

    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # 3. 进度与控制窗口
    pw = Toplevel(root)
    pw.title("生成索引")

    is_canceled = False

    def on_user_cancel():
        global is_canceled
        is_canceled = True

    pw.protocol("WM_DELETE_WINDOW", on_user_cancel)

    lbl = Label(pw, text="正在扫描统计文件...")
    lbl.pack(padx=20, pady=(15, 5))

    var = IntVar()
    pb = ttk.Progressbar(pw, maximum=100, variable=var, length=300)
    pb.pack(padx=20, pady=5)

    cancel_btn = Button(pw, text="取消生成", command=on_user_cancel, width=12)
    cancel_btn.pack(padx=20, pady=(5, 15))

    pw.update()

    # UI 刷新节流: 避免每个文件都刷新一次 GUI 造成卡顿
    last_pump = 0.0
    last_progress = 0.0

    def pump():
        nonlocal last_pump
        now = time.time()
        if now - last_pump >= 0.05:
            last_pump = now
            try:
                pw.update()
            except Exception:
                on_user_cancel()

    def check_cancel():
        pump()
        return is_canceled

    def update_progress(done, total):
        nonlocal last_progress
        if is_canceled:
            return
        now = time.time()
        if total <= 0 or done == total or now - last_progress >= 0.05:
            last_progress = now
            if total > 0:
                var.set(int(done / total * 100))
            lbl.config(text=f"正在生成索引... {done}/{total} 文件")
        pump()

    count_files(folder, excl, check_cancel)
    if is_canceled:
        root.destroy()
        return

    html = generate_html_index(folder, excl, update_progress, check_cancel)
    if is_canceled or not html:
        root.destroy()
        return

    try:
        pw.destroy()
    except Exception:
        pass

    # 4. 写入文件与备份
    out = os.path.join(folder, f"index_{now}.html")
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    messagebox.showinfo("完成", f"索引文件已生成：\n{out}")

    bdir = filedialog.askdirectory(title="选择备份目录(可选)", initialdir=folder)
    if bdir:
        safe_path = folder.replace(":", "").replace("\\", "-").replace("/", "-")
        if len(safe_path) > 120:  # 防止备份文件名过长 (Windows 路径限制)
            safe_path = safe_path[:120]
        bfn = f"index_backup_{safe_path}_{now}.html"
        bpath = os.path.join(bdir, bfn)
        shutil.copyfile(out, bpath)
        messagebox.showinfo("备份完成", f"已备份至：\n{bpath}")

    root.destroy()

if __name__ == '__main__':
    main()
