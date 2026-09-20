-- FCEUX runtime matrix for all 16 refined commands after the $5000 latch fix.

local output = assert(io.open("fceux_refined16_track_smoke.log", "w"))
local commands = {
    0x94, 0x95, 0xa5, 0x96, 0x97,
    0x98, 0x99, 0x9a, 0x9b, 0x9c,
    0xa0, 0xa1, 0xa2, 0xa3, 0xa4, 0xa6,
}

local function reg(name)
    local ok, value = pcall(memory.getregister, name)
    if ok and value ~= nil then return value end
    return -1
end

local frame = 0
local track = 0
local phase_frame = 0
local init_hits = 0
local play_hits = 0
local return_hits = 0
local clear_hits = 0
local apu_writes = 0
local before_init = 0
local before_play = 0
local before_return = 0
local before_clear = 0
local before_apu = 0
local failures = 0

memory.registerexec(0xb100, 1, function() init_hits = init_hits + 1 end)
memory.registerexec(0xb160, 1, function() play_hits = play_hits + 1 end)
memory.registerexec(0x9a04, 1, function() return_hits = return_hits + 1 end)
memory.registerwrite(0x5000, 0x1000, function(address, size, value)
    if value == 0x27 then clear_hits = clear_hits + 1 end
end)
memory.registerwrite(0x4000, 0x14, function() apu_writes = apu_writes + 1 end)

local function start_track(index)
    track = index
    phase_frame = 0
    before_init = init_hits
    before_play = play_hits
    before_return = return_hits
    before_clear = clear_hits
    before_apu = apu_writes
    memory.writebyte(0x004c, commands[index])
end

local function check_track()
    local command = commands[track]
    local active = memory.readbyte(0x046b)
    local initialized = init_hits > before_init
    local played = play_hits - before_play >= 10
    local clean_state = active == command or (active == 0 and played)
    local ok = clean_state and
        initialized and
        played and
        return_hits - before_return >= 10 and
        clear_hits - before_clear >= 10 and
        apu_writes > before_apu and
        reg("pc") >= 0x8000
    if not ok then failures = failures + 1 end
    output:write(string.format(
        "TRACK command=%02X ok=%s active=%02X init=%d play=%d returns=%d " ..
        "clears=%d apu=%d pc=%04X sp=%02X\n",
        command, tostring(ok), active, init_hits - before_init,
        play_hits - before_play, return_hits - before_return,
        clear_hits - before_clear, apu_writes - before_apu,
        reg("pc"), reg("s")))
    output:flush()
end

emu.speedmode("maximum")
emu.softreset()

for loop_frame = 1, 8000 do
    frame = loop_frame
    emu.frameadvance()

    if frame == 1200 then
        start_track(1)
    elseif track > 0 then
        phase_frame = phase_frame + 1
        if phase_frame == 240 then
            check_track()
            if track < #commands then
                start_track(track + 1)
            else
                output:write(string.format(
                    "RESULT pass=%s tracks=%d failures=%d init=%d play=%d " ..
                    "returns=%d clears=%d apu=%d pc=%04X sp=%02X\n",
                    tostring(failures == 0), #commands, failures,
                    init_hits, play_hits, return_hits, clear_hits,
                    apu_writes, reg("pc"), reg("s")))
                output:close()
                emu.exit()
                return
            end
        end
    end
end

output:write(string.format("TIMEOUT frame=%d track=%d failures=%d\n", frame, track, failures))
output:close()
emu.exit()
