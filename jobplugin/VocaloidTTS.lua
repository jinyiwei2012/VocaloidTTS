--
-- VocaloidTTS.lua  ·  VOCALOID4 Job Plugin
-- 读取 VocaloidTTS Studio 生成的调教数据，把音符、拼音、PIT 音高曲线、
-- DYN/BRI/CLE/OPE/BRE 表情参数一次性写入当前 Musical Part。
--
-- 数据默认路径：%LOCALAPPDATA%\VocaloidTTS\vocaloidtts_job.txt
-- 在 VocaloidTTS Studio 中点击“生成 VSQX”时会自动刷新该文件。
--

function manifest()
    myManifest = {
        name          = "VocaloidTTS 语调教导入",
        comment       = "把 VocaloidTTS Studio 的语调教数据写入当前序列（音符 + PIT + 表情参数）",
        author        = "VocaloidTTS",
        pluginID      = "{A7C4E2B1-6D3F-4A8E-9B21-5C0D7E3F1A90}",
        pluginVersion = "1.1.0.0",
        apiVersion    = "3.0.0.1"
    }
    return myManifest
end

local function defaultPath()
    local base = os.getenv("LOCALAPPDATA")
    if base == nil or base == "" then
        base = os.getenv("USERPROFILE") .. "\\AppData\\Local"
    end
    return base .. "\\VocaloidTTS\\vocaloidtts_job.txt"
end

local function readAll(path)
    local f, err = io.open(path, "rb")
    if f == nil then
        return nil, err
    end
    local data = f:read("*a")
    f:close()
    return data
end

local function trim(s)
    return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

function main(processParam, envParam)
    VSDlgSetDialogTitle("VocaloidTTS 语调教导入")

    local field = {}
    field.name       = "path"
    field.caption    = "调教数据文件"
    field.initialVal = defaultPath()
    field.type       = 3
    VSDlgAddField(field)

    field = {}
    field.name       = "offset"
    field.caption    = "插入位置（Tick，0 = 序列开头）"
    field.initialVal = "0"
    field.type       = 0
    VSDlgAddField(field)

    field = {}
    field.name       = "clear"
    field.caption    = "先清除目标范围内的旧音符"
    field.initialVal = "1"
    field.type       = 1
    VSDlgAddField(field)

    local dlgStatus = VSDlgDoModal()
    if dlgStatus ~= 1 then
        return 0
    end

    local path, offset, clearFlag
    dlgStatus, path = VSDlgGetStringValue("path")
    dlgStatus, offset = VSDlgGetIntValue("offset")
    dlgStatus, clearFlag = VSDlgGetBoolValue("clear")

    local data, err = readAll(path)
    if data == nil then
        VSMessageBox("无法读取调教数据：\n" .. path .. "\n\n" .. tostring(err), 0)
        return 0
    end

    local notes = {}
    local ccs = {}
    local total = 0
    for line in data:gmatch("[^\r\n]+") do
        if line:sub(1, 1) ~= "#" then
            local kind = line:match("^(%u+)")
            if kind == "NOTE" then
                local t, d, n, vel, acc, lyric, ph =
                    line:match("^NOTE\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t(%d+)\t([^\t]*)\t(.*)$")
                if t == nil then
                    -- backward compatibility with v1 job files
                    t, d, n, lyric, ph = line:match("^NOTE\t(%d+)\t(%d+)\t(%d+)\t([^\t]*)\t(.*)$")
                    vel, acc = 64, 50
                end
                if t ~= nil then
                    table.insert(notes, {
                        t = tonumber(t), d = tonumber(d), n = tonumber(n),
                        vel = tonumber(vel), acc = tonumber(acc),
                        lyric = lyric, ph = ph
                    })
                end
            elseif kind == "CC" then
                local cid, t, v = line:match("^CC\t([A-Z]+)\t(%-?%d+)\t(%-?%d+)$")
                if cid ~= nil then
                    table.insert(ccs, { id = cid, t = tonumber(t), v = tonumber(v) })
                end
            elseif kind == "TOTAL" then
                local t = line:match("^TOTAL\t(%d+)")
                if t ~= nil then total = tonumber(t) end
            end
        end
    end

    if #notes == 0 then
        VSMessageBox("调教数据里没有音符。\n请先在 VocaloidTTS Studio 中生成一次。", 0)
        return 0
    end

    local ret, part = VSGetMusicalPart()
    if ret ~= 1 then
        VSMessageBox("当前没有 Musical Part。\n请先新建或选中一个音乐序列。", 0)
        return 0
    end

    -- optionally clear old notes in the target range
    if clearFlag then
        local removeList = {}
        VSSeekToBeginNote()
        local nret, n = VSGetNextNote()
        while nret == 1 do
            if n.posTick >= offset and n.posTick < offset + total then
                table.insert(removeList, n)
            end
            nret, n = VSGetNextNote()
        end
        for i = 1, #removeList do
            VSRemoveNote(removeList[i])
        end
    end

    -- notes
    local inserted = 0
    for i = 1, #notes do
        local s = notes[i]
        local note = {}
        note.posTick        = offset + s.t
        note.durTick        = s.d
        note.noteNum        = s.n
        note.velocity       = s.vel or 64
        note.lyric          = s.lyric
        note.phonemes       = s.ph
        note.phLock         = 0
        note.bendDepth      = 8
        note.bendLength     = 0
        note.risePort       = 0
        note.fallPort       = 0
        note.decay          = 50
        note.accent         = s.acc or 50
        note.opening        = 127
        note.vibratoLength  = 0
        note.vibratoType    = 0
        local ok = VSInsertNoteEx(note)
        if ok == 1 then
            inserted = inserted + 1
        end
    end

    -- controllers (dedupe by type + tick)
    local ccCount = 0
    local seen = {}
    for i = 1, #ccs do
        local c = ccs[i]
        local key = c.id .. ":" .. c.t
        if not seen[key] then
            seen[key] = true
            local ctrl = {}
            ctrl.posTick = offset + c.t
            ctrl.value   = c.v
            ctrl.type    = c.id
            local ok = VSInsertControl(ctrl)
            if ok == 1 then
                ccCount = ccCount + 1
            end
        end
    end

    -- extend the part so the new notes are inside it
    if total > 0 then
        local want = part.posTick + offset + total + 1920
        if part.playTime < want then
            part.playTime = want
            VSUpdateMusicalPart(part)
        end
    end

    VSMessageBox("VocaloidTTS 导入完成。\n\n音符：" .. inserted .. " / " .. #notes ..
                 "\n控制点：" .. ccCount .. " / " .. #ccs ..
                 "\n\n按空格试听；可在 File > Export 中导出 WAV。", 0)
    return 0
end
