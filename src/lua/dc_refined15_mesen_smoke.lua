-- Runtime regression for both refined15 bridge variants.
-- The v2 build retains the old FamiStudio $9D-$9F instance.  The v3
-- two-engine build clears it and safely consumes those removed commands.

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

local commands = {
    0x94, 0x95, 0xA5, 0x96, 0x97,
    0x98, 0x99, 0x9A, 0x9B, 0x9C,
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4,
}

local logical_ids = {
    0x14, 0x15, 0x22, 0x16, 0x17,
    0x18, 0x19, 0x1A, 0x1B, 0x1C,
    0x1D, 0x1E, 0x1F, 0x20, 0x21,
}

local frame = 0
local bridge_hits = 0
local stock_hits = 0
local native_init_hits = 0
local native_play_hits = 0
local native_apu_writes = 0
local native_sfx_apu_writes = 0
local fami_update_hits = 0
local fami_apu_writes = 0
local mapping_errors = 0
local unsafe_old_bss_writes = 0
local unsafe_old_bss_pc = 0
local unsafe_old_zp_writes = 0
local dmc_handler_hits = 0
local native_return_hits = 0
local native_init_rts_hits = 0
local native_after_init_hits = 0
local init_milestones = {0, 0, 0, 0, 0, 0, 0, 0, 0, 0}
local two_engine = nil

local hold_custom = false
local allowed_command = -1

local function valid_magic()
    local magic_c = read_byte(0x046A)
    return magic_c == 0xC3 or magic_c == 0xD3 or magic_c == 0xD4
end

local function native_state()
    if not valid_magic() then return false end
    local state = read_byte(0x046B)
    return (state >= 0x94 and state <= 0x9C) or
           (state >= 0xA0 and state <= 0xA5)
end

emu.addMemoryCallback(function()
    bridge_hits = bridge_hits + 1
    if two_engine == nil then
        two_engine = read_byte(0xA009) == 0x00 and
                     read_byte(0xA00A) == 0x00 and
                     read_byte(0xA00B) == 0x00
    end
    if prg_offset(0xB500) ~= 0xC9500 then
        mapping_errors = mapping_errors + 1
    end
    if hold_custom and read_byte(0x046A) ~= 0xD3 then
        local command = read_byte(0x004C)
        if allowed_command >= 0 then
            write_byte(0x004C, allowed_command)
            allowed_command = -1
        elseif command >= 0x80 then
            write_byte(0x004C, 0xFF)
        end
    end
end, emu.memCallbackType.cpuExec, 0xB500, 0xB500)

emu.addMemoryCallback(function()
    stock_hits = stock_hits + 1
end, emu.memCallbackType.cpuExec, 0x8020, 0x8020)

emu.addMemoryCallback(function()
    if native_state() then native_return_hits = native_return_hits + 1 end
end, emu.memCallbackType.cpuExec, 0x9A04, 0x9A04)

emu.addMemoryCallback(function()
    if native_state() then native_init_rts_hits = native_init_rts_hits + 1 end
end, emu.memCallbackType.cpuExec, 0xB12A, 0xB12A)

emu.addMemoryCallback(function()
    if native_state() then native_after_init_hits = native_after_init_hits + 1 end
end, emu.memCallbackType.cpuExec, 0xBD65, 0xBD65)

local milestone_addresses = {
    0xB180, 0xB1D8, 0xB257, 0xB25A, 0xB2D5, 0xB9EF,
    0xB192, 0xB194, 0xB1AB, 0xB1D5,
}
for index, address in ipairs(milestone_addresses) do
    emu.addMemoryCallback(function()
        if native_state() then init_milestones[index] = init_milestones[index] + 1 end
    end, emu.memCallbackType.cpuExec, address, address)
end

local function expected_track_index(command)
    if command == 0xA5 then return 2 end
    if command < 0x96 then return command - 0x94 end
    if command < 0xA0 then return command - 0x93 end
    return command - 0x96
end

local function check_native_mapping(address)
    local command = read_byte(0x046B)
    local index = expected_track_index(command)
    local engine_bank = command == 0x9C and 0x75 or 0x74
    local expected_engine = engine_bank * 0x2000 + (address - 0xA000)
    local expected_data = (0x65 + index) * 0x2000
    if prg_offset(address) ~= expected_engine or prg_offset(0x8000) ~= expected_data then
        mapping_errors = mapping_errors + 1
    end
end

emu.addMemoryCallback(function()
    if not native_state() then return end
    local offset = prg_offset(0xB100)
    if offset ~= 0xE9100 and offset ~= 0xEB100 then return end
    native_init_hits = native_init_hits + 1
    check_native_mapping(0xB100)
end, emu.memCallbackType.cpuExec, 0xB100, 0xB100)

emu.addMemoryCallback(function()
    if not native_state() then return end
    local offset = prg_offset(0xB160)
    if offset ~= 0xE9160 and offset ~= 0xEB160 then return end
    native_play_hits = native_play_hits + 1
    check_native_mapping(0xB160)
end, emu.memCallbackType.cpuExec, 0xB160, 0xB160)

emu.addMemoryCallback(function()
    if not valid_magic() or read_byte(0x046B) < 0x9D or
       read_byte(0x046B) > 0x9F then return end
    fami_update_hits = fami_update_hits + 1
    if prg_offset(0xA009) ~= 0xC8009 then
        mapping_errors = mapping_errors + 1
    end
end, emu.memCallbackType.cpuExec, 0xA009, 0xA009)

emu.addMemoryCallback(function()
    local state = read_byte(0x046B)
    if (state >= 0x94 and state <= 0x9C) or
       (state >= 0xA0 and state <= 0xA5) then
        native_apu_writes = native_apu_writes + 1
    elseif state >= 0x9D and state <= 0x9F then
        fami_apu_writes = fami_apu_writes + 1
    end
end, emu.memCallbackType.cpuWrite, 0x4000, 0x4013)

emu.addMemoryCallback(function()
    if native_state() then
        native_sfx_apu_writes = native_sfx_apu_writes + 1
    end
end, emu.memCallbackType.cpuExec, 0xBE4D, 0xBE4D)

local function native_pc()
    local offset = prg_offset(0xB000)
    if offset ~= 0xE9000 and offset ~= 0xEB000 then return false end
    local pc = emu.getState().cpu.pc
    return pc >= 0xB000 and pc <= 0xBCFF
end

emu.addMemoryCallback(function()
    if native_pc() then
        unsafe_old_bss_writes = unsafe_old_bss_writes + 1
        if unsafe_old_bss_pc == 0 then unsafe_old_bss_pc = emu.getState().cpu.pc end
    end
end, emu.memCallbackType.cpuWrite, 0x0200, 0x02A3)

emu.addMemoryCallback(function()
    if native_pc() then unsafe_old_zp_writes = unsafe_old_zp_writes + 1 end
end, emu.memCallbackType.cpuWrite, 0x0000, 0x0007)

local function dmc_hit()
    if native_state() then dmc_handler_hits = dmc_handler_hits + 1 end
end
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xB85B, 0xB85B)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xB9FA, 0xB9FA)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xBA56, 0xBA56)
emu.addMemoryCallback(dmc_hit, emu.memCallbackType.cpuExec, 0xBC64, 0xBC64)

local phase = "boot"
-- Let a cold ROM finish its title/save initialization before injecting test
-- commands.  Starting at frame 300 made the harness race a first-run SRAM
-- write even though the audio bridge itself was healthy.
local deadline = 1200
local track_index = 0
local removed_command_index = 0
local before_init = 0
local before_play = 0
local before_apu = 0
local before_stock = 0
local before_fami = 0
local before_fami_apu = 0
local before_bridge = 0
local before_native_sfx_apu = 0

local function fail(code)
    emu.stop(code)
end

local function pass()
    emu.stop(0)
end

local function start_track(index)
    track_index = index
    before_init = native_init_hits
    before_play = native_play_hits
    before_apu = native_apu_writes
    before_bridge = bridge_hits
    allowed_command = commands[index]
    write_byte(0x004C, commands[index])
    deadline = frame + 240
    phase = "native"
end

emu.addEventCallback(function()
    frame = frame + 1
    if frame < deadline then return end

    if phase == "boot" then
        if bridge_hits < 100 then return fail(1) end
        if mapping_errors ~= 0 then return fail(2) end
        hold_custom = true
        start_track(1)
    elseif phase == "native" then
        if read_byte(0x046B) ~= commands[track_index] then
            if bridge_hits == before_bridge then return fail(200 + track_index) end
            return fail(read_byte(0x046B))
        end
        if read_byte(0x046A) ~= 0xC3 and read_byte(0x046A) ~= 0xD3 then
            return fail(83)
        end
        if native_init_hits <= before_init then return fail(52) end
        if native_play_hits - before_play < 10 then
            for index = 7, #init_milestones do
                if init_milestones[index] == 0 then return fail(70 + index) end
            end
            for index = 1, #init_milestones do
                if init_milestones[index] == 0 then return fail(70 + index) end
            end
            if native_init_rts_hits == 0 then return fail(69) end
            if native_after_init_hits == 0 then return fail(70) end
            if native_return_hits == 0 then return fail(68) end
            if bridge_hits - before_bridge < 10 then return fail(100 + track_index) end
            local pc = emu.getState().cpu.pc
            if pc >= 0xB000 and pc <= 0xBCFF then return fail(61) end
            if pc >= 0xBD00 and pc <= 0xBDFF then return fail(62) end
            if pc >= 0x8000 and pc <= 0x9FFF then return fail(63) end
            return fail(120 + track_index)
        end
        if native_apu_writes <= before_apu then return fail(54) end
        if mapping_errors ~= 0 then return fail(55) end
        if unsafe_old_bss_writes ~= 0 or unsafe_old_zp_writes ~= 0 then
            if unsafe_old_bss_writes ~= 0 then return fail(unsafe_old_bss_pc % 256) end
            return fail(40)
        end
        if dmc_handler_hits ~= 0 then return fail(41) end
        if track_index < #commands then
            start_track(track_index + 1)
        else
            before_play = native_play_hits
            before_native_sfx_apu = native_sfx_apu_writes
            write_byte(0x004C, 0x10)
        phase = "native-sfx"
            deadline = frame + 120
        end
    elseif phase == "native-sfx" then
        if read_byte(0x046B) ~= 0xA4 then return fail(42) end
        if native_play_hits <= before_play then return fail(49) end
        if native_sfx_apu_writes <= before_native_sfx_apu then return fail(50) end
        hold_custom = false
        before_stock = stock_hits
        -- $81 must now hand off to the stock engine for the restored Getter song.
        write_byte(0x004C, 0x81)
        phase = "stock-handoff"
        deadline = frame + 240
    elseif phase == "stock-handoff" then
        if stock_hits <= before_stock or read_byte(0x046A) == 0xC3 then
            return fail(43)
        end
        hold_custom = true
        allowed_command = 0x9D
        before_fami = fami_update_hits
        before_fami_apu = fami_apu_writes
        before_bridge = bridge_hits
        write_byte(0x004C, 0x9D)
        if two_engine then
            removed_command_index = 0
            phase = "removed-famistudio"
            deadline = frame + 180
        else
            phase = "famistudio"
            deadline = frame + 1200
        end
    elseif phase == "removed-famistudio" then
        if bridge_hits <= before_bridge then return fail(45) end
        if fami_update_hits ~= before_fami or
           fami_apu_writes ~= before_fami_apu then
            return fail(46)
        end
        if read_byte(0x046B) >= 0x9D and read_byte(0x046B) <= 0x9F then
            return fail(47)
        end
        if read_byte(0x004C) ~= 0xFF or mapping_errors ~= 0 then
            return fail(48)
        end
        if removed_command_index < 2 then
            removed_command_index = removed_command_index + 1
            before_fami = fami_update_hits
            before_fami_apu = fami_apu_writes
            before_bridge = bridge_hits
            allowed_command = 0x9D + removed_command_index
            write_byte(0x004C, allowed_command)
            deadline = frame + 180
        else
            pass()
        end
    elseif phase == "famistudio" then
        if read_byte(0x046B) ~= 0x9D or
           fami_update_hits - before_fami < 100 or
           fami_apu_writes <= before_fami_apu or mapping_errors ~= 0 then
            return fail(44)
        end
        pass()
    end
end, emu.eventType.endFrame)
