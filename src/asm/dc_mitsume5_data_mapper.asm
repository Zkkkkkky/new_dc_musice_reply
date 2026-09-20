; Extended native data mapper placed in the unused $BF00-$BFFF wrapper tail.
; Existing wrapper calls still target their original map_native_data label;
; the builder replaces its first instruction with JMP $BF00.

    .base $bf00

custom_state = $046b
mapper_select = $8000
mapper_data = $8001

dc_mitsume5_map_native_data:
    lda custom_state
    cmp #$a6
    beq @last_impression
    cmp #$a7
    beq @stage_5_3
    cmp #$a8
    beq @boss_fight
    cmp #$a9
    beq @introduction
    cmp #$aa
    beq @ending
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
    lda #$67                  ; $A5, Beyond the Time
    bne @map
@last_impression:
    lda #$78                  ; $A6, lower ROM only; upper bridge rejects it
    bne @map
@stage_5_3:
    lda #$79                  ; $A7
    bne @map
@boss_fight:
    lda #$7a                  ; $A8
    bne @map
@introduction:
    lda #$7c                  ; $A9
    bne @map
@ending:
    lda #$7d                  ; $AA
@map:
    tax
    lda #$86
    sta mapper_select
    stx mapper_data
    rts

dc_mitsume5_map_native_data_end:
