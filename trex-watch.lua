-- trex-watch.lua: keep the tabs of agents trex started saying who started
-- whom and how the children are doing.
--
--   parent's tab:  ✉2 ⟳1 ✓1 ⚠1 · its own title  (unread, working, finished,
--                                                 needs you)
--   child's tab:   ↳ fix-retry 40% · its own title   (placed after it by spawn)
--
-- `trex spawn` records each link in LINKS and starts this script when its
-- heartbeat is stale; nothing else needs to run it. It only reads LINKS and
-- writes window labels, so stopping it loses nothing: the next spawn starts
-- it again. Run by hand: rex do trex-watch.lua --all

local STATE = (os.getenv("XDG_STATE_HOME") or (os.getenv("HOME") .. "/.local/state")) .. "/trex"
local LINKS = STATE .. "/links.json"
local BEAT = STATE .. "/watch.beat"
local INBOX = STATE .. "/inbox"
local TERMINAL = "com.superlogical.terminal"

-- How often the whole picture is redrawn, whatever the events say: a link
-- just written by spawn shows up within this many seconds.
local RECONCILE = 3
-- What each state counts as on the parent's tab.
local MARK = { working = "⟳", done = "✓", idle = "✓", blocked = "⚠", error = "⚠" }
local MAIL = "✉"
local ORDER = { MAIL, "⟳", "✓", "⚠" }
-- A child's label starts with CHILD; a parent's starts with its counts and
-- PARENT_SEP comes before its title.
local CHILD, PARENT_SEP = "↳ ", " · "

local function read_links()
  local f = io.open(LINKS, "r")
  if not f then return {} end
  local text = f:read("*a")
  f:close()
  local ok, links = pcall(rex.json.decode, text)
  return (ok and type(links) == "table") and links or {}
end

local function beat()
  local f = io.open(BEAT, "w")
  if f then f:write(tostring(os.time())); f:close() end
end

-- A label this script wrote, or Rex's default "Window xxxxxxxx", says
-- nothing of its own; any other label is the user's and is kept.
local function ours(label)
  if label:sub(1, #CHILD) == CHILD then return true end
  for _, m in ipairs(ORDER) do
    if label:sub(1, #m) == m and label:sub(#m + 1, #m + 1):match("%d") then return true end
  end
  return false
end

local function base_of(label)
  if not label or label == "" or label:match("^Window %x+$") or ours(label) then return nil end
  return label
end

-- What the agent calls its task: the terminal's title without a leading
-- spinner, and without a " | worktree" tail some agents add.
local function title_of(block_id)
  local r = rex.block.call(TERMINAL, "title", { block_id = block_id })
  local t = (r and r.title) or ""
  t = t:gsub("^[^%w%p\208-\209]+", ""):gsub("%s+|%s+[^|]*$", "")
  return t ~= "" and t or nil
end

-- Unread messages in each inbox trex left them in, by block id.
local function unread()
  local counts = {}
  local dirs = rex.exec({ "ls", INBOX }, { timeout = 5 })
  if not (dirs and dirs.ok) then return counts end
  for dir in dirs.stdout:gmatch("[^\n]+") do
    local files = rex.exec({ "ls", INBOX .. "/" .. dir }, { timeout = 5 })
    local n = 0
    for f in ((files and files.stdout) or ""):gmatch("[^\n]+") do
      if f:match("%.txt$") then n = n + 1 end
    end
    if n > 0 then counts[(dir:gsub("_", ":", 1))] = n end
  end
  return counts
end

local function status_of(block_id)
  local r = rex.block.call(TERMINAL, "program_status", { block_id = block_id })
  local rec = r and r.records and r.records[1]
  return (rec and rec.state) or "-", rec and rec.progress
end

-- Every block of a session: its window, its label, and whether it is the
-- only block there (only then is the tab its own to label).
local function blocks_of(session_id)
  local view = rex.session.view{ session_id = session_id }
  local blocks = {}
  for _, w in ipairs((view and view.windows) or {}) do
    local inside = {}
    for _, layer in ipairs(w.layers or {}) do
      for _, b in ipairs(layer.blocks or {}) do inside[#inside + 1] = b end
    end
    for _, b in ipairs(inside) do
      blocks[b.block_id] = { window = w.window_id, window_label = w.label,
                             label = b.label, alone = #inside == 1 }
    end
  end
  return blocks
end

local function name_of(b, fallback)
  if b and b.label and b.label ~= "" and b.label ~= "shell" then return b.label end
  return fallback or "agent"
end

local labelled = {}  -- window_id -> label this script last set
local touched = {}   -- session_id -> true once it had a link

local function set_label(session_id, window, label)
  if labelled[window] == label then return end
  rex.session.set_window_label{ session_id = session_id, window_id = window, label = label }
  labelled[window] = label
end

local function reconcile()
  beat()
  local links = read_links()
  local sessions = {}
  for child, link in pairs(links) do
    sessions[link.session] = sessions[link.session] or {}
    table.insert(sessions[link.session], { child = child, parent = link.parent,
                                           name = link.name, parent_name = link.parent_name })
  end
  for session_id in pairs(sessions) do touched[session_id] = true end
  local mail = unread()
  local seen = {}
  for session_id in pairs(touched) do
    local list = sessions[session_id] or {}
    local blocks = blocks_of(session_id)
    local counts = {}  -- parent block -> mark -> n
    for block_id, n in pairs(mail) do
      if blocks[block_id] then counts[block_id] = { [MAIL] = n } end
    end
    for _, l in ipairs(list) do
      local child = blocks[l.child]
      if child then
        local state, progress = status_of(l.child)
        local parent = blocks[l.parent]
        if child.alone and child.window ~= (parent and parent.window) then
          local title = title_of(l.child)
          local label = CHILD .. (base_of(child.window_label) or name_of(child, l.name))
            .. (progress and (" " .. progress .. "%") or "")
            .. (title and (PARENT_SEP .. title) or "")
          set_label(session_id, child.window, label)
          seen[child.window] = true
        end
        if parent then
          local mark = MARK[state]
          if mark then
            counts[l.parent] = counts[l.parent] or {}
            counts[l.parent].name = l.parent_name
            counts[l.parent][mark] = (counts[l.parent][mark] or 0) + 1
          end
        end
      end
    end
    for parent_id, marks in pairs(counts) do
      local parent = blocks[parent_id]
      if parent and parent.alone then
        local parts = {}
        local pname = marks.name
        for _, m in ipairs(ORDER) do
          if marks[m] then parts[#parts + 1] = m .. marks[m] end
        end
        set_label(session_id, parent.window, table.concat(parts, " ") .. PARENT_SEP
          .. (base_of(parent.window_label) or title_of(parent_id) or name_of(parent, pname)))
        seen[parent.window] = true
      end
    end
    -- A tab this script labelled that has no live link any more gets its
    -- own name back, also one labelled by an earlier run of it.
    for _, b in pairs(blocks) do
      local mine = labelled[b.window] or (b.window_label and ours(b.window_label))
      if mine and not seen[b.window] then
        rex.session.set_window_label{ session_id = session_id, window_id = b.window,
                                      label = base_of(b.window_label) or "" }
        labelled[b.window] = nil
      end
    end
  end
end

local pending
local function soon()
  if pending then pending:cancel() end
  pending = rex.after(0.3, reconcile)
end

rex.on("terminal.program_status_changed", soon)
rex.on("terminal.program_status_removed", soon)
rex.on("block_closed", soon)
-- Labels an earlier run left behind are found in any session.
local listed = rex.call("session.list")
for _, sess in ipairs((listed and listed.sessions) or {}) do touched[sess.session_id] = true end

rex.every(RECONCILE, reconcile)
reconcile()
