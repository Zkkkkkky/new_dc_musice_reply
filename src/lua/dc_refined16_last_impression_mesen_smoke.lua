-- Focused Mesen 0.9.9 runtime check for LAST IMPRESSION.
-- Command $A6 must select Bank $78 and run the relocated common driver.

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
local injected = false
local allowed_command = false
local bridge_hits = 0
local init_hits = 0
local play_hits = 0
local apu_writes = 0
local mapping_errors = 0
local unsafe_bss_writes = 0
local dmc_hits = 0

local function active()
    local magic = read_byte(0x046A)
    return (magic == 0xC3 or magic == 0xD3 or magic == 0xD4) and
           read_byte(0x046B) == 0xA6
end

emu.addMemoryCallback(function()
    bridge_hits = bridge_hits + 1
    if not injected or read_byte(0x046A) == 0xD3 then return end
    if allowed_command then
        write_byte(0x004C, 0xA6)
        allowed_command = false
    elseif read_byte(0x004C) >= 0x80 then
        write_byte(0x004C, 0xFF)
    end
end, emu.memCallbackType.cpuExec, 0xB500, 0xB500)

local function check_mapping(address)
    local expected_engine = 0x74 * 0x2000 + (address - 0xA000)
    local expected_data = 0x78 * 0x2000
    if prg_offset(address) ~= expected_engine or
       prg_offset(0x8000) ~= expected_data then
        mapping_errors = mapping_errors + 1
    end
end

emu.addMemoryCallback(function()
    if not active() then return end
    init_hits = init_hits + 1
    check_mapping(0xB100)
end, emu.memCallbackType.cpuExec, 0xB100, 0xB100)

emu.addMemoryCallback(function()
    if not active() then return end
    play_hits = play_hits + 1
    check_mapping(0xB160)
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

emu.addEventCallback(function()
    frame = frame + 1
    if frame == 1200 then
        injected = true
        allowed_command = true
        write_byte(0x004C, 0xA6)
    elseif frame == 1320 then
        if bridge_hits <= 100 then return emu.stop(1) end
        if init_hits < 1 then return emu.stop(2) end
        if play_hits < 10 then return emu.stop(3) end
        if apu_writes == 0 then return emu.stop(4) end
        if mapping_errors ~= 0 then return emu.stop(5) end
        if unsafe_bss_writes ~= 0 then return emu.stop(6) end
        if dmc_hits ~= 0 then return emu.stop(7) end
        emu.stop(0)
    end
end, emu.eventType.endFrame)
