-- Cold-boot smoke test for encrypted/decrypted expanded DC ROMs in Mesen.
-- This deliberately avoids the refined15 command-injection harness because
-- the legacy "encryption" patch changes the game's launch/configuration path.

local frame = 0
local target_frames = 600

local function cpu_pc()
    local cpu = emu.getCpuState()
    local pc = cpu.pc or cpu.PC
    if pc == nil then error("CPU PC is unavailable") end
    return pc
end

local function finish()
    local pc = cpu_pc()
    local pass = pc >= 0x8000 and pc <= 0xFFFF

    emu.log(string.format(
        "RESULT pass=%s frames=%d pc=%04X\n",
        tostring(pass), frame, pc))
    if pc < 0x8000 or pc > 0xFFFF then return emu.stop(3) end
    emu.stop(0)
end

local function on_frame()
    frame = frame + 1
    if frame >= target_frames then
        finish()
    end
end

emu.addEventCallback(function()
    local ok, message = pcall(on_frame)
    if not ok then
        emu.log("dc_cipher_mesen_boot_smoke: " .. tostring(message))
        emu.stop(10)
    end
end, emu.eventType.endFrame)
