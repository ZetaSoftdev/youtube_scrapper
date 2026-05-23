// ─── State ──────────────────────────────────────────────────────────────────
const state = {
  topics: [],
  activeTopic: null,
  channels: [],
  selectedChannelData: null,   // channel being configured before adding
  selectedSort: "date",
};

// ─── Init ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  checkStatus();
  loadTopics();
});

// ─── API Helper ──────────────────────────────────────────────────────────────
const BASE_PATH = window.location.pathname.replace(/\/$/, '');

async function api(method, path, body = null) {
  const fullPath = BASE_PATH + path;
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(fullPath, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ─── Status ──────────────────────────────────────────────────────────────────
async function checkStatus() {
  const el = document.getElementById("nlmStatus");
  try {
    const data = await api("GET", "/api/status");
    if (data.nlm_available) {
      el.className = "nlm-status connected";
      el.querySelector(".status-label").textContent = "NLM ✓";
    } else {
      el.className = "nlm-status error";
      el.querySelector(".status-label").textContent = "NLM offline";
    }
  } catch {
    el.className = "nlm-status error";
    el.querySelector(".status-label").textContent = "Error";
  }
}

// ─── Views ───────────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById("view" + name.charAt(0).toUpperCase() + name.slice(1)).classList.add("active");
  document.getElementById("nav" + name.charAt(0).toUpperCase() + name.slice(1)).classList.add("active");
  if (name === "activity") loadActivity();
}

// ─── Topics ──────────────────────────────────────────────────────────────────
async function loadTopics() {
  try {
    state.topics = await api("GET", "/api/topics");
    renderTopicsList();
    if (!state.activeTopic && state.topics.length > 0) {
      selectTopic(state.topics[0]);
    }
  } catch (e) {
    toast("Failed to load topics", "error");
  }
}

function renderTopicsList() {
  const el = document.getElementById("topicsList");
  if (state.topics.length === 0) {
    el.innerHTML = `<div style="padding:12px 12px;font-size:12px;color:var(--text3)">No topics yet</div>`;
    return;
  }
  el.innerHTML = state.topics.map(t => `
    <div class="topic-item ${state.activeTopic?.id === t.id ? "active" : ""}"
         onclick="selectTopic(${JSON.stringify(t).replace(/"/g, "&quot;")})"
         id="topicItem_${t.id}">
      <span class="topic-item-name">${esc(t.name)}</span>
      <span class="topic-item-count">${t.channel_count ?? 0}</span>
    </div>
  `).join("");
}

async function selectTopic(topic) {
  state.activeTopic = topic;
  renderTopicsList();
  showView("dashboard");
  document.getElementById("emptyState").style.display = "none";
  document.getElementById("topicDashboard").style.display = "block";
  document.getElementById("topicTitle").textContent = topic.name;
  await loadChannels();
}

// ─── Create Topic ─────────────────────────────────────────────────────────────
function openTopicModal() {
  document.getElementById("topicName").value = "";
  document.getElementById("topicDesc").value = "";
  document.getElementById("topicModal").classList.add("open");
  setTimeout(() => document.getElementById("topicName").focus(), 50);
}

async function createTopic() {
  const name = document.getElementById("topicName").value.trim();
  if (!name) { toast("Please enter a topic name", "error"); return; }

  const btn = document.getElementById("btnCreateTopic");
  btn.disabled = true; btn.textContent = "Creating...";

  try {
    const topic = await api("POST", "/api/topics", {
      name,
      description: document.getElementById("topicDesc").value.trim()
    });
    closeModal("topicModal");
    toast(`Topic "${name}" created & NotebookLM notebook linked!`, "success");
    await loadTopics();
    selectTopic(topic);
  } catch (e) {
    toast("Failed to create topic: " + e.message, "error");
  } finally {
    btn.disabled = false; btn.textContent = "Create Topic";
  }
}

async function deleteTopic() {
  if (!state.activeTopic) return;
  if (!confirm(`Delete topic "${state.activeTopic.name}"? This will also delete all tracked channels.`)) return;
  try {
    await api("DELETE", `/api/topics/${state.activeTopic.id}`);
    state.activeTopic = null;
    state.channels = [];
    document.getElementById("topicDashboard").style.display = "none";
    document.getElementById("emptyState").style.display = "flex";
    toast("Topic deleted", "info");
    await loadTopics();
  } catch (e) {
    toast("Failed to delete topic", "error");
  }
}

// ─── Channels ─────────────────────────────────────────────────────────────────
async function loadChannels() {
  if (!state.activeTopic) return;
  try {
    state.channels = await api("GET", `/api/topics/${state.activeTopic.id}/channels`);
    renderChannels();
    updateTopicMeta();
  } catch (e) {
    toast("Failed to load channels", "error");
  }
}

function updateTopicMeta() {
  const ch = state.channels.length;
  const nb = state.activeTopic?.notebook_id ? "NotebookLM linked ✓" : "NotebookLM not linked";
  document.getElementById("topicMeta").textContent = `${ch} channel${ch !== 1 ? "s" : ""} · ${nb}`;
}

function renderChannels() {
  const grid = document.getElementById("channelsGrid");
  if (state.channels.length === 0) {
    grid.innerHTML = `<div class="no-channels"><p>No channels yet.<br/>Click <strong>+ Add Channel</strong> to start tracking.</p></div>`;
    return;
  }
  grid.innerHTML = state.channels.map(c => `
    <div class="channel-card" id="channelCard_${c.id}" style="cursor:pointer" onclick="openConfigPanel(${JSON.stringify(c).replace(/"/g, "&quot;")})">
      <div class="channel-card-top">
        <img class="channel-thumb" src="${c.thumbnail_url || ''}" alt=""
             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22><rect width=%2240%22 height=%2240%22 fill=%22%23333%22/><text x=%2250%%22 y=%2255%%22 text-anchor=%22middle%22 fill=%22%23888%22 font-size=%2218%22>▶</text></svg>'" />
        <div class="channel-info">
          <div class="channel-name">${esc(c.channel_name)}</div>
          <div class="channel-subs">${formatNum(c.subscriber_count)} subscribers</div>
        </div>
      </div>
      <div class="channel-badges">
        <span class="badge ${c.sort_by === "date" ? "badge-date" : "badge-views"}">
          ${c.sort_by === "date" ? "🕐 Recent" : "🔥 Popular"}
        </span>
        <span class="badge badge-date">${c.video_fetch_count} videos</span>
        <span class="badge ${c.webhook_subscribed ? "badge-webhook" : "badge-rss"}">
          ${c.webhook_subscribed ? "⚡ Live" : "⏱ RSS"}
        </span>
      </div>
      <div class="channel-card-actions">
        <button class="btn-remove-sm" onclick="event.stopPropagation(); removeChannel(${c.id}, '${esc(c.channel_name)}')">✕ Remove</button>
      </div>
    </div>
  `).join("");
}

async function removeChannel(channelDbId, name) {
  if (!confirm(`Remove "${name}" from tracking?`)) return;
  try {
    await api("DELETE", `/api/channels/${channelDbId}`);
    toast(`"${name}" removed`, "info");
    await loadChannels();
  } catch (e) {
    toast("Failed to remove channel", "error");
  }
}

async function openFetchDialog(channelDbId, name) {
  const count = parseInt(prompt(`How many videos to fetch from "${name}"? (1-50)`, "10"));
  if (!count || count < 1 || count > 50) return;
  const sort = prompt("Sort by: 'date' (recent) or 'viewCount' (popular)?", "date");
  if (!sort) return;

  toast(`Fetching ${count} videos from "${name}"...`, "info");
  try {
    const result = await api("POST", `/api/channels/${channelDbId}/fetch`, {
      count, sort_by: sort.includes("view") ? "viewCount" : "date"
    });
    toast(`Done! ${result.pushed} pushed to NotebookLM, ${result.skipped} already existed.`, "success");
    await loadChannels();
  } catch (e) {
    toast("Fetch failed: " + e.message, "error");
  }
}

// ─── Search Panel ─────────────────────────────────────────────────────────────
function openSearchPanel() {
  document.getElementById("searchPanelBackdrop").classList.add("open");
  document.getElementById("searchPanel").classList.add("open");
  setTimeout(() => document.getElementById("channelSearchInput").focus(), 300);
}

function closeSearchPanel() {
  document.getElementById("searchPanelBackdrop").classList.remove("open");
  document.getElementById("searchPanel").classList.remove("open");
  document.getElementById("searchResults").innerHTML = "";
  document.getElementById("suggestionsSection").style.display = "none";
}

function switchTab(tab) {
  document.getElementById("tabSearch").classList.toggle("active", tab === "search");
  document.getElementById("tabUrl").classList.toggle("active", tab === "url");
  document.getElementById("tabSearchContent").style.display = tab === "search" ? "" : "none";
  document.getElementById("tabUrlContent").style.display = tab === "url" ? "" : "none";
}

async function searchChannels() {
  const q = document.getElementById("channelSearchInput").value.trim();
  if (!q) { toast("Enter a search keyword", "error"); return; }

  const minSubs = parseInt(document.getElementById("minSubsFilter").value) || 0;
  const maxResults = parseInt(document.getElementById("maxResultsFilter").value) || 8;
  const resultsEl = document.getElementById("searchResults");
  const btn = document.getElementById("btnSearch");

  btn.disabled = true; btn.textContent = "Searching...";
  resultsEl.innerHTML = `<div class="search-loading"><div class="loading-spinner"></div></div>`;

  try {
    const results = await api("GET", `/api/channels/search?q=${encodeURIComponent(q)}&min_subscribers=${minSubs}&max_results=${maxResults}`);
    renderSearchResults(results, resultsEl);
  } catch (e) {
    resultsEl.innerHTML = `<div class="search-empty">Search failed: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Search";
  }
}

function renderSearchResults(results, container) {
  const existingIds = state.channels.map(c => c.channel_id);
  if (!results.length) {
    container.innerHTML = `<div class="search-empty">No channels found. Try different keywords.</div>`;
    return;
  }
  container.innerHTML = results.map(ch => {
    const isAdded = existingIds.includes(ch.channel_id);
    return `
      <div class="channel-result ${isAdded ? "added" : ""}" id="result_${ch.channel_id}">
        <img class="result-thumb" src="${ch.thumbnail_url}" alt="" onerror="this.style.background='#333'" />
        <div class="result-body">
          <div class="result-name">${esc(ch.channel_name)}</div>
          <div class="result-subs">${formatNum(ch.subscriber_count)} subscribers · ${formatNum(ch.view_count)} views</div>
          <div class="result-why">✦ ${esc(ch.why_suggested)}</div>
        </div>
        ${isAdded
          ? `<span class="result-add added-btn">✓ Added</span>`
          : `<button class="result-add" onclick="openFetchPreview(${JSON.stringify(ch).replace(/"/g, "&quot;")}, true)">Select Videos...</button>`
        }
      </div>
    `;
  }).join("");
}

async function resolveChannelUrl() {
  const url = document.getElementById("channelUrlInput").value.trim();
  if (!url) return;
  const btn = document.getElementById("btnResolve");
  btn.disabled = true; btn.textContent = "Resolving...";
  const resultEl = document.getElementById("urlResult");
  resultEl.innerHTML = `<div class="search-loading"><div class="loading-spinner"></div></div>`;

  try {
    const ch = await api("GET", `/api/channels/resolve?url=${encodeURIComponent(url)}`);
    renderSearchResults([ch], resultEl);
  } catch (e) {
    resultEl.innerHTML = `<div class="search-empty">Could not find channel: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Resolve";
  }
}

// ─── Config Panel (channel add settings) ─────────────────────────────────────
function openConfigPanel(channelData) {
  state.selectedChannelData = channelData;
  state.selectedSort = "date";

  document.getElementById("configThumb").src = channelData.thumbnail_url || "";
  document.getElementById("configChannelName").textContent = channelData.channel_name;
  document.getElementById("configSubscribers").textContent = `${formatNum(channelData.subscriber_count)} subscribers`;

  const slider = document.getElementById("videoCountSlider");
  slider.value = 10;
  updateSliderValue(10);

  document.getElementById("sortDate").classList.add("active");
  document.getElementById("sortViews").classList.remove("active");

  document.getElementById("configPanelBackdrop").classList.add("open");
  document.getElementById("configPanel").classList.add("open");
}

function closeConfigPanel() {
  document.getElementById("configPanelBackdrop").classList.remove("open");
  document.getElementById("configPanel").classList.remove("open");
}

function updateSliderValue(val) {
  document.getElementById("sliderValueDisplay").textContent = val;
  document.getElementById("previewCount").textContent = val;
}

function selectSort(sort) {
  state.selectedSort = sort;
  document.getElementById("sortDate").classList.toggle("active", sort === "date");
  document.getElementById("sortViews").classList.toggle("active", sort === "viewCount");
  document.getElementById("previewSort").textContent = sort === "date" ? "recently uploaded" : "most popular";
}

async function confirmAddChannel() {
  if (!state.selectedChannelData || !state.activeTopic) return;

  const count = parseInt(document.getElementById("videoCountSlider").value);
  const ch = state.selectedChannelData;

  const btn = document.getElementById("btnConfirmAdd");
  btn.disabled = true;
  document.getElementById("btnConfirmText").textContent = "Adding...";

  try {
    const result = await api("POST", "/api/channels", {
      topic_id: state.activeTopic.id,
      channel_id: ch.channel_id,
      channel_name: ch.channel_name,
      thumbnail_url: ch.thumbnail_url || "",
      subscriber_count: ch.subscriber_count || 0,
      video_fetch_count: count,
      sort_by: state.selectedSort,
    });

    closeConfigPanel();

    const pushed = result.videos_pushed ?? 0;
    toast(`"${ch.channel_name}" added! ${pushed} videos pushed to NotebookLM.`, "success");

    await loadChannels();
    await loadTopics();

    // Load similar channel suggestions
    loadSuggestions(ch.channel_id);

  } catch (e) {
    toast("Failed to add channel: " + e.message, "error");
  } finally {
    btn.disabled = false;
    document.getElementById("btnConfirmText").textContent = "Add Channel & Fetch";
  }
}

async function loadSuggestions(channelId) {
  if (!state.activeTopic) return;
  try {
    const suggestions = await api("GET", `/api/channels/suggest?channel_id=${channelId}&topic_id=${state.activeTopic.id}`);
    if (!suggestions.length) return;
    const section = document.getElementById("suggestionsSection");
    const list = document.getElementById("suggestionsList");
    renderSearchResults(suggestions, list);
    section.style.display = "block";
  } catch { /* silent */ }
}

// ─── Activity Log ─────────────────────────────────────────────────────────────
async function loadActivity() {
  const el = document.getElementById("activityList");
  el.innerHTML = `<div class="loading-spinner"></div>`;
  try {
    const items = await api("GET", "/api/activity?limit=100");
    if (!items.length) {
      el.innerHTML = `<div style="text-align:center;padding:60px;color:var(--text3)">No activity yet.<br/>Add channels to start tracking.</div>`;
      return;
    }
    el.innerHTML = items.map(item => `
      <div class="activity-item">
        <div class="activity-status ${item.status}"></div>
        <div class="activity-item-body">
          <div class="activity-title">${esc(item.video_title || "Untitled video")}</div>
          <div class="activity-meta">
            ${esc(item.channel_name || "")} · ${esc(item.topic_name || "")}
            ${item.video_url ? `· <a href="${item.video_url}" target="_blank" class="activity-link">Watch ↗</a>` : ""}
          </div>
        </div>
        <span class="activity-via">${esc(item.message || "")}</span>
        <span class="activity-time">${timeAgo(item.created_at)}</span>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = `<div style="text-align:center;padding:40px;color:var(--error)">Failed to load activity</div>`;
  }
}

// ─── Modals ───────────────────────────────────────────────────────────────────
function openTopicModal() {
  document.getElementById("topicName").value = "";
  document.getElementById("topicDesc").value = "";
  document.getElementById("topicModal").classList.add("open");
  setTimeout(() => document.getElementById("topicName").focus(), 50);
}

function closeModal(id) {
  document.getElementById(id).classList.remove("open");
}

// Enter key on modal inputs
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeModal("topicModal");
    closeSearchPanel();
    closeConfigPanel();
  }
});

// ─── Toast ───────────────────────────────────────────────────────────────────
function toast(msg, type = "info") {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = "0"; el.style.transition = "opacity 0.3s"; setTimeout(() => el.remove(), 300); }, 3500);
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function formatNum(n) {
  if (!n) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(0) + "K";
  return String(n);
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso + "Z").getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
}

// ─── Channel Detail View ─────────────────────────────────────────────────────
async function openChannelDetail(channelDbId, name) {
  const ch = state.channels.find(c => c.id === channelDbId);
  if (!ch) return;
  state.activeChannel = ch;
  
  document.getElementById("topicChannelsView").style.display = "none";
  document.getElementById("channelDetailView").style.display = "block";
  document.getElementById("detailChannelName").textContent = name;
  
  const grid = document.getElementById("detailVideosGrid");
  grid.innerHTML = `<div class="loading-spinner"></div>`;
  
  try {
    const videos = await api("GET", `/api/channels/${channelDbId}/videos`);
    document.getElementById("detailChannelMeta").textContent = `${videos.length} tracked videos`;
    
    if (videos.length === 0) {
      grid.innerHTML = `<div style="padding: 20px; color: var(--text3)">No videos tracked yet.</div>`;
      return;
    }
    
    grid.innerHTML = videos.map(v => `
      <div class="video-card">
        <img class="video-thumb" src="https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg" onerror="this.style.background='#222'" />
        <span class="video-status ${v.pushed_to_nlm ? 'pushed' : 'tracked'}">${v.pushed_to_nlm ? 'NLM ✓' : 'Tracked'}</span>
        <div class="video-info">
          <div class="video-title" title="${esc(v.title)}">${esc(v.title)}</div>
          <div class="video-meta">${timeAgo(v.created_at)}</div>
        </div>
      </div>
    `).join("");
  } catch(e) {
    grid.innerHTML = `<div style="color:var(--error)">Failed to load videos</div>`;
  }
}

function closeChannelDetail() {
  document.getElementById("channelDetailView").style.display = "none";
  document.getElementById("topicChannelsView").style.display = "block";
  state.activeChannel = null;
}

// ─── Preview Fetch View ──────────────────────────────────────────────────────
let previewState = {
  isNew: true,
  channelData: null,
  videos: [],
  selectedIds: new Set()
};

async function openFetchPreview(channelData, isNew = true) {
  previewState.isNew = isNew;
  previewState.channelData = channelData;
  previewState.selectedIds.clear();
  previewState.videos = [];
  
  if(isNew) closeSearchPanel();
  document.getElementById("topicChannelsView").style.display = "none";
  document.getElementById("channelDetailView").style.display = "none";
  document.getElementById("previewFetchView").style.display = "block";
  
  document.getElementById("previewTitle").textContent = isNew ? "Add Channel & Push Videos" : "Fetch More Videos";
  document.getElementById("previewChannelName").textContent = channelData.channel_name;
  
  await reloadPreview();
}

function closePreviewFetch() {
  document.getElementById("previewFetchView").style.display = "none";
  if (previewState.isNew) {
    document.getElementById("topicChannelsView").style.display = "block";
  } else {
    document.getElementById("channelDetailView").style.display = "block";
  }
}

async function reloadPreview() {
  const grid = document.getElementById("previewVideosGrid");
  const count = document.getElementById("previewFetchCount")?.value || 25;
  const sort = document.getElementById("previewSortBy").value;
  
  grid.innerHTML = `<div style="grid-column: 1/-1; padding: 40px; text-align: center;"><div class="loading-spinner" style="display:inline-block"></div><div style="margin-top:16px; color:var(--text2)">Fetching videos from YouTube...</div></div>`;
  
  try {
    const chId = previewState.isNew ? previewState.channelData.channel_id : previewState.channelData.channel_id;
    const videos = await api("GET", `/api/channels/preview?channel_id=${chId}&sort_by=${sort}`);
    
    // Default select all up to the chosen count
    previewState.videos = videos.slice(0, parseInt(count));
    previewState.selectedIds = new Set(previewState.videos.map(v => v.video_id));
    
    renderPreviewGrid();
  } catch (e) {
    grid.innerHTML = `<div style="grid-column: 1/-1; padding: 40px; text-align: center; color:var(--error)">Failed to fetch preview: ${e.message}</div>`;
  }
}

function renderPreviewGrid() {
  const grid = document.getElementById("previewVideosGrid");
  document.getElementById("previewSelectedCount").textContent = `(${previewState.selectedIds.size} selected)`;
  
  if(previewState.videos.length === 0) {
    grid.innerHTML = `<div style="color:var(--text3); padding:20px;">No videos found.</div>`;
    return;
  }
  
  grid.innerHTML = previewState.videos.map(v => {
    const isSel = previewState.selectedIds.has(v.video_id);
    return `
      <div class="video-card ${isSel ? 'selected' : ''}" onclick="togglePreviewVideo('${v.video_id}')">
        <input type="checkbox" class="video-checkbox" ${isSel ? 'checked' : ''} onclick="event.stopPropagation(); togglePreviewVideo('${v.video_id}')" />
        <img class="video-thumb" src="${v.thumbnail || `https://i.ytimg.com/vi/${v.video_id}/mqdefault.jpg`}" onerror="this.style.background='#222'" />
        <div class="video-info">
          <div class="video-title" title="${esc(v.title)}">${esc(v.title)}</div>
          <div class="video-meta">${v.published_at ? new Date(v.published_at).toLocaleDateString() : ''}</div>
        </div>
      </div>
    `;
  }).join("");
}

function togglePreviewVideo(id) {
  if (previewState.selectedIds.has(id)) {
    previewState.selectedIds.delete(id);
  } else {
    previewState.selectedIds.add(id);
  }
  renderPreviewGrid();
}

async function confirmPushVideos() {
  if (previewState.selectedIds.size === 0) {
    if(!confirm("You haven't selected any videos. Add channel without pushing anything?")) return;
  }
  
  const btn = document.getElementById("btnConfirmPush");
  btn.disabled = true;
  btn.textContent = "Pushing to NotebookLM...";
  
  try {
    const ch = previewState.channelData;
    const sort = document.getElementById("previewSortBy").value;
    
    if (previewState.isNew) {
      await api("POST", "/api/channels", {
        topic_id: state.activeTopic.id,
        channel_id: ch.channel_id,
        channel_name: ch.channel_name,
        thumbnail_url: ch.thumbnail_url || "",
        subscriber_count: ch.subscriber_count || 0,
        sort_by: sort,
        video_ids: Array.from(previewState.selectedIds),
        video_fetch_count: previewState.selectedIds.size
      });
      toast(`Channel added and videos pushed!`, "success");
      await loadChannels();
      await loadTopics();
      closePreviewFetch();
      loadSuggestions(ch.channel_id);
    } else {
      // Fetch more logic
      toast("Not fully implemented yet for existing channels (requires backend manual fetch update)", "info");
      closePreviewFetch();
    }
  } catch(e) {
    toast("Failed: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirm & Push Selected";
  }
}

