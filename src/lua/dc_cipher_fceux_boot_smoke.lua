-- Cold-boot smoke test for encrypted/decrypted expanded DC ROMs in FCEUX.

local output = assert(io.open("dc_cipher_fceux_boot_smoke.log", "w"))
local valid_pc_frames = 0
local pc_changes = 0
local previous_pc = -1
local frames = 1800

emu.speedmode("maximum")
emu.softreset()

for frame = 1, frames do
    emu.frameadvance()
    local pc = memory.getregister("pc")
    if pc >= 0x8000 and pc <= 0xFFFF then
        valid_pc_frames = valid_pc_frames + 1
    end
    if previous_pc >= 0 and pc ~= previous_pc then
        pc_changes = pc_changes + 1
    end
    previous_pc = pc
end

local pc = memory.getregister("pc")
local pass = valid_pc_frames >= 1700 and pc_changes >= 100
output:write(string.format(
    "RESULT pass=%s frames=%d validPcFrames=%d pcChanges=%d pc=%04X\n",
    tostring(pass), frames, valid_pc_frames, pc_changes, pc))
output:close()
emu.exit()
