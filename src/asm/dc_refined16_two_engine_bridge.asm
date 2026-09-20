; Two-engine dispatcher for the expanded Mapper 194 DC ROM.
;
; The original DC engine remains responsible for stock music.  The relocated
; F000/F100/F160 common driver handles the 15 existing refined tracks plus
; LAST IMPRESSION on command $A6.  Removed legacy commands $9D-$9F remain
; safely consumed.

    .base $b500

music_command = $004c
music_state   = $004d
music_current = $0052
music_limit   = $0053

bridge_magic_c = $046a
custom_state   = $046b

sfx_stream_lo = $0054
sfx_stream_hi = $0055
sfx_repeat    = $0056

mapper_select = $8000
mapper_data   = $8001

native_dispatch_bank = $76
stock_low_bank = $60

stock_restore_dispatch = $99bc
stock_handoff_dispatch = $99ec
native_dispatch_entry = $8000

dc_refined16_two_engine_bridge:
    lda bridge_magic_c
    cmp #$d3
    beq @launch_native
    cmp #$d4
    bne @direct_selectors
    jmp @launch_native

@direct_selectors:
    lda music_command
    cmp #$94
    bcc @check_active
    cmp #$9d
    bcs @direct_at_least_9d
    jmp @start_native
@direct_at_least_9d:
    cmp #$a0
    bcc @discard_removed_song
    cmp #$a7
    bcs @check_active
    jmp @start_native

@discard_removed_song:
    lda #$ff
    sta music_command

@check_active:
    lda bridge_magic_c
    cmp #$c3
    bne @stock_update

    lda custom_state
    cmp #$94
    bcc @stock_update
    cmp #$9d
    bcc @native_active
    cmp #$a0
    bcc @stock_update
    cmp #$a7
    bcc @native_active
    jmp @stock_update

@native_active:
    lda music_command
    cmp #$ff
    beq @native_update
    tax
    lda #$ff
    sta music_command
    txa
    bmi @leave_with_stock_command

    cmp #$38
    bcs @native_update
    sta music_limit
    lda #$00
    sta sfx_stream_lo
    sta sfx_stream_hi
    sta sfx_repeat
    jmp @native_update

@native_update:
    lda #$ff
    sta music_command

@launch_native:
    lda #$86
    sta mapper_select
    lda #native_dispatch_bank
    sta mapper_data
    jmp native_dispatch_entry

@stock_update:
    sec
    jmp stock_restore_dispatch

@leave_with_stock_command:
    cmp #$fe
    bne @handoff_command_ready
    lda #$ff
@handoff_command_ready:
    tax
    lda #$00
    sta bridge_magic_c
    sta custom_state
    jsr @restore_stock_low_bank
    txa
    jmp stock_handoff_dispatch

@start_native:
    sta custom_state
    jsr @set_magic

    lda custom_state
    cmp #$a0
    bcc @native_low_logical_id
    sec
    sbc #$83
    bcs @native_store_logical_id
@native_low_logical_id:
    sec
    sbc #$80
@native_store_logical_id:
    sta music_current
    lda #$00
    sta music_state
    lda #$ff
    sta music_limit
    lda #$00
    sta sfx_stream_lo
    sta sfx_stream_hi
    sta sfx_repeat
    lda #$fe
    sta music_command
    jmp @launch_native

@set_magic:
    lda #$c3
    sta bridge_magic_c
    rts

@restore_stock_low_bank:
    lda #$86
    sta mapper_select
    lda #stock_low_bank
    sta mapper_data
    rts

dc_refined16_two_engine_bridge_end:
