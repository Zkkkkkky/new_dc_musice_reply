; Wrapper stored in the unused tail of each relocated driver bank at $BD00.
; The driver itself occupies $B000-$BC6E.

    .base $bd00

music_command = $004c
custom_state = $046b
bridge_magic_c = $046a
mapper_select = $8000
mapper_data = $8001

native_driver_init = $b100
native_driver_play = $b160
stock_low_bank = $60
sfx_data_bank = $77
sfx_table = $8004
native_return_dispatch = $9a04

sfx_progress_lo = $0054
sfx_progress_hi = $0055
sfx_repeat = $0056

native_update_entry:
    jmp native_update_impl
native_init_entry:
    jmp native_init_impl
native_resume_entry:
    jmp native_resume_impl

native_update_impl:
    lda #$d3
    sta bridge_magic_c
    jsr map_native_data

    lda $4c
    pha
    lda $4d
    pha
    lda $4e
    pha
    lda $4f
    pha
    lda $50
    pha
    lda $51
    pha
    lda $52
    pha
    lda $53
    pha
    jsr native_driver_play
    pla
    sta $53
    jsr native_sfx_update
    pla
    sta $52
    pla
    sta $51
    pla
    sta $50
    pla
    sta $4f
    pla
    sta $4e
    pla
    sta $4d
    pla
    sta $4c
    lda #$ff
    sta music_command
    jmp return_to_game

native_init_impl:
    lda #$d3
    sta bridge_magic_c
    jsr map_native_data

    lda $4c
    pha
    lda $4d
    pha
    lda $4e
    pha
    lda $4f
    pha
    lda $50
    pha
    lda $51
    pha
    lda $52
    pha
    lda $53
    pha
    lda #$00
    tax
    tay
    jsr native_driver_init
    pla
    sta $53
    pla
    sta $52
    pla
    sta $51
    pla
    sta $50
    pla
    sta $4f
    pla
    sta $4e
    pla
    sta $4d
    pla
    sta $4c
    lda #$ff
    sta music_command

return_to_game:
    lda #$86
    sta mapper_select
    lda #stock_low_bank
    sta mapper_data
    jmp native_return_dispatch

native_resume_impl:
    lda bridge_magic_c
    cmp #$d4
    beq @sfx_data
    jsr map_native_data
    rts
@sfx_data:
    jsr map_sfx_data
    rts

map_native_data:
    lda custom_state
    cmp #$a5
    beq @replacement
    cmp #$a0
    bcs @high_commands
    cmp #$96
    bcs @middle_commands
    sec
    sbc #$2f                  ; $94/$95 -> banks $65/$66
    bcs @map
@middle_commands:
    sec
    sbc #$2e                  ; $96-$9C -> banks $68-$6E
    bcs @map
@high_commands:
    sec
    sbc #$31                  ; $A0-$A4 -> banks $6F-$73
    bcs @map
@replacement:
    lda #$67                  ; $A5/$22, archive index 2, Beyond the Time
@map:
    tax
    lda #$86
    sta mapper_select
    stx mapper_data
    rts

; Compact overlay for the 56 migrated stock effects.  The stream format is
; FamiStudio's simple SFX bytecode: $80-$8A write one of the 11 tonal APU
; values, $01-$7F wait, and $00 ends the effect.  Only four persistent bytes
; are needed ($53-$56).  Instead of keeping an 11-byte mix buffer, replay the
; already-consumed prefix after the music update; the last write to each APU
; register reconstructs the current effect state.
native_sfx_update:
    lda $53
    cmp #$38
    bcc @active
    rts

@active:
    lda #$d4
    sta bridge_magic_c
    jsr map_sfx_data

    lda $53
    asl
    tay
    lda sfx_table,y
    sta $4c
    iny
    lda sfx_table,y
    sta $4d

    lda sfx_progress_lo
    sta $4e
    lda sfx_progress_hi
    sta $4f

; Replay the consumed prefix, ignoring wait bytes but restoring every explicit
; register value after the refined music driver overwrote the APU this frame.
@replay_check:
    lda $4e
    ora $4f
    beq @at_current
    jsr sfx_read_replay_byte
    bmi @replay_register
    jmp @replay_check
@replay_register:
    and #$7f
    tax
    jsr sfx_read_replay_byte
    jsr sfx_write_register
    jmp @replay_check

@at_current:
    lda sfx_repeat
    beq @read_new
    dec sfx_repeat
    bne @done

@read_new:
    ldy #$00
    lda ($4c),y
    beq @end_effect
    bmi @new_register

    sta sfx_repeat
    jsr sfx_advance_current
    jmp @done

@new_register:
    and #$7f
    tax
    jsr sfx_advance_current
    ldy #$00
    lda ($4c),y
    jsr sfx_write_register
    jsr sfx_advance_current
    jmp @read_new

@end_effect:
    lda #$ff
    sta $53

@done:
    lda #$d3
    sta bridge_magic_c
    rts

; Read one previously consumed byte, advance the stream pointer, and decrement
; the 16-bit replay count in $4E/$4F.
sfx_read_replay_byte:
    ldy #$00
    lda ($4c),y
    pha
    inc $4c
    bne @pointer_ok
    inc $4d
@pointer_ok:
    lda $4e
    bne @low_ok
    dec $4f
@low_ok:
    dec $4e
    pla
    rts

; Advance both the live stream pointer and its persistent 16-bit progress.
sfx_advance_current:
    inc $4c
    bne @pointer_ok
    inc $4d
@pointer_ok:
    inc sfx_progress_lo
    bne @progress_ok
    inc sfx_progress_hi
@progress_ok:
    rts

; X is a compact output-buffer index $00-$0A; A is the value.
sfx_write_register:
    pha
    lda sfx_apu_offsets,x
    tax
    pla
    sta $4000,x
    rts

map_sfx_data:
    lda #$86
    sta mapper_select
    lda #sfx_data_bank
    sta mapper_data
    rts

sfx_apu_offsets:
    db $00,$02,$03,$04,$06,$07,$08,$0a,$0b,$0c,$0e

dc_refined15_native_wrapper_end:
