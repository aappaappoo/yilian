"""
Soulmeet 记忆查看器 — 临时调试工具

启动: python scripts/memory_viewer.py
访问: http://localhost:8765

功能:
- 查询指定 audiences 的摘要和事件
- 展示实际的 user_id、speaker_id、audiences 查询参数
- 完整展示 contents（不截断），方便排查数据格式问题
"""

from __future__ import annotations
import asyncio
import json
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

# 复用项目已有的组件
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.conversation.models import init_db
from core.conversation.sql_store import SQLStore

app = FastAPI(title="Soulmeet Memory Viewer")
sql_store: Optional[SQLStore] = None


# ── API 路由 ──

@app.on_event("startup")
async def startup():
    global sql_store
    if not settings.context_sql_url:
        print("❌ 未配置 CONTEXT_SQL_URL，无法连接数据库")
        return
    session_factory = await init_db(db_url=settings.context_sql_url)
    sql_store = SQLStore(session_factory)
    print(f"✅ 数据库已连接: {settings.context_sql_url[:50]}...")


@app.get("/api/query")
async def query_memory(
    audiences: str = Query(default="Liyin", description="人群标识"),
    user_id: str = Query(default="", description="用户 ID"),
    speaker_id: str = Query(default="", description="说话者 ID"),
    summary_limit: int = Query(default=5, description="摘要条数"),
    events_limit: int = Query(default=20, description="事件条数"),
):
    """查询摘要和事件，返回完整数据（不截断）"""
    if sql_store is None:
        return {"error": "数据库未连接"}

    # 查询摘要
    summaries = await sql_store.get_summaries(audiences, limit=summary_limit)

    # 查询事件（复用 get_events 的完整逻辑）
    events = await sql_store.get_events(
        audiences,
        user_id=user_id,
        speaker_id=speaker_id,
        limit=events_limit,
    )

    # 解析 contents：如果是 JSON 三元组就格式化，否则原样返回
    def parse_contents(raw: str) -> dict:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {"type": "triplet", "parsed": data, "raw": raw}
        except (json.JSONDecodeError, TypeError):
            pass
        return {"type": "text", "parsed": None, "raw": raw}

    return {
        "query_params": {
            "audiences": audiences,
            "user_id": user_id or "(空)",
            "speaker_id": speaker_id or "(空)",
            "summary_limit": summary_limit,
            "events_limit": events_limit,
        },
        "summaries": [
            {
                "id": s.get("id"),
                "contents": parse_contents(s.get("contents", "")),
                "create_time": s.get("create_time"),
                "speaker_id": s.get("speaker_id"),
                "user_id": s.get("user_id"),
            }
            for s in summaries
        ],
        "events": [
            {
                "id": e.get("id"),
                "content_type": e.get("content_type"),
                "contents": parse_contents(e.get("contents", "")),
                "importance": e.get("importance"),
                "speaker_id": e.get("speaker_id"),
                "user_id": e.get("user_id"),
                "create_time": e.get("create_time"),
                "updated_at": e.get("updated_at"),
            }
            for e in events
        ],
        "counts": {
            "summaries": len(summaries),
            "events": len(events),
        },
    }


@app.get("/api/speaker_memories")
async def query_speaker_memories(
    speaker_id: str = Query(default="yxx", description="说话者 ID"),
    user_id: str = Query(default="", description="用户 ID"),
    status: str = Query(default="valid", description="记录状态"),
    limit: int = Query(default=50, description="最大条数"),
):
    """查询指定身份的所有记忆记录"""
    if sql_store is None:
        return {"error": "数据库未连接"}

    memories = await sql_store.get_speaker_memories(
        speaker_id=speaker_id,
        status=status,
        limit=limit,
        user_id=user_id,
    )
    return {
        "query_params": {
            "speaker_id": speaker_id,
            "user_id": user_id or "(空)",
            "status": status,
            "limit": limit,
        },
        "memories": memories,
        "count": len(memories),
    }


# ── 前端页面 ──

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Soulmeet 记忆查看器</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }
h1 { color: #38bdf8; margin-bottom: 20px; font-size: 1.5rem; }
h2 { color: #94a3b8; font-size: 1.1rem; margin: 16px 0 8px; }

.controls { background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }
.field input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 6px 10px; border-radius: 4px; font-size: 0.9rem; width: 200px; }
.field input:focus { outline: none; border-color: #38bdf8; }
button { background: #2563eb; color: white; border: none; padding: 8px 20px; border-radius: 4px; cursor: pointer; font-size: 0.9rem; height: 34px; }
button:hover { background: #1d4ed8; }
button.secondary { background: #475569; }
button.secondary:hover { background: #64748b; }

.query-info { background: #1e293b; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; font-size: 0.85rem; font-family: monospace; }
.query-info span { color: #38bdf8; }

.section { margin-bottom: 24px; }
.card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.badge { font-size: 0.7rem; padding: 2px 8px; border-radius: 10px; }
.badge-triplet { background: #7c3aed; color: white; }
.badge-text { background: #0d9488; color: white; }
.badge-importance { background: #f59e0b; color: #1e293b; font-weight: bold; }

.meta { font-size: 0.75rem; color: #64748b; margin-top: 6px; }
.meta span { margin-right: 12px; }

.contents-raw { background: #0f172a; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; word-break: break-all; margin-top: 6px; max-height: 300px; overflow-y: auto; }
.triplet-view { display: flex; gap: 8px; align-items: center; font-size: 0.95rem; margin: 8px 0; }
.triplet-view .subject { color: #38bdf8; font-weight: bold; }
.triplet-view .relation { color: #a78bfa; }
.triplet-view .object { color: #34d399; }
.triplet-view .arrow { color: #64748b; }

.empty { color: #64748b; font-style: italic; padding: 20px; text-align: center; }
.count { color: #64748b; font-size: 0.85rem; }
.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tab { padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 0.85rem; border: 1px solid #334155; background: transparent; color: #94a3b8; }
.tab.active { background: #2563eb; color: white; border-color: #2563eb; }
#loading { display: none; color: #f59e0b; margin-left: 12px; }
</style>
</head>
<body>

<h1>🧠 Soulmeet 记忆查看器</h1>

<div class="controls">
  <div class="field">
    <label>Audiences</label>
    <input id="audiences" value="Liyin" />
  </div>
  <div class="field">
    <label>User ID</label>
    <input id="user_id" placeholder="留空测试未登录查询" />
  </div>
  <div class="field">
    <label>Speaker ID</label>
    <input id="speaker_id" value="yxx" />
  </div>
  <div class="field">
    <label>摘要条数</label>
    <input id="summary_limit" type="number" value="5" style="width:80px" />
  </div>
  <div class="field">
    <label>事件条数</label>
    <input id="events_limit" type="number" value="20" style="width:80px" />
  </div>
  <button onclick="queryMemory()">🔍 查询</button>
  <button class="secondary" onclick="querySpeaker()">👤 Speaker 全量</button>
  <span id="loading">查询中...</span>
</div>

<div id="query-info" class="query-info" style="display:none"></div>

<div class="tabs">
  <div class="tab active" data-tab="events" onclick="switchTab('events')">📌 事件</div>
  <div class="tab" data-tab="summaries" onclick="switchTab('summaries')">📝 摘要</div>
  <div class="tab" data-tab="all" onclick="switchTab('all')">📋 Speaker 全量</div>
</div>

<div id="content"></div>

<script>
let currentData = {};
let currentTab = 'events';

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  render();
}

function val(id) { return document.getElementById(id).value.trim(); }

async function queryMemory() {
  const loading = document.getElementById('loading');
  loading.style.display = 'inline';
  try {
    const params = new URLSearchParams({
      audiences: val('audiences'),
      user_id: val('user_id'),
      speaker_id: val('speaker_id'),
      summary_limit: val('summary_limit'),
      events_limit: val('events_limit'),
    });
    const resp = await fetch('/api/query?' + params);
    const data = await resp.json();
    currentData.summaries = data.summaries;
    currentData.events = data.events;
    showQueryInfo(data.query_params, data.counts);
    render();
  } catch (e) {
    document.getElementById('content').innerHTML = '<div class="empty">❌ 查询失败: ' + e.message + '</div>';
  }
  loading.style.display = 'none';
}

async function querySpeaker() {
  const loading = document.getElementById('loading');
  loading.style.display = 'inline';
  try {
    const params = new URLSearchParams({
      speaker_id: val('speaker_id'),
      user_id: val('user_id'),
      limit: '100',
    });
    const resp = await fetch('/api/speaker_memories?' + params);
    const data = await resp.json();
    currentData.all = data.memories;
    showQueryInfo(data.query_params, { all: data.count });
    switchTab('all');
  } catch (e) {
    document.getElementById('content').innerHTML = '<div class="empty">❌ 查询失败: ' + e.message + '</div>';
  }
  loading.style.display = 'none';
}

function showQueryInfo(params, counts) {
  const el = document.getElementById('query-info');
  el.style.display = 'block';
  el.innerHTML = 'SQL 查询参数: ' + Object.entries(params).map(
    ([k, v]) => `<span>${k}</span>=${v}`
  ).join(', ') + ' | 结果: ' + Object.entries(counts).map(
    ([k, v]) => `<span>${k}</span>=${v}条`
  ).join(', ');
}

function renderContents(c) {
  if (!c) return '<span class="empty">空</span>';
  let html = '';
  if (c.type === 'triplet' && c.parsed) {
    const p = c.parsed;
    const obj = Array.isArray(p.object) ? p.object.join('、') : (p.object || '');
    html += `<div class="triplet-view">
      <span class="subject">${p.subject || '?'}</span>
      <span class="arrow">→</span>
      <span class="relation">${p.relation || '?'}</span>
      <span class="arrow">→</span>
      <span class="object">${obj}</span>
    </div>`;
    html += `<span class="badge badge-triplet">三元组 JSON</span>`;
  } else {
    html += `<span class="badge badge-text">自然语言</span>`;
  }
  html += `<div class="contents-raw">${escHtml(c.raw)}</div>`;
  return html;
}

function escHtml(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderEvent(e) {
  return `<div class="card">
    <div class="card-header">
      <span>[${escHtml(e.content_type || '未分类')}]</span>
      <span>
        <span class="badge badge-importance">重要度: ${e.importance ?? '?'}</span>
        ID: ${e.id ?? '?'}
      </span>
    </div>
    ${renderContents(e.contents)}
    <div class="meta">
      <span>🔑 user_id: ${escHtml(e.user_id || '(NULL)')}</span>
      <span>🎤 speaker: ${escHtml(e.speaker_id || '?')}</span>
      <span>📅 ${e.create_time || ''}</span>
      <span>🔄 ${e.updated_at || ''}</span>
    </div>
  </div>`;
}

function renderSummary(s) {
  return `<div class="card">
    <div class="card-header">
      <span>📝 对话摘要</span>
      <span>ID: ${s.id ?? '?'}</span>
    </div>
    <div class="contents-raw">${escHtml(s.contents?.raw || '')}</div>
    <div class="meta">
      <span>🔑 user_id: ${escHtml(s.user_id || '(NULL)')}</span>
      <span>🎤 speaker: ${escHtml(s.speaker_id || '?')}</span>
      <span>📅 ${s.create_time || ''}</span>
    </div>
  </div>`;
}

function renderAllMemory(m) {
  return `<div class="card">
    <div class="card-header">
      <span>[${escHtml(m.msg_type || '?')} / ${escHtml(m.content_type || '?')}]</span>
      <span>
        <span class="badge badge-importance">重要度: ${m.importance ?? '?'}</span>
        ID: ${m.id ?? '?'} | ${m.status || '?'}
      </span>
    </div>
    <div class="contents-raw">${escHtml(m.contents || '')}</div>
    <div class="meta">
      <span>🔑 user_id: ${escHtml(m.user_id || '(NULL)')}</span>
      <span>🎤 speaker: ${escHtml(m.speaker_id || '?')}</span>
      <span>🌐 audiences: ${escHtml(m.audiences || '?')}</span>
      <span>📅 ${m.create_time || ''}</span>
      <span>🔄 ${m.updated_at || ''}</span>
    </div>
  </div>`;
}

function render() {
  const el = document.getElementById('content');
  let html = '';

  if (currentTab === 'events') {
    const events = currentData.events || [];
    html += `<h2>📌 事件记忆 <span class="count">(${events.length}条)</span></h2>`;
    if (events.length === 0) html += '<div class="empty">无事件数据（检查 user_id / speaker_id 是否正确）</div>';
    else events.forEach(e => html += renderEvent(e));
  }
  else if (currentTab === 'summaries') {
    const summaries = currentData.summaries || [];
    html += `<h2>📝 摘要 <span class="count">(${summaries.length}条)</span></h2>`;
    if (summaries.length === 0) html += '<div class="empty">无摘要数据</div>';
    else summaries.forEach(s => html += renderSummary(s));
  }
  else if (currentTab === 'all') {
    const all = currentData.all || [];
    html += `<h2>📋 Speaker 全量记忆 <span class="count">(${all.length}条)</span></h2>`;
    if (all.length === 0) html += '<div class="empty">无数据</div>';
    else all.forEach(m => html += renderAllMemory(m));
  }

  el.innerHTML = html;
}

// 页面加载后自动查询一次
window.addEventListener('load', () => queryMemory());
</script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
