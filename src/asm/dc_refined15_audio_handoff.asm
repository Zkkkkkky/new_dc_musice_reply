; FCEUX-compatible stock handoff for the expanded Mapper 194 ROM.
;
; FCEUX installs its generic KT-008 multicart write hook at $5000 for every
; MMC3-family mapper, including Mapper 194.  A write made during the battle
; path can therefore leave FCEUX's private PRG high-bit latch enabled.  The
; original 512 KiB ROM masks that bit away; after expanding to 1 MiB it turns
; a later stock bank such as $1C into $5C and makes the event pointer read as
; zero.  $27 is FCEUX's defined latch-clear value.  Real Mapper 194 hardware
; and Mesen leave $5000 unmapped, so the compatibility write is inert there.

    .base $99ec

mapper_select = $8000
mapper_data   = $8001
music_command = $004c
bridge_magic_c = $046a
stock_restore_dispatch = $99bc
fceux_kt_clear = $5000

; Keep the historical $99EC entry and the fixed $9A04 native-return address.
stock_handoff_dispatch:
    jmp stock_handoff_impl
    .dsb $15, $00

native_return_dispatch:
    lda #$27
    sta fceux_kt_clear
    lda #$c3
    sta bridge_magic_c
    lda #$87
    sta mapper_select
    lda #$64
    sta mapper_data
    clc
    jmp stock_restore_dispatch

stock_handoff_impl:
    pha
    lda #$27
    sta fceux_kt_clear
    lda #$87
    sta mapper_select
    lda #$19
    sta mapper_data
    lda #$fe
    sta music_command
    jsr $8020
    pla
    sta music_command
    jmp $8020

dc_refined15_audio_handoff_v7_end:
