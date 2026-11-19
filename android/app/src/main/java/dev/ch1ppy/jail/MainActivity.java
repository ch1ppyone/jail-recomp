package dev.ch1ppy.jail;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** First-run asset installer. Once all files pass validation, launches GameActivity directly. */
public class MainActivity extends Activity {
    private static final int PICK = 100;
    /* Runtime modules and generated game image are shipped with the APK. */
    private static final String[] BUNDLED_MODULES = {
            "libc.img", "libgxm_es4.img", "libgpu_es4.img", "libfios2.img",
            "libpvf.img", "libult.img", "libSceFt2.img"
    };
    private static final String[] KEYS = {"pkg", "firmware", "work"};
    interface Status { void set(String text); }
    private final Map<String, Button> buttons = new HashMap<>();
    private final Map<String, String> labels = new HashMap<>();
    private final Map<String, Uri> pending = new HashMap<>();
    private final ExecutorService copyExecutor = Executors.newSingleThreadExecutor();
    private TextView status;
    private int picking;

    private static GradientDrawable buttonBackground(int fill, int stroke) {
        GradientDrawable d = new GradientDrawable(); d.setColor(fill); d.setStroke(1, stroke); d.setCornerRadius(4); return d;
    }

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        try {
            Assets.installBundledModules(this);
            Assets.installBundledGameImage(this);
            if (Assets.valid(this)) { launchGame(); return; }
        } catch (Exception e) {
            buildLauncher();
            status.setText("Included runtime files could not be installed: " + e.getMessage());
            return;
        }
        buildLauncher();
        if (Assets.canAutoInstall(this)) startAutoInstall();
    }

    private void buildLauncher() {
        getWindow().setStatusBarColor(Color.rgb(5, 5, 6));
        getWindow().setNavigationBarColor(Color.rgb(5, 5, 6));
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.rgb(5, 5, 6));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = (int) (24 * getResources().getDisplayMetrics().density);
        root.setPadding(pad, pad, pad, pad);
        TextView title = new TextView(this);
        title.setText("TOKYO GHOUL: JAIL\nFIRST LAUNCH");
        title.setTextColor(Color.rgb(242, 236, 226)); title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        title.setTextSize(24); title.setPadding(0, 0, 0, pad / 2); root.addView(title);
        TextView hint = new TextView(this);
        hint.setText("Select your original Vita PKG, firmware dump and matching work.bin.\nThe installer decrypts and prepares the game before launching it.");
        hint.setTextColor(Color.rgb(160, 150, 140)); hint.setTextSize(16); root.addView(hint);
        addFile(root, "pkg", "Game package  ·  PCSG00615.pkg");
        addFile(root, "firmware", "Vita firmware  ·  PSVUPDAT.PUP");
        addFile(root, "work", "License  ·  work.bin");
        Button start = new Button(this); start.setText("CHECK FILES  ·  LAUNCH GAME");
        start.setTextColor(Color.WHITE); start.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        start.setBackground(buttonBackground(Color.rgb(145, 0, 25), Color.rgb(220, 15, 45)));
        start.setOnClickListener(v -> installAndLaunch()); root.addView(start);
        status = new TextView(this); status.setTextColor(Color.rgb(210, 190, 170)); status.setTextSize(14); status.setPadding(0, pad / 2, 0, 0); root.addView(status);
        scroll.addView(root); setContentView(scroll);
        refreshButtons();
    }

    private void addFile(LinearLayout root, String key, String label) {
        Button button = new Button(this); button.setText(label + "  ·  CHOOSE FILE");
        button.setTextColor(Color.rgb(225, 218, 208)); button.setAllCaps(false);
        button.setBackground(buttonBackground(Color.rgb(20, 17, 20), Color.rgb(65, 30, 38)));
        button.setOnClickListener(v -> choose(key)); root.addView(button); buttons.put(key, button); labels.put(key, label);
    }

    private void choose(String key) {
        picking = Arrays.asList(KEYS).indexOf(key);
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("application/octet-stream");
        i.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/octet-stream", "*/*"});
        startActivityForResult(i, PICK);
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null || picking < 0) return;
        String key = KEYS[picking];
        Uri uri = data.getData();
        try { getContentResolver().takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION); } catch (Exception ignored) {}
        pending.put(key, uri); refreshButtons();
    }

    private void refreshButtons() {
        for (Map.Entry<String, Button> e : buttons.entrySet()) {
            Uri uri = pending.get(e.getKey());
            e.getValue().setText(labels.get(e.getKey()) + (uri == null ? "  ·  CHOOSE FILE" : "  ·  SELECTED"));
            e.getValue().setTextColor(uri == null ? Color.rgb(225, 218, 208) : Color.rgb(90, 210, 140));
        }
    }

    private void installAndLaunch() {
        if (!allSelected()) { status.setText("Select all three files before launching."); return; }
        status.setText("Validating files and decrypting game package…");
        for (Button b : buttons.values()) b.setEnabled(false);
        copyExecutor.execute(() -> {
            try {
                Assets.install(this, pending, text -> runOnUiThread(() -> status.setText(text)));
                runOnUiThread(this::launchGame);
            } catch (Exception e) {
                runOnUiThread(() -> { status.setText("Error: " + e.getMessage()); for (Button b : buttons.values()) b.setEnabled(true); });
            }
        });
    }

    /** Complete an install whose files were staged over ADB (development/testing). */
    private void startAutoInstall() {
        status.setText("Preparing game data from the staged package…");
        for (Button b : buttons.values()) b.setEnabled(false);
        copyExecutor.execute(() -> {
            try {
                Assets.decryptSource(this, text -> runOnUiThread(() -> status.setText(text)));
                runOnUiThread(this::launchGame);
            } catch (Exception e) {
                runOnUiThread(() -> { status.setText("Error: " + e.getMessage()); for (Button b : buttons.values()) b.setEnabled(true); });
            }
        });
    }

    private boolean allSelected() { for (String key : KEYS) if (!pending.containsKey(key)) return false; return true; }
    private void launchGame() { startActivity(new Intent(this, GameActivity.class)); finish(); }

    static String[] gameArguments(Activity activity) {
        ArrayList<String> args = new ArrayList<>(); String base = activity.getFilesDir().getAbsolutePath();
        args.add("--base-dir"); args.add(base); args.add("--lang"); args.add("en_us");
        args.add("--log"); args.add("1");
        // Let SDL open physical Bluetooth/USB controllers. Touch controls remain available
        // until a controller actually sends input.
        args.add("--gamepad");
        args.add("--env"); args.add("RECOMP_ANDROID_NO_INTRO=1");
        return args.toArray(new String[0]);
    }

    static final class Assets {
        private static final byte[] PUP_MAGIC = {'S', 'C', 'E', 'U', 'F'};
        private static final byte[] CONTENT_ID = "JP0700-PCSG00615_00-TOKYOGHOUL000001".getBytes();
        static boolean valid(Activity a) {
            File source = new File(a.getFilesDir(), "source");
            return validGameImage(new File(new File(a.getFilesDir(), "jail"), "game.img"))
                    && validPup(new File(source, "PSVUPDAT.PUP"))
                    && validWork(new File(source, "work.bin"))
                    && validApp0(a);
        }
        /* the recompiled image starts with "VRIM". A PSN .pkg or the app0 archive is
         * about 1 GB and is not a game image: accepting one made the runtime print
         * "not an image" and crash, so the check now names the file it wants. */
        private static boolean validGameImage(File f) {
            if (!validFile(f, 1024 * 1024)) return false;
            try (InputStream in = new java.io.FileInputStream(f)) {
                byte[] h = new byte[4]; if (in.read(h) < h.length) return false;
                return h[0] == 'V' && h[1] == 'R' && h[2] == 'I' && h[3] == 'M';
            } catch (Exception e) { return false; }
        }
        static void install(Activity a, Map<String, Uri> files, Status status) throws Exception {
            File jail = new File(a.getFilesDir(), "jail"); File source = new File(a.getFilesDir(), "source");
            if (!jail.mkdirs() && !jail.isDirectory()) throw new Exception("cannot create app storage");
            if (!source.mkdirs() && !source.isDirectory()) throw new Exception("cannot create app storage");
            installBundledGameImage(a);
            copy(a, files.get("firmware"), new File(source, "PSVUPDAT.PUP"), 0x80);
            copy(a, files.get("work"), new File(source, "work.bin"), 512);
            File pkg = new File(source, "game.pkg");
            status.set("Copying package… (about 1 GB)");
            copy(a, files.get("pkg"), pkg, 0x100);
            if (!validPkg(pkg)) { pkg.delete(); throw new Exception("the selected file is not a Vita PKG"); }
            decryptSource(a, status);
            if (!valid(a)) throw new Exception("one or more files are invalid");
        }

        static void decryptSource(Activity a, Status status) throws Exception {
            File source = new File(a.getFilesDir(), "source");
            File pkg = new File(source, "game.pkg");
            if (!validPkg(pkg)) throw new Exception("game.pkg is missing");
            if (!validWork(new File(source, "work.bin"))) throw new Exception("work.bin is invalid");
            status.set("Decrypting game data…");
            VitaDecryptor.decryptPkg(pkg, new File(source, "work.bin"), new File(a.getFilesDir(), "fs"),
                    (stage, done, total) -> status.set(total > 1
                            ? stage + "… " + (done * 100 / total) + "%"
                            : stage + "…"));
            /* The ~1 GB copy is only needed for the random access during
               decryption; the user's original stays untouched. */
            pkg.delete();
        }

        static boolean canAutoInstall(Activity a) {
            File source = new File(a.getFilesDir(), "source");
            return validPkg(new File(source, "game.pkg"))
                    && validPup(new File(source, "PSVUPDAT.PUP"))
                    && validWork(new File(source, "work.bin"))
                    && !validApp0(a);
        }

        private static boolean validPkg(File f) {
            if (!validFile(f, 0x100)) return false;
            try (InputStream in = new java.io.FileInputStream(f)) {
                byte[] h = new byte[4];
                if (in.read(h) < 4) return false;
                return (h[0] & 0xFF) == 0x7F && h[1] == 'P' && h[2] == 'K' && h[3] == 'G';
            } catch (Exception e) { return false; }
        }
        private static boolean validApp0(Activity a) {
            File root = new File(new File(a.getFilesDir(), "fs"), "app0");
            // The decrypted Vita app produced by vitadecrypt keeps the executable
            // at the content root; PSP2_GAME contains metadata and resources.
            return new File(root, "eboot.bin").isFile()
                    && new File(root, "game.json").isFile();
        }
        private static void installBundledGameImage(Activity a) throws Exception {
            File jail = new File(a.getFilesDir(), "jail");
            if (!jail.mkdirs() && !jail.isDirectory()) throw new Exception("cannot create app storage");
            File out = new File(jail, "game.img");
            long size;
            try (InputStream probe = a.getAssets().open("game.img")) { size = probe.available(); }
            if (!out.isFile() || out.length() != size) copyAsset(a, "game.img", out);
        }
        static void installBundledModules(Activity a) throws Exception {
            File jail = new File(a.getFilesDir(), "jail");
            if (!jail.mkdirs() && !jail.isDirectory()) throw new Exception("cannot create app storage");
            for (String name : BUNDLED_MODULES) {
                File out = new File(jail, name);
                long assetSize;
                try (InputStream probe = a.getAssets().open(name)) {
                    assetSize = probe.available();
                }
                if (out.isFile() && out.length() == assetSize) continue;
                copyAsset(a, name, out);
            }
        }
        private static void copyAsset(Activity a, String name, File out) throws Exception {
            File tmp = new File(out.getPath() + ".part");
            try (InputStream in = a.getAssets().open(name); FileOutputStream fos = new FileOutputStream(tmp)) {
                byte[] buf = new byte[64 * 1024]; int n;
                while ((n = in.read(buf)) != -1) fos.write(buf, 0, n);
                fos.getFD().sync();
            }
            if (!tmp.renameTo(out)) { tmp.delete(); throw new Exception("cannot install " + name); }
        }
        private static void copy(Activity a, Uri uri, File out, long minimum) throws Exception {
            File tmp = new File(out.getPath() + ".part"); long total = 0; byte[] buf = new byte[1024 * 1024];
            try (InputStream in = a.getContentResolver().openInputStream(uri); FileOutputStream fos = new FileOutputStream(tmp)) {
                if (in == null) throw new Exception("cannot open selected file"); int n;
                while ((n = in.read(buf)) != -1) { fos.write(buf, 0, n); total += n; }
                fos.getFD().sync();
            }
            if (total < minimum || !tmp.renameTo(out)) { tmp.delete(); throw new Exception("invalid file: " + out.getName()); }
        }
        private static boolean validFile(File f, long min) { return f.isFile() && f.length() >= min; }
        private static boolean validPup(File f) {
            if (!validFile(f, 0x80)) return false;
            try (InputStream in = new java.io.FileInputStream(f)) {
                byte[] h = new byte[0x80]; if (in.read(h) < h.length) return false;
                for (int i = 0; i < PUP_MAGIC.length; i++) if (h[i] != PUP_MAGIC[i]) return false;
                boolean version = h[0x10] != 0 || h[0x11] != 0 || h[0x12] != 0 || h[0x13] != 0;
                boolean entries = h[0x18] != 0 || h[0x19] != 0 || h[0x1a] != 0 || h[0x1b] != 0;
                return version && entries;
            } catch (Exception e) { return false; }
        }
        private static boolean validWork(File f) {
            if (f.length() != 512) return false;
            try { byte[] data = java.nio.file.Files.readAllBytes(f.toPath());
                outer: for (int i = 0; i + CONTENT_ID.length <= data.length; i++) {
                    for (int j = 0; j < CONTENT_ID.length; j++) if (data[i + j] != CONTENT_ID[j]) continue outer;
                    return true;
                }
            } catch (Exception ignored) {}
            return false;
        }
        private static GradientDrawable buttonBackground(int fill, int stroke) {
            GradientDrawable d = new GradientDrawable(); d.setColor(fill); d.setStroke(1, stroke); d.setCornerRadius(4); return d;
        }
    }
}
