-- Mesen 0.9.9 focused runtime check for the five Mitsume commands.

local commands = { 0xA0, 0xA7, 0xA8, 0xA9, 0xAA }
local data_banks = { 0x6F, 0x79, 0x7A, 0x7C, 0x7D }
local engine_banks = { 0x74, 0x74, 0x7B, 0x74, 0x74 }

local function read_byte(address)
    return emu.read(address, emu.memType.cpuDebug, false)
end

local function write_byte(address, value)
    emu.write(address, value, emu.memType.cpuDebug)
end

local function prg_offset(address)
    local value = emu.getPrgRomOffset(address)
    if value == nil then return -1 end
    return value
end

local frame = 0
local track = 0
local phase_frame = 0
local allowed_command = nil
local injected = false
local init_hits = 0
local play_hits = 0
local apu_writes = 0
local mapping_errors = 0
local unsafe_bss_writes = 0
local dmc_hits = 0
local before_init = 0
local before_play = 0
local before_apu = 0

local function active()
    if track < 1 or track > #commands then return false end
    local magic = read_byte(0x046A)
    return (magic == 0xC3 or magic == 0xD3 or magic == 0xD4) and
           read_byte(0x046B) == commands[track]
end

emu.addMemoryCallback(function()
    if not injected or read_byte(0x046A) == 0xD3 then return end
    if allowed_command ~= nil then
        write_byte(0x004C, allowed_command)
        allowed_command = nil
    elseif read_byte(0x004C) >= 0x80 then
        write_byte(0x004C, 0xFF)
    end
end, emu.memCallbackType.cpuExec, 0xB500, 0xB500)

local function check_mapping(address)
    if not active() then return end
    local expected_engine = engine_banks[track] * 0x2000 + (address - 0xA000)
    local expected_data = data_banks[track] * 0x2000
    if prg_offset(address) ~= expected_engine or
       prg_offset(0x8000) ~= expected_data then
        mapping_errors = mapping_errors + 1
    end
end

emu.addMemoryCallback(function()
    if active() then
        init_hits = init_hits + 1
        check_mapping(0xB100)
    end
end, emu.memCallbackType.cpuExec, 0xB100, 0xB100)

emu.addMemoryCallback(function()
    if active() then
        play_hits = play_hits + 1
        check_mapping(0xB160)
    end
end, emu.memCallbackType.cpuExec, 0xB160, 0xB160)

emu.addMemoryCallback(function()
    if active() then apu_writes = apu_writes + 1 end
end, emu.memCallbackType.cpuWrite, 0x4000, 0x4013)

local function native_pc()
    local pc = emu.getState().cpu.pc
    return active() and pc >= 0xB000 and pc <= 0xBCFF
end

emu.addMemoryCallback(function()
    if native_pc() then unsafe_bss_writes = unsafe_bss_writes + 1 end
end, emu.memCallbackType.cpuWrite, 0x0200, 0x02A3)

local function dmc_hit()
    if active() then dmc_hits = dmc_hits + 1 end
end
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xB85B, 0xB85B)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xB9FA, 0xB9FA)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xBA56, 0xBA56)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xBC64, 0xBC64)

local function start_track(index)
    track = index
    phase_frame = 0
    before_init = init_hits
    before_play = play_hits
    before_apu = apu_writes
    allowed_command = commands[index]
    write_byte(0x004C, commands[index])
end

local function check_track()
    if read_byte(0x046B) ~= commands[track] then return false end
    if init_hits <= before_init then return false end
    if play_hits - before_play < 30 then return false end
    if apu_writes <= before_apu then return false end
    if mapping_errors ~= 0 or unsafe_bss_writes ~= 0 or dmc_hits ~= 0 then
        return false
    end
    return true
end

emu.addEventCallback(function()
    frame = frame + 1
    if frame == 1200 then
        injected = true
        start_track(1)
    elseif track >= 1 and track <= #commands then
        phase_frame = phase_frame + 1
        if phase_frame == 180 then
            if not check_track() then return emu.stop(10 + track) end
            if track < #commands then
                start_track(track + 1)
            else
                track = #commands + 1
                phase_frame = 0
                allowed_command = 0x80
                write_byte(0x004C, 0x80)
            end
        end
    elseif track == #commands + 1 then
        phase_frame = phase_frame + 1
        if phase_frame == 120 then
            if read_byte(0x046A) ~= 0 then return emu.stop(30) end
            emu.stop(0)
        end
    elseif frame > 3000 then
        emu.stop(40)
    end
end, emu.eventType.endFrame)
