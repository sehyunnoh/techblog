#!/usr/bin/env python3
"""Model the store-mask arithmetic in OpenJDK's AVX-512 Base64 decoder tail.

Usage: python java4shell-mask-model.py

This is a pen-and-paper model written from the C++ source of
generate_base64_decodeBlock() (src/hotspot/cpu/x86/stubGenerator_x86_64.cpp,
jdk-17.0.21.0.3-ga and jdk-21.0.13.0.3-ga). It does not execute AVX-512
instructions. It reproduces the tail logic:

    output_size = (length / 4) * 3
    if tail ends in '=':   output_size -= 1; and if the byte before is '=': -= 1
    output_mask = bzhiq(-1, output_size)     # BMI2: index taken from bits 7:0;
                                             # an index of 64 or more clears nothing

and the Java-side buffer size from Base64.Decoder.decodedOutLength():
    3 * ((len + 3) / 4) - paddings
"""

MASK64 = (1 << 64) - 1


def bzhiq(value, index):
    """BMI2 BZHI on a 64-bit operand: zero the bits from position index upward."""
    n = index & 0xFF
    return value & MASK64 if n >= 64 else value & ((1 << n) - 1)


def tail_mask(tail):
    """Store mask for the final 1..63 input bytes, as the stub computes it."""
    length = len(tail)
    out = (length // 4) * 3
    if tail[-1] == "=":
        out -= 1
        if length >= 2 and tail[-2] == "=":
            out -= 1
    return out, bzhiq(MASK64, out)


# 1) Which padded tails get a full 64-byte store mask?
print("tail length 1..63, tail ends in one or two '=':")
bad = []
for length in range(1, 64):
    for pad in (1, 2):
        if pad > length:
            continue
        tail = "A" * (length - pad) + "=" * pad
        out, mask = tail_mask(tail)
        if mask == MASK64 and out < 0:
            bad.append((length, tail, out))
for length, tail, out in bad:
    print(f"  tail {tail!r:8} length {length}: output_size {out:+d} -> output_mask all ones (64 bytes stored)")
print(f"  {len(bad)} cases, tail lengths {sorted({b[0] for b in bad})}")
print("  tails of length 4..63 that underflow:",
      sum(1 for L in range(4, 64) for p in (1, 2)
          if tail_mask('A' * (L - p) + '=' * p)[0] < 0))

# 2) What the 65-character trigger from the write-up does
for n_a in (64, 128):
    data = "A" * n_a + "="
    length = len(data)
    paddings = 1 + (data[-2] == "=")
    java_len = 3 * ((length + 3) // 4) - paddings
    full_blocks = (length // 64) * 64       # consumed by the 64-byte loop
    dp = full_blocks // 4 * 3               # output bytes already written
    tail = data[full_blocks:]
    out, mask = tail_mask(tail)
    print(f"\n{n_a} x 'A' + '=': {length} bytes in, Java sizes the result at {java_len} bytes")
    print(f"  64-byte loop decodes {full_blocks} chars -> dp = {dp}; tail {tail!r}: output_size {out}, mask all ones: {mask == MASK64}")
    if mask == MASK64:
        first, last = dp, dp + 63
        print(f"  store covers offsets {first}..{last}; past the {java_len}-byte result: {last + 1 - java_len} bytes (offsets {java_len}..{last})")

# 3) With the patch: padded tails shorter than 4 bytes go to the Java code
print("\nwith the 'cmpl(length, 4); jcc less, L_bruteForce' guard:")
reach = [b for b in bad if b[0] >= 4]
print(f"  underflowing tails that still reach the mask code: {len(reach)}")
