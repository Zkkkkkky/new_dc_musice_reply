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

sfx_stream_lo = $0054
sfx_stream_hi = $0055
sfx_repeat    = $0056

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

; Bounded overlay for the 56 migrated stock effects. Bank $77 is converted at
; build time into snapshot records:
;
;   duration, register_count, (register_index, value) * count
;
; Every record contains the complete active SFX register state. Re-reading a
; record costs at most four APU writes for the current data set, independent
; of the effect's age. This replaces the consumed-prefix replay whose cost
; grew every frame and could starve the battle raster IRQ.
native_sfx_update:
    lda $53
    cmp #$38
    bcc @active
    rts

@active:
    lda #$d4
    sta bridge_magic_c
    jsr map_sfx_data

    lda sfx_stream_lo
    ora sfx_stream_hi
    bne @have_stream
    lda $53
    asl
    tay
    lda sfx_table,y
    sta sfx_stream_lo
    iny
    lda sfx_table,y
    sta sfx_stream_hi

@have_stream:
    lda sfx_stream_lo
    sta $4c
    lda sfx_stream_hi
    sta $4d
    ldy #$00
    lda ($4c),y
    beq @end_effect
    ldx sfx_repeat
    bne @duration_ready
    sta sfx_repeat
@duration_ready:
    iny
    lda ($4c),y
    sta $4e
    iny

@write_snapshot:
    lda $4e
    beq @snapshot_done
    lda ($4c),y
    tax
    iny
    lda ($4c),y
    jsr sfx_write_register
    iny
    dec $4e
    jmp @write_snapshot

@snapshot_done:
    dec sfx_repeat
    bne @done
    tya
    clc
    adc $4c
    sta sfx_stream_lo
    lda $4d
    adc #$00
    sta sfx_stream_hi
    jmp @done

@end_effect:
    lda #$ff
    sta $53
    lda #$00
    sta sfx_stream_lo
    sta sfx_stream_hi
    sta sfx_repeat

@done:
    lda #$d3
    sta bridge_magic_c
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
