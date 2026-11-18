import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;

/**
 * Probe for the Java4Shell tail bug: decode n x 'A' + "=" into a large array
 * after JIT warm-up and report which bytes past the expected result changed.
 * Usage: java Base64TailProbe [n]   (n defaults to 64; the write-up uses 128 on JDK 17)
 * Every write stays inside the 4096-byte array. This is a re-implementation of
 * the check described in the Calif write-up, not a copy of its code.
 */
public final class Base64TailProbe {
    public static void main(String[] args) {
        int n = args.length > 0 ? Integer.parseInt(args[0]) : 64;
        Base64.Decoder dec = Base64.getDecoder();
        byte[] good = "A".repeat(n).getBytes(StandardCharsets.US_ASCII);
        byte[] bad = ("A".repeat(n) + "=").getBytes(StandardCharsets.US_ASCII);
        byte[] out = new byte[4096];
        long sink = 0;
        for (int i = 0; i < 300_000; i++) sink += dec.decode(good, out);
        Arrays.fill(out, (byte) 0x5a);
        boolean rejected = false;
        try { dec.decode(bad, out); } catch (IllegalArgumentException e) { rejected = true; }
        int expected = 3 * ((bad.length + 3) / 4) - 1;   // Decoder.decodedOutLength for one '='
        int changed = 0, first = -1, last = -1;
        for (int i = expected; i < out.length; i++) {
            if (out[i] != (byte) 0x5a) { changed++; if (first < 0) first = i; last = i; }
        }
        System.out.println("runtime=" + System.getProperty("java.runtime.version") + " sink=" + (sink != 0));
        System.out.println("n=" + n + " rejected=" + rejected + " expectedLen=" + expected
            + " changedPastResult=" + changed + " first=" + first + " last=" + last);
    }
}
