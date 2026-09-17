; Bank $76 transition code.  It executes from $8000 while replacing the
; $A000 window with the relocated refined-driver bank.

    .base $8000

music_command = $004c
custom_state = $046b
bridge_magic_c = $046a
mapper_select = $8000
mapper_data = $8001

native_engine_bank = $74
native_anime_engine_bank = $75
native_update_entry = $bd00
native_init_entry = $bd03
native_resume_entry = $bd06

dc_refined15_dispatcher:
    ldx #native_engine_bank
    lda custom_state
    cmp #$9c
    bne @engine_ready
    ldx #native_anime_engine_bank
@engine_ready:
    lda #$87
    sta mapper_select
    stx mapper_data

    lda bridge_magic_c
    cmp #$d3
    beq @resume
    cmp #$d4
    beq @resume
    lda music_command
    cmp #$fe
    beq @init
    jmp native_update_entry
@init:
    jmp native_init_entry
@resume:
    jmp native_resume_entry

dc_refined15_dispatcher_end:
