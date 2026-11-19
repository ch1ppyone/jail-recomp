package dev.ch1ppy.jail;

/** Host-side check of the launcher's free-space message (no Android runtime). */
public final class SpaceCheck {
    public static void main(String[] args) {
        String ok = VitaDecryptor.spaceMessage(5_000_000_000L, 3_000_000_000L, "the game data");
        if (ok != null) throw new AssertionError("expected enough space, got: " + ok);
        String bad = VitaDecryptor.spaceMessage(1_000_000_000L, 3_000_000_000L, "the game data");
        if (bad == null || !bad.contains("Not enough free space")
                || !bad.contains("3.0 GB") || !bad.contains("1.0 GB")) {
            throw new AssertionError("unexpected message: " + bad);
        }
        System.out.println("space check: OK");
    }
}
