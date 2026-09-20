; Select the ordinary common driver, It's Not Anime's third-page driver bank,
; or Boss Fight's third-page driver bank before entering the wrapper.

    .base $8000

music_command = $004c
custom_state = $046b
bridge_magic_c = $046a
mapper_select = $8000
mapper_data = $8001

native_engine_bank = $74
native_anime_engine_bank = $75
native_boss_engine_bank = $7b
native_update_entry = $bd00
native_init_entry = $bd03
native_resume_entry = $bd06

dc_mitsume5_dispatcher:
    ldx #native_engine_bank
    lda custom_state
    cmp #$9c
    bne @check_boss
    ldx #native_anime_engine_bank
    bne @engine_ready
@check_boss:
    cmp #$a8
    bne @engine_ready
    ldx #native_boss_engine_bank
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

dc_mitsume5_dispatcher_end:
