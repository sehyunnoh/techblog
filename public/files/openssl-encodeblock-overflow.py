"""Call the real EVP_EncodeBlock() with input lengths around the int limit.

Needs ~4 GB of free RAM. The output buffer is always allocated with the correct
size_t size (4 * ceil(n/3) + 1), so nothing is written out of bounds: this only
observes the int return value. Usage: python openssl-encodeblock-overflow.py <libcrypto path>
"""
import ctypes, sys, time

lib = ctypes.CDLL(sys.argv[1])
lib.OpenSSL_version.restype = ctypes.c_char_p
lib.EVP_EncodeBlock.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
lib.EVP_EncodeBlock.restype = ctypes.c_int
print("library:", lib.OpenSSL_version(0).decode())

LIMIT = (2**31 - 1) // 4 * 3          # 1,610,612,733: the bound used in the fix PR
src = ctypes.create_string_buffer(LIMIT + 3)   # zero-filled input, big enough for both lengths
for n in (LIMIT, LIMIT + 1):
    need = 4 * ((n + 2) // 3) + 1
    out = ctypes.create_string_buffer(need)
    t = time.time()
    r = lib.EVP_EncodeBlock(out, src, n)
    print(f"n={n:,}  correct output size={need - 1:,}  returned={r:,}  ({time.time()-t:.1f}s)")
    del out
