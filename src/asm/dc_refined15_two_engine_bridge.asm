; Two-engine dispatcher for the expanded Mapper 194 DC ROM.
;
; The original DC engine remains responsible for stock music.  The relocated
; F000/F100/F160 common driver handles the 15 refined tracks.  The older
; FamiStudio instance and its $9D-$9F songs are intentionally absent.

    .base $b500

music_command = $004c
music_state   = $004d
music_current = $0052
music_limit   = $0053

bridge_magic_a = $0468
bridge_magic_b = $0469
bridge_magic_c = $046a
custom_state   = $046b

sfx_progress_lo = $0054
sfx_progress_hi = $0055
sfx_repeat      = $0056

mapper_select = $8000
mapper_data   = $8001

native_dispatch_bank = $76
stock_low_bank = $60

stock_restore_dispatch = $99bc
stock_handoff_dispatch = $99ec
native_dispatch_entry = $8000

dc_refined15_two_engine_bridge:
    ; A native-driver update can cross a video frame.  A nested NMI must only
    ; restore the interrupted mappings; it must not read transient $004C-$0053
    ; state or start a second update.
    lda bridge_magic_a
    cmp #$5a
    bne @direct_selectors
    lda bridge_magic_b
    cmp #$a5
    bne @direct_selectors
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
    cmp #$a6
    bcs @check_active
    jmp @start_native

@discard_removed_song:
    ; $9D-$9F belonged to the removed FamiStudio instance.  Consume them so
    ; stale character/map bindings cannot reach the stock driver as invalid
    ; song numbers.  The currently playing track, if any, continues safely.
    lda #$ff
    sta music_command

@check_active:
    lda bridge_magic_a
    cmp #$5a
    bne @stock_update
    lda bridge_magic_b
    cmp #$a5
    bne @stock_update
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
    cmp #$a6
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

    ; The relocated refined driver owns music, but a compact one-stream SFX
    ; overlay replays the migrated 56-effect data after each music update.
    ; $53 remains the original priority/effect byte; $54-$56 hold only overlay
    ; progress while a refined song is active.
    cmp #$38
    bcs @native_update
    sta music_limit
    lda #$00
    sta sfx_progress_lo
    sta sfx_progress_hi
    sta sfx_repeat
    jmp @native_update

@native_update:
    lda #$ff
    sta music_command

@launch_native:
    ; This code executes from bank $64 at $A000.  Bank $76 replaces only the
    ; $8000 window, then changes the $A000 window from its safe dispatcher.
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
    sta bridge_magic_a
    sta bridge_magic_b
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
    sta sfx_progress_lo
    sta sfx_progress_hi
    sta sfx_repeat
    lda #$fe
    sta music_command
    jmp @launch_native

@set_magic:
    lda #$5a
    sta bridge_magic_a
    lda #$a5
    sta bridge_magic_b
    lda #$c3
    sta bridge_magic_c
    rts

@restore_stock_low_bank:
    lda #$86
    sta mapper_select
    lda #stock_low_bank
    sta mapper_data
    rts

dc_refined15_two_engine_bridge_end:
